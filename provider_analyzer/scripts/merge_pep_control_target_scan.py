#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge monthly exact-RUT PEP/control procurement scans.")
    ap.add_argument("--input-root", type=Path, required=True)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--expected-months", required=True, help="Comma-separated YYYY-M values")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    target_doc = json.loads(args.targets.read_text(encoding="utf-8"))
    targets = {str(x["rut"]): x for x in target_doc.get("targets", []) if x.get("rut")}
    expected = [x.strip() for x in args.expected_months.split(",") if x.strip()]
    loaded: list[str] = []
    incomplete: list[str] = []
    all_pairs: list[dict] = []
    all_events: list[dict] = []

    for path in sorted(args.input_root.rglob("pep_control_month.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        period = f"{doc.get('year')}-{doc.get('month')}"
        loaded.append(period)
        if doc.get("source_month_fully_scanned") is not True:
            incomplete.append(period)
        all_pairs.extend(doc.get("pairs") or [])
        all_events.extend(doc.get("purchase_events") or [])

    by_target: dict[str, dict] = {}
    for rut, target in targets.items():
        rows = [x for x in all_pairs if str(x.get("supplier_id") or "") == rut]
        events = [x for x in all_events if str(x.get("supplier_id") or "") == rut]
        buyer_ids = sorted({str(x.get("buyer_id")) for x in rows if x.get("buyer_id")})
        order_ids = sorted({str(x.get("order_id")) for x in events if x.get("order_id")})
        tender_ids = sorted({str(x.get("tender_id")) for x in events if x.get("tender_id")})
        by_target[rut] = {
            "entity_id": target.get("entity_id"),
            "name": target.get("name"),
            "relationship": target.get("relationship"),
            "beneficial_owner_confirmed": target.get("beneficial_owner_confirmed") is True,
            "status": "MATCH_FOUND" if rows or events else "NO_MATCH_IN_LOADED_DATASET",
            "pair_month_rows": len(rows),
            "purchase_event_rows": len(events),
            "order_count_sum": sum(int(x.get("order_count") or 0) for x in rows),
            "amount_total_clp_sum": round(sum(float(x.get("amount_total_clp") or 0) for x in rows), 2),
            "buyers": buyer_ids,
            "order_ids": order_ids,
            "tender_ids": tender_ids,
            "first_seen": min([x.get("first_seen") for x in rows if x.get("first_seen")], default=None),
            "last_seen": max([x.get("last_seen") for x in rows if x.get("last_seen")], default=None),
            "signal_code": "PEP-05" if rows or events else None,
            "semantics": "CONTEXT_ONLY",
            "scoring_eligible": False,
            "risk_effect": "NONE",
        }

    missing = sorted(set(expected) - set(loaded))
    coverage_complete = not missing and not incomplete and set(loaded) == set(expected)
    output = {
        "schema": "PEP_CONTROL_PROCUREMENT_SCAN_V1",
        "source_observation_id": target_doc.get("source_observation_id"),
        "expected_months": expected,
        "loaded_months": sorted(set(loaded)),
        "missing_months": missing,
        "incomplete_months": sorted(set(incomplete)),
        "coverage_complete": coverage_complete,
        "match_method": "EXACT_NORMALIZED_SUPPLIER_RUT",
        "targets": by_target,
        "matched_targets": sum(1 for x in by_target.values() if x["status"] == "MATCH_FOUND"),
        "semantics": "CONTEXT_ONLY",
        "guardrails": [
            "PEP_STATUS_IS_CONTEXT_NOT_ADVERSE_SIGNAL",
            "DECLARED_CONTROLLER_IS_NOT_AUTOMATICALLY_AML_BENEFICIAL_OWNER",
            "PURCHASE_ORDER_IS_COMMITMENT_NOT_PROOF_OF_PAYMENT",
            "NO_MATCH_IN_LOADED_DATASET_IS_NOT_EQUIVALENT_TO_NO_PUBLIC_PROCUREMENT",
            "NO_NAME_MATCHING"
        ]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"coverage_complete": coverage_complete, "matched_targets": output["matched_targets"], "missing_months": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
