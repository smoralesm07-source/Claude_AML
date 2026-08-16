#!/usr/bin/env python3
"""Ensambla el contrato de consumo del IFL Cockpit.

Las secciones `sources` y `program_health` se derivan de los
`interop/integration_manifest_v1.json` REALES de los repositorios hermanos.
El resto se toma de `demo_overlay.json` mientras la capa de fusión no las
materialice; esas secciones quedan marcadas en `provenance` como sintéticas.

Uso:
    python tools/build_cockpit_data.py                     # busca los radares en ..
    python tools/build_cockpit_data.py --repos-root /ruta  # raíz explícita
    python tools/build_cockpit_data.py --validate          # valida contra el esquema
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uaf_real  # noqa: E402  (requiere el sys.path anterior)

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
OUT = ROOT / "app" / "data" / "cockpit_contract_v1.json"
SCHEMA = ROOT / "contracts" / "cockpit_contract_v1.schema.json"
CATALOG = ROOT / "contracts" / "metrics_catalog_v1.json"

# Normalización de los `current_status` que usan los manifiestos hacia el
# vocabulario cerrado del contrato del cockpit.
KEY_STATUS = {
    "NATIVE_INTEROP_READY": "NATIVE",
    "NATIVE_TRANSACTION_INTEROP_READY": "NATIVE",
    "NATIVE_PARQUET_READY": "NATIVE",
    "ADAPTER_READY": "READY",
    "FUSION_CONTRACT_READY": "READY",
    "ADAPTER_PARTIAL": "PARTIAL",
    "NOT_PRIMARY_DIMENSION": "NOT_PRIMARY",
}

# Peso de cada estado para el cálculo de cobertura conformada.
KEY_WEIGHT = {"NATIVE": 1.0, "READY": 1.0, "PARTIAL": 0.5, "NOT_PRIMARY": None, None: None}


def infer_from_materialization(block: dict | None) -> str | None:
    """Infiere estado cuando el bloque no declara `current_status`.

    Context Hub no usa `current_status`: declara directamente cuántas filas
    materializó (`region_rows_materialized`, `seeded_sectors`). Contar eso como
    ausencia de dato sería leer mal el manifiesto.
    """
    if not isinstance(block, dict):
        return None
    evidence = [v for k, v in block.items()
                if isinstance(v, int) and ("materialized" in k or k.startswith("seeded_"))]
    if evidence and any(v > 0 for v in evidence):
        return "NATIVE"
    return None


def norm_key_status(raw: str | None) -> str | None:
    """Traduce un `current_status` de manifiesto al vocabulario del contrato."""
    if not raw:
        return None
    if raw in KEY_STATUS:
        return KEY_STATUS[raw]
    # Los manifiestos usan cadenas libres para `sector`; se clasifican por forma.
    if "NATIVE" in raw:
        return "NATIVE"
    if "READY" in raw:
        return "READY"
    if "PARTIAL" in raw or "REFERENCE" in raw or "CANDIDATE" in raw:
        return "PARTIAL"
    if "NOT_PRIMARY" in raw:
        return "NOT_PRIMARY"
    return "PARTIAL"


def status_from_stage(stage: str, keys: dict) -> str:
    """Semáforo de la fuente a partir de su etapa y sus claves conformadas."""
    if not stage:
        return "NO_DATA"
    resolved = [v for v in keys.values() if v in ("NATIVE", "READY")]
    partial = [v for v in keys.values() if v == "PARTIAL"]
    if stage.startswith("ADAPTER_PARTIAL"):
        return "WARN"
    if len(resolved) >= 2 and not partial:
        return "OK"
    if resolved:
        return "WARN"
    return "CRIT"


def read_manifest(repos_root: Path, dirname: str) -> dict | None:
    path = repos_root / dirname / "interop" / "integration_manifest_v1.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"  ! {dirname}: manifiesto ilegible ({exc})", file=sys.stderr)
        return None


def build_sources(repos_root: Path, config: dict) -> tuple[list[dict], list[str]]:
    """Construye `sources` desde los interop reales. Devuelve también las ausencias."""
    sources, missing = [], []
    for entry in config["sources"]:
        manifest = read_manifest(repos_root, entry["dir"])
        if manifest is None:
            missing.append(entry["dir"])
            sources.append({
                "source_id": entry["source_id"],
                "label": entry["label"],
                "repository": f"smoralesm07-source/{entry['dir']}",
                "implementation_stage": "UNKNOWN",
                "status": "NO_DATA",  # missing != zero
                "coverage": entry["coverage"],
                "update_cadence": entry["update_cadence"],
                "sla_days": entry["sla_days"],
                "last_snapshot_at": None,
                "freshness_days": None,
                "conformed_keys": {"entity_id": None, "territory_id": None,
                                   "sector_id": None, "period_id": None},
                "exports": [],
                "signal_count": None,
            })
            continue

        keys = {}
        for key, block_name in [("entity_id", "entity_hub"), ("territory_id", "territory"),
                                ("sector_id", "sector"), ("period_id", "temporal_evidence")]:
            block = manifest.get(block_name)
            status = norm_key_status((block or {}).get("current_status"))
            keys[key] = status if status else infer_from_materialization(block)
        stage = manifest.get("implementation_stage", "")
        # Cuando un radar publica su tasa de resolución medida, esa cifra manda
        # sobre la etapa cualitativa del manifiesto: es un hecho, no una etiqueta.
        measured = (manifest.get("territory") or {}).get("measured") or {}
        sources.append({
            "territory_resolution_pct": measured.get("row_resolution_pct"),
            "territory_granularity": (manifest.get("territory") or {}).get("granularity"),
            "source_id": entry["source_id"],
            "radar_id": manifest.get("radar_id"),
            "label": entry["label"],
            "repository": manifest.get("repository", f"smoralesm07-source/{entry['dir']}"),
            "implementation_stage": stage,
            "status": status_from_stage(stage, keys),
            "coverage": entry["coverage"],
            "update_cadence": entry["update_cadence"],
            "sla_days": entry["sla_days"],
            # La frescura real exige leer fusion_interop_status_v1.json de la rama
            # de datos de cada radar. Hasta entonces: NO_DATA, nunca 0.
            "last_snapshot_at": None,
            "freshness_days": None,
            "conformed_keys": keys,
            "exports": [e.get("path", "") for e in (manifest.get("exports") or [])],
            "signal_count": None,
        })
    return sources, missing


def pct(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def coverage_metric(sources: list[dict], key: str) -> float | None:
    """Cobertura conformada de una clave: NOT_PRIMARY no cuenta ni a favor ni en contra."""
    scored = [KEY_WEIGHT[s["conformed_keys"].get(key)] for s in sources]
    applicable = [v for v in scored if v is not None]
    return pct(sum(applicable), len(applicable)) if applicable else None


def status_for(metric_id: str, value: float | None, catalog: dict) -> str:
    """Aplica los umbrales del catálogo. Sin valor -> NO_DATA."""
    if value is None:
        return "NO_DATA"
    meta = next((m for m in catalog["metrics"] if m["metric_id"] == metric_id), None)
    thresholds = (meta or {}).get("thresholds") or {}

    def meets(expr: str) -> bool:
        try:
            op, num = expr.split(" ", 1) if " " in expr else (expr[:2].strip(), expr[2:])
            num = float(num)
        except (ValueError, AttributeError):
            return False
        return {"<=": value <= num, ">=": value >= num, "<": value < num,
                ">": value > num, "=": value == num}.get(op.strip(), False)

    if "ok" in thresholds and meets(thresholds["ok"]):
        return "OK"
    if "warn" in thresholds and meets(thresholds["warn"]):
        return "WARN"
    return "CRIT" if ("ok" in thresholds or "warn" in thresholds) else "OK"


def build_program_health(sources: list[dict], cases: list[dict], catalog: dict,
                         as_of: date) -> list[dict]:
    """Métricas de familia KPI_PROGRAMA. Derivadas donde se puede, NO_DATA donde no.

    `as_of` es la fecha de referencia del corte. Para datos reales es hoy; para la
    sobrecapa demostrativa es el cierre de su propio período, de modo que la
    antigüedad de cola no crezca sin sentido con el paso del tiempo.
    """
    today = as_of
    metrics: list[dict] = []

    by_id = {m["metric_id"]: m for m in catalog["metrics"]}

    def add(metric_id, value, unit, scope="GLOBAL", target=None, trend=None):
        meta = by_id.get(metric_id, {})
        metrics.append({
            "metric_id": metric_id,
            # El nombre y el guardrail viajan desde el catálogo: la interfaz no
            # inventa etiquetas ni reformatea identificadores.
            "name": meta.get("name", metric_id),
            "family": meta.get("family"),
            "guardrail": meta.get("guardrail"),
            "scope": scope, "value": value, "unit": unit,
            "target": target, "status": status_for(metric_id, value, catalog),
            "trend": trend or [],
        })

    # --- Derivadas de los interop reales ---
    add("PRG_IDENTITY_RESOLUTION", coverage_metric(sources, "entity_id"), "%", target=90)
    add("PRG_TERRITORY_COVERAGE", coverage_metric(sources, "territory_id"), "%", target=95)
    add("PRG_SECTOR_COVERAGE", coverage_metric(sources, "sector_id"), "%", target=80)

    # Frescura por fuente: sólo cuando el radar publique su estado de fusión.
    for src in sources:
        add("PRG_FRESHNESS_DAYS", src["freshness_days"], "días",
            scope=src["source_id"], target=src["sla_days"])

    # --- Derivadas del estado de casos ---
    open_states = {"DETECTADO", "EN_REVISION", "CORROBORADO"}
    open_cases = [c for c in cases if c.get("state") in open_states]
    closed = [c for c in cases if c.get("disposed_at")]

    add("PRG_QUEUE_BACKLOG", float(len(open_cases)), "casos")

    if open_cases:
        ages = sorted((today - date.fromisoformat(c["opened_at"])).days for c in open_cases)
        idx = min(int(round(0.9 * (len(ages) - 1))), len(ages) - 1)
        add("PRG_QUEUE_AGING", float(ages[idx]), "días")
    else:
        add("PRG_QUEUE_AGING", None, "días")

    if closed:
        spans = sorted((date.fromisoformat(c["disposed_at"]) -
                        date.fromisoformat(c["opened_at"])).days for c in closed)
        mid = len(spans) // 2
        median = spans[mid] if len(spans) % 2 else (spans[mid - 1] + spans[mid]) / 2
        add("PRG_MTTD", float(median), "días")

        on_time = [c for c in closed if c.get("sla_due_at")
                   and date.fromisoformat(c["disposed_at"]) <= date.fromisoformat(c["sla_due_at"])]
        with_sla = [c for c in closed if c.get("sla_due_at")]
        add("PRG_SLA_COMPLIANCE", pct(len(on_time), len(with_sla)), "%", target=90)
    else:
        add("PRG_MTTD", None, "días")
        add("PRG_SLA_COMPLIANCE", None, "%", target=90)

    # Convergencia: entidades con señales de 3 o más fuentes independientes.
    if cases:
        converged = sum(1 for c in cases if len({s["source_id"] for s in c["signals"]}) >= 3)
        add("PRG_SOURCE_CONVERGENCE", pct(converged, len(cases)), "%", target=15)
    else:
        add("PRG_SOURCE_CONVERGENCE", None, "%", target=15)

    # Integridad de evidencia: invariante duro, verificable sobre los casos cargados.
    total_signals = sum(len(c["signals"]) for c in cases)
    with_evidence = sum(1 for c in cases for s in c["signals"] if s.get("evidence_refs"))
    add("PRG_EVIDENCE_INTEGRITY", pct(with_evidence, total_signals), "%", target=100)

    # --- Aún no derivables sin la capa de fusión materializada ---
    for metric_id, unit in [("PRG_SOURCE_AVAILABILITY", "%"), ("PRG_QUARANTINE_BATCHES", "lotes"),
                            ("PRG_SIGNAL_DRIFT", "%"), ("PRG_MUTE_RULES", "reglas")]:
        add(metric_id, None, unit)

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensambla cockpit_contract_v1.json")
    parser.add_argument("--repos-root", type=Path, default=ROOT.parent,
                        help="Directorio que contiene los repositorios de los radares")
    parser.add_argument("--validate", action="store_true",
                        help="Valida la salida contra el esquema (requiere jsonschema)")
    parser.add_argument("--as-of", type=str, default=None,
                        help="Fecha de referencia del corte (YYYY-MM-DD). Por defecto: hoy, "
                             "o el cierre declarado por la sobrecapa demostrativa")
    args = parser.parse_args()

    config = json.loads((TOOLS / "source_config.json").read_text(encoding="utf-8"))
    overlay = json.loads((TOOLS / "demo_overlay.json").read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    print(f"Leyendo radares desde {args.repos_root}")
    sources, missing = build_sources(args.repos_root, config)
    real = len(sources) - len(missing)
    print(f"  interop real: {real}/{len(sources)} fuentes")
    for name in missing:
        print(f"  - {name}: sin manifiesto, marcado NO_DATA")

    # Secciones que ya tienen fuente real: se prefieren sobre la sobrecapa.
    real = uaf_real.build(args.repos_root)
    provenance = {k: "DEMO_SYNTHETIC" for k in
                  ["cases", "anomalies", "territory", "sectors", "benchmark", "rules",
                   "sanctions", "network"]}
    if real:
        p = real["provenance"]
        print(f"  UAF real: {p['registry_entities']:,} sujetos obligados inscritos, "
              f"{p['mapped_pct']}% con equivalencia exacta en la taxonomía")
        print(f"  brechas de equivalencia: {len(real['sector_gaps'])} actividades del registro")
        provenance["sectors"] = "REAL"
        provenance["benchmark"] = "REAL"
    else:
        print("  UAF real: no disponible (falta pyarrow o los parquet); se usa la sobrecapa")

    cases = overlay["cases"]
    # La sobrecapa demostrativa es un corte de un período pasado: se mide contra su
    # propio cierre. Los datos reales de la capa de fusión se miden contra hoy.
    as_of = date.fromisoformat(overlay["_as_of"]) if overlay.get("_as_of") else date.today()
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
    print(f"  fecha de referencia del corte: {as_of.isoformat()}")

    contract = {
        "contract_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "tools/build_cockpit_data.py",
        "period_id": overlay.get("_period_id", "2024"),
        "sources": sources,
        "program_health": build_program_health(sources, cases, catalog, as_of),
        "cases": cases,
        "anomalies": overlay["anomalies"],
        "territory": overlay["territory"],
        "sectors": real["sectors"] if real else overlay["sectors"],
        "benchmark": real["benchmark"] if real else overlay["benchmark"],
        "sector_gaps": real["sector_gaps"] if real else [],
        "provenance": provenance,
        "rules": overlay["rules"],
        "sanctions": overlay["sanctions"],
        "network": overlay["network"],
        "guardrails": overlay["guardrails"],
    }
    # `signal_series` es material de apoyo para gráficos, fuera del esquema estricto.
    contract["signal_series"] = overlay["signal_series"]

    if args.validate:
        try:
            import jsonschema
        except ImportError:
            print("  ! jsonschema no instalado; se omite la validación", file=sys.stderr)
        else:
            schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
            strict = {k: v for k, v in contract.items() if k != "signal_series"}
            jsonschema.validate(strict, schema)
            print("  validación contra el esquema: OK")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {OUT.relative_to(ROOT)} "
          f"({len(contract['program_health'])} métricas, {len(cases)} casos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
