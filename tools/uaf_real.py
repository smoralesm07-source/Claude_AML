"""Construye las secciones `sectors` y `benchmark` desde datos reales.

Fuentes:
  - Radar_UAF/data/gold/entities.parquet     registro de sujetos obligados con RUT
  - Radar_UAF/data/gold/statistics.parquet   estadísticas oficiales publicadas por la UAF
  - Context-Hub/data/seed/sectors_v1.csv     taxonomía de 55 actividades UAF
  - Context-Hub/data/seed/sector_sii_mapping_v1_part*.csv   crosswalk UAF-ACTECO

Devuelve None cuando las fuentes no están disponibles, para que el constructor
caiga en la sobrecapa demostrativa sin romperse.

Regla de gobierno: el cruce entre el nombre de actividad del registro UAF y la
taxonomía del Context Hub se hace por igualdad exacta sobre la forma normalizada.
Lo que no cruza exacto NO se fuerza: se reporta como brecha de equivalencia.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

ENTITIES = "Radar_UAF/data/gold/entities.parquet"
STATISTICS = "Radar_UAF/data/gold/statistics.parquet"
TAXONOMY = "Context-Hub/data/seed/sectors_v1.csv"
MAPPING_GLOB = "Context-Hub/data/seed/sector_sii_mapping_v1_part*.csv"

# Métricas nacionales que se publican como serie anual y sí son comparables.
NATIONAL_SERIES = {
    "ros_recibidos": ("ROS recibidos", "reportes"),
    "roe_recibidos_miles": ("ROE recibidos", "miles de reportes"),
    "entidades_reportantes_total": ("Universo inscrito", "entidades"),
    "acciones_supervision": ("Acciones de supervisión", "acciones"),
    "procesos_sancionatorios_iniciados": ("Procesos sancionatorios iniciados", "procesos"),
}


def normalize(text: str) -> str:
    """Forma normalizada para el cruce exacto: sin acentos, sin caso, sin puntuación."""
    stripped = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def load_frames(repos_root: Path):
    """Carga los parquet del gold de Radar UAF. None si falta pyarrow o los archivos."""
    try:
        import pandas as pd
    except ImportError:
        return None, None
    ent_path = repos_root / ENTITIES
    stat_path = repos_root / STATISTICS
    if not ent_path.exists() or not stat_path.exists():
        return None, None
    try:
        return pd.read_parquet(ent_path), pd.read_parquet(stat_path)
    except Exception:
        return None, None


def load_taxonomy(repos_root: Path):
    """55 actividades UAF y el crosswalk hacia ACTECO del SII."""
    tax_path = repos_root / TAXONOMY
    if not tax_path.exists():
        return None, None
    with tax_path.open(encoding="utf-8") as fh:
        sectors = list(csv.DictReader(fh))

    mappings: list[dict] = []
    for part in sorted((repos_root / "Context-Hub/data/seed").glob("sector_sii_mapping_v1_part*.csv")):
        with part.open(encoding="utf-8") as fh:
            mappings.extend(csv.DictReader(fh))
    return sectors, mappings


def build(repos_root: Path) -> dict | None:
    """Arma `sectors`, `benchmark` y las brechas de equivalencia. None si no hay fuentes."""
    entities, stats = load_frames(repos_root)
    sectors_raw, mappings = load_taxonomy(repos_root)
    if entities is None or sectors_raw is None:
        return None

    obliged = entities[entities.entity_type == "SUJETO_OBLIGADO"]

    # ── Universo por actividad, tal como lo declara el registro ──────────
    registry_counts = obliged.name.value_counts().to_dict()
    by_key = {normalize(k): (k, v) for k, v in registry_counts.items()}

    # ── Crosswalk hacia ACTECO, contado por sector ──────────────────────
    strong = {"MATCH_FUERTE"}
    map_by_sector: dict[str, dict] = {}
    for row in mappings or []:
        sid = row["uaf_sector_id"]
        slot = map_by_sector.setdefault(sid, {"total": 0, "strong": 0})
        slot["total"] += 1
        if row.get("original_use", "").strip() in strong:
            slot["strong"] += 1

    sectors: list[dict] = []
    matched_keys: set[str] = set()
    for row in sectors_raw:
        sid_num = int(row["uaf_sector_id"])
        key = normalize(row["uaf_activity_name"])
        registry = by_key.get(key)
        if registry:
            matched_keys.add(key)
        maps = map_by_sector.get(row["uaf_sector_id"], {"total": 0, "strong": 0})
        sectors.append({
            "sector_id": f"UAF-SEC-{sid_num:02d}",
            "name": row["uaf_activity_name"],
            "macrofamily": row.get("macrofamily"),
            # Real: proviene del registro publicado por la UAF.
            "so_count": int(registry[1]) if registry else None,
            "registry_label": registry[0] if registry else None,
            "crosswalk_status": "VALIDATED_EXACT" if registry else "NO_REGISTRY_MATCH",
            "acteco_mappings": maps["total"] or None,
            "acteco_strong_mappings": maps["strong"] or None,
            # La UAF no publica ROS/ROE ni sanciones desagregados por actividad.
            # missing != zero: se serializa NO_DATA.
            "ros_reporters": None,
            "roe_reporters": None,
            "sanctioned": None,
            "strong_match_unregistered": None,
        })

    # ── Actividades del registro sin equivalencia exacta en la taxonomía ─
    gaps = [
        {"registry_label": label, "so_count": int(count), "status": "AMBIGUOUS"}
        for key, (label, count) in sorted(by_key.items(), key=lambda kv: -kv[1][1])
        if key not in matched_keys
    ]

    total_registry = int(obliged.shape[0])
    mapped_entities = sum(s["so_count"] or 0 for s in sectors)

    benchmark = build_benchmark(stats, total_registry, mapped_entities, gaps)

    return {
        "sectors": sectors,
        "benchmark": benchmark,
        "sector_gaps": gaps,
        "provenance": {
            "sectors": "REAL · Radar_UAF/data/gold/entities.parquet + Context-Hub taxonomía",
            "benchmark": "REAL · Radar_UAF/data/gold/statistics.parquet",
            "registry_entities": total_registry,
            "mapped_entities": mapped_entities,
            "mapped_pct": round(mapped_entities / total_registry * 100, 1) if total_registry else None,
        },
    }


def suspect_zeros(series: list[dict]) -> list[dict]:
    """Marca ceros rodeados de valores distintos de cero en una misma serie.

    No se corrigen ni se ocultan: el radar los publica como hechos oficiales con
    confianza 1.0, y el cockpit no tiene autoridad para contradecir a la fuente.
    Se levantan para que el Data Steward los verifique contra el informe original,
    porque un cero que en realidad es «sin dato» rompe el principio missing != zero
    aguas abajo.
    """
    flags = []
    for entry in series:
        values = [p["value"] for p in entry["points"]]
        if len(values) < 3 or all(v == 0 for v in values):
            continue
        zeros = [p for p in entry["points"] if p["value"] == 0]
        nonzero = [v for v in values if v != 0]
        if zeros and nonzero:
            flags.append({
                "metric": entry["metric"],
                "label": entry["label"],
                "periods": [p["period"] for p in zeros],
                "severity": "WARN",
                "text": f"La serie «{entry['label']}» registra 0 en "
                        f"{', '.join(p['period'] for p in zeros)} mientras el resto del "
                        f"período va de {min(nonzero):,.0f} a {max(nonzero):,.0f}. El radar los "
                        f"publica como hecho oficial con confianza 1.0. Verificar contra el "
                        f"informe de origen si se trata de un cero real o de una ausencia de dato.",
            })
    return flags


def build_benchmark(stats, total_registry: int, mapped_entities: int, gaps: list) -> dict:
    """Benchmark nacional. La UAF no publica desagregación sectorial de ROS/ROE."""
    series: list[dict] = []
    if stats is not None:
        for metric, (label, unit) in NATIONAL_SERIES.items():
            rows = stats[(stats.metric == metric) & (stats.period.astype(str).str.len() == 4)]
            points = sorted(
                ({"period": str(r.period), "value": float(r.value), "source_url": r.source_url}
                 for r in rows.itertuples()),
                key=lambda p: p["period"])
            if points:
                series.append({"metric": metric, "label": label, "unit": unit, "points": points})

    def latest(metric: str):
        entry = next((s for s in series if s["metric"] == metric), None)
        return entry["points"][-1] if entry else None

    ros = latest("ros_recibidos")
    roe = latest("roe_recibidos_miles")
    universe = latest("entidades_reportantes_total")

    derived: list[dict] = []
    if ros and universe:
        derived.append({
            "label": "ROS por sujeto obligado inscrito",
            "value": round(ros["value"] / universe["value"], 2),
            "unit": "ROS/entidad",
            "period": ros["period"],
            "note": "Intensidad de reporte del sistema completo. No indica cumplimiento "
                    "individual: un solo sujeto obligado puede concentrar muchos ROS.",
        })
    if roe and universe:
        derived.append({
            "label": "ROE por sujeto obligado inscrito",
            "value": round(roe["value"] * 1000 / universe["value"], 1),
            "unit": "ROE/entidad",
            "period": roe["period"],
            "note": "El ROE es reporte de operación en efectivo sobre umbral; su volumen "
                    "responde al giro del sector, no al riesgo de la entidad.",
        })
    ros_series = next((s for s in series if s["metric"] == "ros_recibidos"), None)
    if ros_series and len(ros_series["points"]) >= 2:
        first, last = ros_series["points"][0], ros_series["points"][-1]
        derived.append({
            "label": f"Variación de ROS {first['period']}–{last['period']}",
            "value": round((last["value"] / first["value"] - 1) * 100, 1),
            "unit": "%",
            "period": f"{first['period']}–{last['period']}",
            "note": "Un alza de ROS puede reflejar mayor detección, mayor actividad ilícita "
                    "o cambios de instrucción del supervisor. No es interpretable por sí sola.",
        })

    return {
        "level": "NATIONAL",
        "series": series,
        "derived": derived,
        "quality_flags": suspect_zeros(series),
        "coverage": {
            "registry_entities": total_registry,
            "mapped_entities": mapped_entities,
            "mapped_pct": round(mapped_entities / total_registry * 100, 1) if total_registry else None,
            "unmapped_activities": len(gaps),
        },
        "caveats": [
            {
                "id": "BMK_NO_SECTOR_BREAKDOWN",
                "title": "La UAF no publica ROS/ROE por actividad",
                "text": "Las estadísticas oficiales son agregados nacionales. La intensidad de "
                        "señal por sector (BMK_SIGNAL_INTENSITY) no es computable con las fuentes "
                        "públicas disponibles y se serializa NO_DATA. El benchmark se ancla a "
                        "nivel nacional y la desagregación sectorial se limita al universo inscrito.",
            },
            {
                "id": "BMK_REPORTANTES_ES_UNIVERSO",
                "title": "«Entidades reportantes» no son quienes reportaron",
                "text": "La métrica publicada entidades_reportantes_total coincide exactamente con "
                        "la suma de sujetos obligados del sector privado más entidades públicas "
                        "inscritas (9.403 + 508 = 9.911 en 2025). Es el universo inscrito, no el "
                        "conjunto que efectivamente presentó reportes. No se deriva de ella ninguna "
                        "tasa de cumplimiento: KRI_ROS_GAP queda fuera de alcance con estas fuentes.",
            },
        ],
    }
