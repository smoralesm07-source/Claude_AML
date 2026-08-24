from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .sources.common import norm_text

NEGATIVE_ROUTE_STATUSES = {
    'NOT_AWARDED',
    'UNSUCCESSFUL',
    'DESERTED',
    'CANCELLED',
    'SIN_ADJUDICACION',
    'DESIERTA',
}
POSITIVE_ROUTE_STATUSES = {
    'AWARDED',
    'PURCHASED',
    'ORDERED',
    'ACTIVE',
    'ADJUDICADA',
    'COMPRADA',
}


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    for fmt in (None, '%d/%m/%Y', '%d-%m-%Y'):
        try:
            parsed = (
                datetime.fromisoformat(text)
                if fmt is None
                else datetime.strptime(text[:10], fmt)
            )
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            pass
    return None


def _buyer(row: dict) -> str:
    return str(row.get('buyer_id') or row.get('buyer_name') or '')


def _product(row: dict) -> str:
    return norm_text(
        row.get('product_key') or row.get('product_code') or row.get('description')
    ).lower()


def detect_alternative_purchase_routes(events: list[dict], days: int = 180) -> list[dict]:
    """Match negative procurement outcomes to later purchases without an O(N²) scan.

    Semantics intentionally mirror the original detector: strictly later lifecycle date,
    same buyer and normalized product, different process when both process IDs exist,
    first eligible later positive event, and global finding deduplication.
    """
    rows = []
    for input_index, event in enumerate(events):
        event_date = _date(event.get('date') or event.get('event_date') or event.get('created_at'))
        if event_date is None:
            continue
        row = {
            **event,
            '_date': event_date,
            '_input_index': input_index,
            '_route_buyer': _buyer(event),
            '_route_product': _product(event),
            '_route_status': str(event.get('status') or '').upper(),
        }
        rows.append(row)

    # The legacy implementation sorted only by date. Python's sort is stable, so
    # date + input index reproduces its ordering explicitly and deterministically.
    rows.sort(key=lambda row: (row['_date'], row['_input_index']))

    positives: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        buyer = row['_route_buyer']
        product = row['_route_product']
        if (
            buyer
            and product
            and row['_route_status'] in POSITIVE_ROUTE_STATUSES
        ):
            positives[(buyer, product)].append(row)

    positive_dates = {
        key: [row['_date'] for row in group]
        for key, group in positives.items()
    }

    findings = []
    seen = set()
    for origin in rows:
        if origin['_route_status'] not in NEGATIVE_ROUTE_STATUSES:
            continue
        buyer = origin['_route_buyer']
        product = origin['_route_product']
        if not buyer or not product:
            continue

        group_key = (buyer, product)
        candidates = positives.get(group_key) or []
        if not candidates:
            continue

        # Strictly later than the origin date, preserving legacy behavior that
        # never links two lifecycle events occurring on the same date.
        start = bisect_right(positive_dates[group_key], origin['_date'])
        for later in candidates[start:]:
            delta = (later['_date'] - origin['_date']).days
            if delta > days:
                break

            origin_process = str(
                origin.get('tender_id') or origin.get('process_id') or ''
            )
            later_process = str(
                later.get('tender_id') or later.get('process_id') or ''
            )
            if origin_process and later_process and origin_process == later_process:
                continue

            supplier = str(
                later.get('supplier_id') or later.get('supplier_name') or ''
            )
            pair = f'{supplier}::{buyer}' if supplier else None
            dedupe = (
                buyer,
                product,
                origin_process,
                later_process,
                supplier,
                later.get('order_id'),
            )
            if dedupe in seen:
                continue
            seen.add(dedupe)

            origin_modality = str(origin.get('modality') or '')
            later_modality = str(later.get('modality') or '')
            findings.append(
                {
                    'finding_type': 'ALTERNATIVE_PURCHASE_ROUTE',
                    'semantic_class': 'INTEGRITY_REVIEW',
                    'pair_id': pair,
                    'buyer_id': buyer,
                    'product_key': product,
                    'origin_process_id': origin_process or None,
                    'origin_status': origin.get('status'),
                    'origin_modality': origin.get('modality'),
                    'origin_line': origin.get('line'),
                    'origin_evidence': origin.get('evidence'),
                    'later_process_id': later_process or None,
                    'later_order_id': later.get('order_id'),
                    'later_modality': later.get('modality'),
                    'later_supplier_id': supplier or None,
                    'days_after': delta,
                    'modality_changed': bool(
                        origin_modality
                        and later_modality
                        and norm_text(origin_modality).lower()
                        != norm_text(later_modality).lower()
                    ),
                    'review_reason': (
                        'Una línea no adjudicada reaparece como compra/adjudicación '
                        'posterior del mismo comprador y producto.'
                    ),
                    'scoring_eligible': False,
                    'risk_effect': 'NONE',
                }
            )
            break

    return findings
