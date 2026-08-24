#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from intelligence_fusion.targeted_routes import (
    collect_targeted_route_events,
    month_serial,
    route_document,
)


def gz_iter(path: Path):
    with gzip.open(path, 'rt', encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def period_from_serial(serial: int) -> str:
    return f'{serial // 12:04d}-{serial % 12 + 1:02d}'


def run_builder(script: Path, *, url: str, year: int, month: int, output_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(script),
            '--url',
            url,
            '--year',
            str(year),
            '--month',
            str(month),
            '--output-dir',
            str(output_dir),
        ],
        check=True,
    )


def compact_order_health(doc: dict) -> dict:
    c = doc.get('coverage') or {}
    return {
        'rows_read': c.get('rows_read'),
        'orders': c.get('orders'),
        'identity_coverage': c.get('identity_coverage'),
        'clp_amount_coverage': c.get('clp_amount_coverage'),
        'quarantine_rate': c.get('quarantine_rate'),
        'source_month_fully_scanned': c.get('source_month_fully_scanned') is True,
    }


def compact_tender_health(doc: dict) -> dict:
    c = doc.get('coverage') or {}
    return {
        'rows_read': c.get('rows_read'),
        'tenders': c.get('tenders'),
        'negative_events': c.get('negative_events'),
        'skipped_awarded_tenders_without_selected_offer_evidence': c.get(
            'skipped_awarded_tenders_without_selected_offer_evidence'
        ),
        'source_month_fully_scanned': c.get('source_month_fully_scanned') is True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--targets', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--days', type=int, default=180)
    args = ap.parse_args()

    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    targets = json.loads(args.targets.read_text(encoding='utf-8'))
    target_buyers = {str(x).strip() for x in (targets.get('buyer_ids') or []) if str(x).strip()}
    source_months = (plan.get('month_matrix') or {}).get('include') or []
    if not source_months:
        raise RuntimeError('NO_SOURCE_COHORTS_IN_PLAN')

    end_year = int(str(plan['period'])[:4])
    end_month = int(str(plan['period'])[5:7])
    event_end = month_serial(end_year, end_month)
    event_months = int(plan.get('route_months') or 7)
    event_start = event_end - (event_months - 1)

    selected: dict[tuple, dict] = {}
    stats = Counter()
    scanned_periods: list[str] = []
    source_details: dict[str, dict] = {}
    scripts = Path(__file__).resolve().parent
    order_builder = scripts / 'build_chilecompra_order_month_summary.py'
    tender_builder = scripts / 'build_chilecompra_tender_route_month.py'

    with tempfile.TemporaryDirectory(prefix='provider-targeted-routes-') as td:
        root = Path(td)
        for item in source_months:
            year = int(item['year'])
            month = int(item['month'])
            period = f'{year:04d}-{month:02d}'
            month_root = root / 'month'
            if month_root.exists():
                shutil.rmtree(month_root)
            order_dir = month_root / 'orders'
            tender_dir = month_root / 'tenders'

            run_builder(
                order_builder,
                url=f'https://transparenciachc.blob.core.windows.net/oc-da/{year}-{month}.zip',
                year=year,
                month=month,
                output_dir=order_dir,
            )
            run_builder(
                tender_builder,
                url=f'https://transparenciachc.blob.core.windows.net/lic-da/{year}-{month}.zip',
                year=year,
                month=month,
                output_dir=tender_dir,
            )

            order_health = json.loads((order_dir / 'history_month.json').read_text(encoding='utf-8'))
            tender_health = json.loads((tender_dir / 'health.json').read_text(encoding='utf-8'))
            if int(order_health.get('year')) != year or int(order_health.get('month')) != month:
                raise RuntimeError(f'ORDER_PERIOD_MISMATCH:{period}')
            if int(tender_health.get('year')) != year or int(tender_health.get('month')) != month:
                raise RuntimeError(f'TENDER_PERIOD_MISMATCH:{period}')
            oc = compact_order_health(order_health)
            lic = compact_tender_health(tender_health)
            if not oc['source_month_fully_scanned'] or not lic['source_month_fully_scanned']:
                raise RuntimeError(f'INCOMPLETE_SOURCE_COHORT:{period}')

            selected, stats = collect_targeted_route_events(
                gz_iter(order_dir / 'purchase_events.jsonl.gz'),
                target_buyers=target_buyers,
                start_serial=event_start,
                end_serial=event_end,
                selected=selected,
                stats=stats,
            )
            selected, stats = collect_targeted_route_events(
                gz_iter(tender_dir / 'tender_negative_events.jsonl.gz'),
                target_buyers=target_buyers,
                start_serial=event_start,
                end_serial=event_end,
                selected=selected,
                stats=stats,
            )
            scanned_periods.append(period)
            source_details[period] = {'oc': oc, 'lic': lic}
            print(
                json.dumps(
                    {
                        'period': period,
                        'target_buyers': len(target_buyers),
                        'selected_events_total': len(selected),
                    },
                    ensure_ascii=False,
                )
            )

    events = sorted(
        selected.values(),
        key=lambda x: (
            x.get('date') or '',
            x.get('buyer_id') or '',
            x.get('product_key') or '',
            x.get('process_id') or '',
            x.get('order_id') or '',
        ),
    )
    doc = route_document(
        events,
        expected_months=len(source_months),
        scanned_periods=scanned_periods,
        target_buyers=len(target_buyers),
        source_details=source_details,
        validation_stats=dict(stats),
        days=args.days,
    )
    doc['coverage'].update(
        {
            'source_cohort_start': scanned_periods[0],
            'source_cohort_end': scanned_periods[-1],
            'event_window_start': period_from_serial(event_start),
            'event_window_end': period_from_serial(event_end),
            'event_window_months': event_months,
            'source_cohort_semantics': 'CHILECOMPRA_ARCHIVE_MONTH',
            'event_window_semantics': 'VALIDATED_LIFECYCLE_EVENT_DATE',
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        json.dumps(
            {
                'source_cohorts': len(scanned_periods),
                'event_window': [period_from_serial(event_start), period_from_serial(event_end)],
                'target_buyers': len(target_buyers),
                'events': len(events),
                'route_findings': len(doc['findings']),
                'coverage_complete': doc['coverage']['coverage_complete'],
            },
            ensure_ascii=False,
        )
    )


if __name__ == '__main__':
    main()
