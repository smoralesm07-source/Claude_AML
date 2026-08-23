#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Filter one governed ChileCompra order month to PEP/control company targets by exact RUT.")
    ap.add_argument("--history", type=Path, required=True)
    ap.add_argument("--purchase-events", type=Path, required=True)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    history = load_json(args.history)
    target_doc = load_json(args.targets)
    targets = {str(x["rut"]): x for x in target_doc.get("targets", []) if x.get("rut")}
    pairs = []
    for row in history.get("pairs", []):
        sid = str(row.get("supplier_id") or "")
        if sid not in targets:
            continue
        target = targets[sid]
        pairs.append({
            "entity_id": target.get("entity_id"),
            "target_name": target.get("name"),
            "supplier_id": sid,
            "buyer_id": row.get("buyer_id"),
            "pair_id": row.get("pair_id"),
            "order_count": row.get("order_count", 0),
            "amount_total_clp": row.get("amount_total_clp", 0),
            "buyer_amount_total_clp": row.get("buyer_amount_total_clp", 0),
            "buyer_share_month": row.get("buyer_share_month"),
            "modalities": row.get("modalities") or [],
            "first_seen": row.get("first_seen"),
            "last_seen": row.get("last_seen"),
            "year": row.get("year"),
            "month": row.get("month"),
        })

    events = []
    with gzip.open(args.purchase_events, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = str(row.get("supplier_id") or "")
            if sid not in targets:
                continue
            target = targets[sid]
            events.append({
                "entity_id": target.get("entity_id"),
                "target_name": target.get("name"),
                "supplier_id": sid,
                "buyer_id": row.get("buyer_id"),
                "pair_id": row.get("pair_id"),
                "date": row.get("date"),
                "order_id": row.get("order_id"),
                "tender_id": row.get("tender_id"),
                "process_id": row.get("process_id"),
                "modality": row.get("modality"),
                "product_key": row.get("product_key"),
                "source": row.get("source"),
            })

    coverage = history.get("coverage") or {}
    out = {
        "schema": "PEP_CONTROL_PROCUREMENT_MONTH_V1",
        "year": history.get("year"),
        "month": history.get("month"),
        "source_url": history.get("source_url"),
        "source_month_fully_scanned": coverage.get("source_month_fully_scanned") is True,
        "match_method": "EXACT_NORMALIZED_SUPPLIER_RUT",
        "target_count": len(targets),
        "matched_pair_count": len(pairs),
        "matched_purchase_event_count": len(events),
        "pairs": pairs,
        "purchase_events": events,
        "semantics": "CONTEXT_ONLY",
        "signal_code": "PEP-05",
        "scoring_eligible": false if False else False,
        "risk_effect": "NONE",
        "guardrails": [
            "PEP_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL",
            "DECLARED_CONTROLLER_IS_NOT_AUTOMATICALLY_AML_BENEFICIAL_OWNER",
            "PURCHASE_ORDER_IS_COMMITMENT_NOT_PROOF_OF_PAYMENT",
            "NO_MATCH_IN_LOADED_DATASET_IS_NOT_EQUIVALENT_TO_NO_PUBLIC_PROCUREMENT",
            "NO_NAME_MATCHING"
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"year": out["year"], "month": out["month"], "pairs": len(pairs), "events": len(events)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
