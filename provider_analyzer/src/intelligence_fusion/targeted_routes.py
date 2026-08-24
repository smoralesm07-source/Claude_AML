from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable

from .alternative_route_matcher import detect_alternative_purchase_routes
from .sources.validation import plausible_event_date, valid_order_id


def month_serial(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def normalize_targeted_route_event(
    raw: dict,
    *,
    target_buyers: set[str],
    start_serial: int,
    end_serial: int,
) -> tuple[dict | None, str]:
    buyer = str(raw.get('buyer_id') or '').strip()
    if buyer not in target_buyers:
        return None, 'NON_TARGET_BUYER'

    event_date = plausible_event_date(raw.get('date') or raw.get('event_date'))
    if not event_date:
        return None, 'INVALID_EVENT_DATE'
    parsed = date.fromisoformat(event_date)
    serial = month_serial(parsed.year, parsed.month)
    if serial < start_serial or serial > end_serial:
        return None, 'OUTSIDE_EVENT_WINDOW'

    product = str(raw.get('product_key') or '').strip()
    status = str(raw.get('status') or '').strip().upper()
    order_id = str(raw.get('order_id') or '').strip()
    if len(buyer) < 3:
        return None, 'INVALID_BUYER_ID'
    if not product:
        return None, 'MISSING_PRODUCT_KEY'
    if not status:
        return None, 'MISSING_STATUS'
    if status == 'PURCHASED' and not valid_order_id(order_id):
        return None, 'INVALID_ORDER_ID'

    process_id = raw.get('process_id') or raw.get('tender_id')
    row = {
        'buyer_id': buyer,
        'supplier_id': raw.get('supplier_id'),
        'pair_id': raw.get('pair_id'),
        'product_key': product,
        'date': event_date,
        'status': status,
        'process_id': process_id,
        'tender_id': raw.get('tender_id') or process_id,
        'order_id': order_id or None,
        'modality': raw.get('modality'),
        'source': raw.get('source') or 'CHILECOMPRA',
        'line': raw.get('line'),
        'evidence': raw.get('evidence'),
        'bidder_count': raw.get('bidder_count'),
    }
    return row, 'SELECTED'


def event_key(row: dict) -> tuple:
    return (
        row.get('date'),
        row.get('buyer_id'),
        row.get('supplier_id'),
        row.get('product_key'),
        row.get('status'),
        row.get('process_id'),
        row.get('order_id'),
        row.get('modality'),
        row.get('line'),
    )


def collect_targeted_route_events(
    rows: Iterable[dict],
    *,
    target_buyers: set[str],
    start_serial: int,
    end_serial: int,
    selected: dict[tuple, dict] | None = None,
    stats: Counter | None = None,
) -> tuple[dict[tuple, dict], Counter]:
    selected = selected if selected is not None else {}
    stats = stats if stats is not None else Counter()
    for raw in rows:
        stats['rows_seen'] += 1
        normalized, reason = normalize_targeted_route_event(
            raw,
            target_buyers=target_buyers,
            start_serial=start_serial,
            end_serial=end_serial,
        )
        stats[reason] += 1
        if normalized is None:
            continue
        key = event_key(normalized)
        if key in selected:
            stats['DUPLICATE_EVENT'] += 1
            continue
        selected[key] = normalized
    return selected, stats


def route_document(
    events: list[dict],
    *,
    expected_months: int,
    scanned_periods: list[str],
    target_buyers: int,
    source_details: dict,
    validation_stats: dict,
    days: int = 180,
) -> dict:
    findings = detect_alternative_purchase_routes(events, days=days)
    complete = len(scanned_periods) == expected_months
    return {
        'schema': 'PROVIDER_ANALYZER_ALTERNATIVE_ROUTES_V1',
        'mode': 'SHADOW',
        'coverage': {
            'expected_months': expected_months,
            'available_months': len(scanned_periods),
            'coverage_complete': complete,
            'scanned_periods': scanned_periods,
            'target_buyers': target_buyers,
            'events': len(events),
            'route_findings': len(findings),
            'source_details': source_details,
            'validation': validation_stats,
            'storage_semantics': 'EPHEMERAL_TARGETED_SOURCE_WINDOW',
            'route_days': days,
            'missing_is_not_zero': True,
        },
        'findings': findings,
        'guardrails': {
            'finding_is_not_wrongdoing_probability': True,
            'same_buyer_and_product_required': True,
            'different_process_required': True,
            'public_integrity_modifies_aml_score': False,
            'raw_route_dataset_persisted': False,
            'targeted_source_window_only': True,
        },
    }
