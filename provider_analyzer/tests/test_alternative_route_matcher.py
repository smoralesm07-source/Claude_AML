from __future__ import annotations

import random
from datetime import date, timedelta

from intelligence_fusion.alternative_route_matcher import detect_alternative_purchase_routes
from intelligence_fusion.sources.common import norm_text


def legacy_reference(events: list[dict], days: int = 180) -> list[dict]:
    """Reference copy of the pre-indexed O(N²) matcher for semantic regression tests."""
    from intelligence_fusion.alternative_route_matcher import _date

    rows = []
    for event in events:
        parsed = _date(event.get('date') or event.get('event_date') or event.get('created_at'))
        if parsed:
            rows.append({**event, '_date': parsed})
    rows.sort(key=lambda row: row['_date'])
    out = []
    seen = set()
    negative = {
        'NOT_AWARDED', 'UNSUCCESSFUL', 'DESERTED', 'CANCELLED',
        'SIN_ADJUDICACION', 'DESIERTA',
    }
    positive = {'AWARDED', 'PURCHASED', 'ORDERED', 'ACTIVE', 'ADJUDICADA', 'COMPRADA'}

    for origin in rows:
        if str(origin.get('status') or '').upper() not in negative:
            continue
        buyer = str(origin.get('buyer_id') or origin.get('buyer_name') or '')
        product = norm_text(
            origin.get('product_key') or origin.get('product_code') or origin.get('description')
        ).lower()
        if not buyer or not product:
            continue
        for later in rows:
            if later['_date'] <= origin['_date']:
                continue
            delta = (later['_date'] - origin['_date']).days
            if delta > days:
                break
            later_buyer = str(later.get('buyer_id') or later.get('buyer_name') or '')
            later_product = norm_text(
                later.get('product_key') or later.get('product_code') or later.get('description')
            ).lower()
            if (
                later_buyer != buyer
                or later_product != product
                or str(later.get('status') or '').upper() not in positive
            ):
                continue
            origin_process = str(origin.get('tender_id') or origin.get('process_id') or '')
            later_process = str(later.get('tender_id') or later.get('process_id') or '')
            if origin_process and later_process and origin_process == later_process:
                continue
            supplier = str(later.get('supplier_id') or later.get('supplier_name') or '')
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
            out.append(
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
    return out


def test_indexed_matcher_matches_legacy_semantics_on_edge_cases():
    events = [
        # Same-day purchase must not match.
        {'buyer_id':'B1','product_key':'CODE:P1','date':'2026-01-10','status':'DESERTED','process_id':'T1','line':'1'},
        {'buyer_id':'B1','supplier_id':'S1','product_key':'CODE:P1','date':'2026-01-10','status':'PURCHASED','process_id':'O-SAME-DAY','order_id':'1000-1-SE26','modality':'SE'},
        # First later event is the same process and must be skipped.
        {'buyer_id':'B1','supplier_id':'S1','product_key':'CODE:P1','date':'2026-01-11','status':'PURCHASED','process_id':'T1','order_id':'1000-2-SE26','modality':'SE'},
        {'buyer_id':'B1','supplier_id':'S2','product_key':'CODE:P1','date':'2026-01-12','status':'PURCHASED','process_id':'O2','order_id':'1000-3-SE26','modality':'SE'},
        # A second negative origin can hit the same dedupe tuple; it must continue to the next candidate.
        {'buyer_id':'B1','product_key':'CODE:P1','date':'2026-01-10','status':'NOT_AWARDED','process_id':'T1','line':'2'},
        {'buyer_id':'B1','supplier_id':'S3','product_key':'CODE:P1','date':'2026-01-13','status':'PURCHASED','process_id':'O3','order_id':'1000-4-SE26','modality':'TD'},
        # Different buyer/product are irrelevant to B1/P1.
        {'buyer_id':'B2','supplier_id':'S9','product_key':'CODE:P1','date':'2026-01-11','status':'PURCHASED','process_id':'X1','order_id':'2000-1-SE26'},
        {'buyer_id':'B1','supplier_id':'S9','product_key':'CODE:P2','date':'2026-01-11','status':'PURCHASED','process_id':'X2','order_id':'2000-2-SE26'},
        # Outside 180-day window.
        {'buyer_id':'B3','product_key':'CODE:P3','date':'2026-01-01','status':'DESERTED','process_id':'T3'},
        {'buyer_id':'B3','supplier_id':'S3','product_key':'CODE:P3','date':'2026-08-01','status':'PURCHASED','process_id':'O8','order_id':'3000-1-SE26'},
        # Invalid date is ignored by both implementations.
        {'buyer_id':'B4','product_key':'CODE:P4','date':'not-a-date','status':'DESERTED','process_id':'T4'},
    ]
    assert detect_alternative_purchase_routes(events) == legacy_reference(events)


def test_indexed_matcher_matches_legacy_on_seeded_mixed_universe():
    rng = random.Random(913)
    start = date(2026, 1, 1)
    statuses = ['DESERTED', 'NOT_AWARDED', 'PURCHASED', 'AWARDED', 'OPEN']
    events = []
    for index in range(360):
        buyer = f'B{rng.randrange(12):02d}'
        product = f'CODE:P{rng.randrange(9):02d}'
        when = start + timedelta(days=rng.randrange(210))
        status = rng.choice(statuses)
        process = f'PROC-{rng.randrange(70):03d}'
        row = {
            'buyer_id': buyer,
            'product_key': product,
            'date': when.isoformat(),
            'status': status,
            'process_id': process,
            'modality': rng.choice(['LE', 'SE', 'TD', None]),
            'line': str(rng.randrange(1, 5)),
        }
        if status in {'PURCHASED', 'AWARDED'}:
            row['supplier_id'] = f'S{rng.randrange(30):02d}'
            row['order_id'] = f'{1000+rng.randrange(9000)}-{1+rng.randrange(9)}-SE26'
        events.append(row)

    assert detect_alternative_purchase_routes(events) == legacy_reference(events)


def test_indexed_matcher_handles_large_grouped_universe_without_changing_guardrails():
    events = []
    for index in range(5000):
        buyer = f'B{index % 250:03d}'
        product = f'CODE:P{index % 100:03d}'
        base = date(2026, 1, 1) + timedelta(days=index % 120)
        events.append(
            {
                'buyer_id': buyer,
                'product_key': product,
                'date': base.isoformat(),
                'status': 'DESERTED',
                'process_id': f'T-{index}',
            }
        )
        events.append(
            {
                'buyer_id': buyer,
                'supplier_id': f'S{index % 400:03d}',
                'product_key': product,
                'date': (base + timedelta(days=7)).isoformat(),
                'status': 'PURCHASED',
                'process_id': f'O-{index}',
                'order_id': f'{10000+index}-1-SE26',
            }
        )

    findings = detect_alternative_purchase_routes(events)
    assert findings
    assert all(row['scoring_eligible'] is False for row in findings)
    assert all(row['risk_effect'] == 'NONE' for row in findings)
