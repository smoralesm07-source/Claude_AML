#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser(description='Derive compact provider-buyer targets from recent Public Integrity signals.')
    ap.add_argument('--signals', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()

    pairs: set[str] = set()
    buyers: set[str] = set()
    suppliers: set[str] = set()
    tender_ids: set[str] = set()
    signal_types: set[str] = set()
    rows = 0
    for s in iter_jsonl(args.signals):
        rows += 1
        pair = str(s.get('provider_buyer_pair_id') or s.get('pair_id') or '').strip()
        buyer = str(s.get('buyer_id') or '').strip()
        supplier = str(s.get('supplier_id') or '').strip()
        tender = str(s.get('tender_id') or '').strip()
        signal_type = str(s.get('signal_type') or '').strip()
        if pair:
            pairs.add(pair)
            if not buyer and '::' in pair:
                buyer = pair.rsplit('::', 1)[1].strip()
            if not supplier and '::' in pair:
                supplier = pair.split('::', 1)[0].strip()
        if buyer: buyers.add(buyer)
        if supplier: suppliers.add(supplier)
        if tender: tender_ids.add(tender)
        if signal_type: signal_types.add(signal_type)

    out = {
        'schema': 'PUBLIC_INTEGRITY_TARGETS_V1',
        'mode': 'SHADOW',
        'counts': {
            'signals': rows,
            'provider_buyer_pairs': len(pairs),
            'buyers': len(buyers),
            'suppliers': len(suppliers),
            'tenders': len(tender_ids),
        },
        'pair_ids': sorted(pairs),
        'buyer_ids': sorted(buyers),
        'supplier_ids': sorted(suppliers),
        'tender_ids': sorted(tender_ids),
        'signal_types': sorted(signal_types),
        'guardrails': {
            'targets_come_only_from_current_signal_universe': True,
            'target_membership_is_not_wrongdoing_probability': True,
            'public_integrity_modifies_aml_score': False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(out['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
