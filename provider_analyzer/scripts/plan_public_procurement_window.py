#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from intelligence_fusion.public_integrity_calendar import monthly_window


def build_plan(year: int | None = None, month: int | None = None) -> dict:
    target = monthly_window(year=year, month=month, months=1, route_months=7)
    start = 2024 * 12
    end = target['year'] * 12 + (target['month'] - 1)
    if end < start:
        raise ValueError('El analizador comienza en enero de 2024')
    months = []
    for serial in range(start, end + 1):
        yy, mm = serial // 12, serial % 12 + 1
        months.append({'year': yy, 'month': mm, 'period': f'{yy:04d}-{mm:02d}'})
    route_n = min(7, len(months))
    return {
        'window_start': '2024-01',
        'period': target['period'],
        'as_of': target['as_of'],
        'expected_months': len(months),
        'route_months': route_n,
        'month_matrix': {'include': months},
        'history_matrix': {'include': months[:-route_n]},
        'route_matrix': {'include': months[-route_n:]},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int)
    ap.add_argument('--month', type=int)
    ap.add_argument('--output', type=Path)
    ap.add_argument('--github-output', action='store_true')
    args = ap.parse_args()
    plan = build_plan(args.year, args.month)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.github_output:
        target = os.environ.get('GITHUB_OUTPUT')
        if not target:
            raise SystemExit('GITHUB_OUTPUT unavailable')
        scalar = ('period', 'as_of', 'expected_months', 'route_months')
        with open(target, 'a', encoding='utf-8') as fh:
            for key in scalar:
                fh.write(f'{key}={plan[key]}\n')
            for key in ('month_matrix', 'history_matrix', 'route_matrix'):
                fh.write(f'{key}={json.dumps(plan[key], separators=(",", ":"))}\n')
    print(json.dumps({k: plan[k] for k in ('window_start','period','expected_months','route_months')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
