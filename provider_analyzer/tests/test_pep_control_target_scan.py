from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILTER = ROOT / "provider_analyzer/scripts/filter_pep_control_target_month.py"
MERGE = ROOT / "provider_analyzer/scripts/merge_pep_control_target_scan.py"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_exact_rut_filter_and_merge(tmp_path: Path) -> None:
    targets = tmp_path / "targets.json"
    write_json(targets, {
        "source_observation_id": "DIP-REAL-001",
        "targets": [
            {"rut": "76013464-3", "entity_id": "ENT-RUT-76013464-3", "name": "TARGET", "relationship": "DECLARED_CONTROLLER_CANDIDATE", "beneficial_owner_confirmed": False},
            {"rut": "76114976-8", "entity_id": "ENT-RUT-76114976-8", "name": "NO MATCH", "relationship": "DECLARED_CONTROLLER_CANDIDATE", "beneficial_owner_confirmed": False},
        ],
    })
    history = tmp_path / "history.json"
    write_json(history, {
        "year": 2026,
        "month": 1,
        "source_url": "https://example.invalid/2026-1.zip",
        "coverage": {"source_month_fully_scanned": True},
        "pairs": [
            {"pair_id": "76013464-3::61111111-1", "supplier_id": "76013464-3", "buyer_id": "61111111-1", "order_count": 2, "amount_total_clp": 1500, "buyer_amount_total_clp": 3000, "buyer_share_month": 0.5, "modalities": ["Licitación"], "first_seen": "2026-01-10", "last_seen": "2026-01-20", "year": 2026, "month": 1},
            {"pair_id": "79999999-9::61111111-1", "supplier_id": "79999999-9", "buyer_id": "61111111-1", "order_count": 9, "amount_total_clp": 9999, "year": 2026, "month": 1},
        ],
    })
    events = tmp_path / "events.jsonl.gz"
    with gzip.open(events, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"supplier_id": "76013464-3", "buyer_id": "61111111-1", "pair_id": "76013464-3::61111111-1", "date": "2026-01-10", "order_id": "OC1", "tender_id": "T1", "process_id": "T1", "modality": "Licitación", "product_key": "CODE:1", "source": "MERCADO_PUBLICO_BULK_ORDERS"}) + "\n")
        fh.write(json.dumps({"supplier_id": "79999999-9", "buyer_id": "61111111-1", "order_id": "OTHER"}) + "\n")

    month_out = tmp_path / "months/a/pep_control_month.json"
    subprocess.run([sys.executable, str(FILTER), "--history", str(history), "--purchase-events", str(events), "--targets", str(targets), "--output", str(month_out)], check=True)
    month = json.loads(month_out.read_text(encoding="utf-8"))
    assert month["matched_pair_count"] == 1
    assert month["matched_purchase_event_count"] == 1
    assert month["pairs"][0]["supplier_id"] == "76013464-3"
    assert month["scoring_eligible"] is False

    merged_out = tmp_path / "merged.json"
    subprocess.run([sys.executable, str(MERGE), "--input-root", str(tmp_path / "months"), "--targets", str(targets), "--expected-months", "2026-1", "--output", str(merged_out)], check=True)
    merged = json.loads(merged_out.read_text(encoding="utf-8"))
    assert merged["coverage_complete"] is True
    assert merged["matched_targets"] == 1
    assert merged["targets"]["76013464-3"]["status"] == "MATCH_FOUND"
    assert merged["targets"]["76013464-3"]["amount_total_clp_sum"] == 1500
    assert merged["targets"]["76114976-8"]["status"] == "NO_MATCH_IN_LOADED_DATASET"
    assert merged["targets"]["76114976-8"]["signal_code"] is None
