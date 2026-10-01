#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

MONTH_BUILDER = Path(__file__).with_name('build_chilecompra_order_month_summary.py')
BASE_URL = 'https://transparenciachc.blob.core.windows.net/oc-da'


def dec(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, '') else 0))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'INVALID_DECIMAL:{value!r}') from exc


def json_number(value: Decimal):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def iso_min(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return min(a, b)


def iso_max(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return max(a, b)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--start-month', type=int, default=1)
    ap.add_argument('--end-month', type=int, default=12)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()

    if args.year < 2007:
        raise SystemExit('year must be >= 2007')
    if not (1 <= args.start_month <= args.end_month <= 12):
        raise SystemExit('invalid month range')

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pair_agg: dict[tuple[str, str], dict] = {}
    supplier_months: dict[str, set[int]] = defaultdict(set)
    coverage_rows: list[dict] = []
    generated_at = datetime.now(timezone.utc).isoformat()

    with tempfile.TemporaryDirectory(prefix=f'chilecompra-{args.year}-') as tmp_raw:
        tmp = Path(tmp_raw)
        for month in range(args.start_month, args.end_month + 1):
            month_out = tmp / f'{month:02d}'
            url = f'{BASE_URL}/{args.year}-{month}.zip'
            cmd = [
                sys.executable,
                str(MONTH_BUILDER),
                '--url', url,
                '--year', str(args.year),
                '--month', str(month),
                '--output-dir', str(month_out),
            ]
            print(f'[year {args.year}] scanning month {month:02d}', flush=True)
            subprocess.run(cmd, check=True)

            hist = json.loads((month_out / 'history_month.json').read_text(encoding='utf-8'))
            cov = hist.get('coverage') or {}
            coverage_rows.append({
                'source': 'CHILECOMPRA_OC_DA',
                'year': args.year,
                'month': month,
                'rows_read': int(cov.get('rows_read') or 0),
                'orders': int(cov.get('orders') or 0),
                'identity_coverage': cov.get('identity_coverage'),
                'amount_coverage': cov.get('clp_amount_coverage'),
                'detail': cov,
                'loaded_at': generated_at,
            })

            for row in hist.get('pairs') or []:
                supplier = str(row.get('supplier_id') or '').strip()
                buyer = str(row.get('buyer_id') or '').strip()
                if not supplier or not buyer:
                    continue
                key = (supplier, buyer)
                cur = pair_agg.setdefault(key, {
                    'supplier_id': supplier,
                    'buyer_id': buyer,
                    'amount': Decimal(0),
                    'orders': 0,
                    'months': set(),
                    'first_seen': None,
                    'last_seen': None,
                })
                cur['amount'] += dec(row.get('amount_total_clp'))
                cur['orders'] += int(row.get('order_count') or 0)
                cur['months'].add(month)
                cur['first_seen'] = iso_min(cur['first_seen'], row.get('first_seen'))
                cur['last_seen'] = iso_max(cur['last_seen'], row.get('last_seen'))
                supplier_months[supplier].add(month)

    by_supplier: dict[str, list[dict]] = defaultdict(list)
    for row in pair_agg.values():
        by_supplier[row['supplier_id']].append(row)

    out_path = args.output_dir / f'supplier_year_{args.year}.jsonl.gz'
    supplier_rows = 0
    total_orders = 0
    total_amount = Decimal(0)
    with gzip.open(out_path, 'wt', encoding='utf-8') as fh:
        for supplier in sorted(by_supplier):
            pairs = sorted(
                by_supplier[supplier],
                key=lambda r: (-r['amount'], r['buyer_id']),
            )
            amount = sum((r['amount'] for r in pairs), Decimal(0))
            orders = sum(r['orders'] for r in pairs)
            first_seen = None
            last_seen = None
            for r in pairs:
                first_seen = iso_min(first_seen, r['first_seen'])
                last_seen = iso_max(last_seen, r['last_seen'])
            row = {
                'year': args.year,
                'supplier_id': supplier,
                'amount_total_clp': json_number(amount),
                'order_count': orders,
                'buyer_count': len(pairs),
                'active_months': len(supplier_months[supplier]),
                'first_seen': first_seen,
                'last_seen': last_seen,
                # Compact contract: [buyer_id, amount_clp, order_count].
                'buyers': [
                    [r['buyer_id'], json_number(r['amount']), r['orders']]
                    for r in pairs
                ],
            }
            fh.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
            supplier_rows += 1
            total_orders += orders
            total_amount += amount

    coverage_path = args.output_dir / f'coverage_{args.year}.json'
    coverage_path.write_text(
        json.dumps(coverage_rows, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8',
    )
    meta = {
        'schema': 'PROVIDER_ENTITY_HISTORY_YEAR_V1',
        'year': args.year,
        'start_month': args.start_month,
        'end_month': args.end_month,
        'generated_at': generated_at,
        'supplier_rows': supplier_rows,
        'supplier_buyer_pairs': len(pair_agg),
        'orders': total_orders,
        'amount_total_clp': str(total_amount),
        'storage_semantics': 'SUPPLIER_YEAR_PACKED_V1',
        'buyer_tuple': ['buyer_id', 'amount_clp', 'order_count'],
        'source': 'CHILECOMPRA_OC_DA',
    }
    (args.output_dir / f'meta_{args.year}.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(json.dumps(meta, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
