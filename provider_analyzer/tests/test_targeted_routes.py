from __future__ import annotations

from intelligence_fusion.targeted_routes import (
    collect_targeted_route_events,
    month_serial,
    route_document,
)


def test_targeted_routes_filter_window_dedupe_and_find_route():
    buyers = {'69123456-7'}
    start = month_serial(2026, 1)
    end = month_serial(2026, 7)
    rows = [
        {
            'buyer_id': '69123456-7',
            'product_key': 'CODE:44103103',
            'date': '2026-02-10',
            'status': 'NOT_AWARDED',
            'tender_id': '1000-1-LE26',
            'process_id': '1000-1-LE26',
            'modality': 'LE',
            'line': '1',
            'source': 'MERCADO_PUBLICO_BULK_TENDERS',
        },
        {
            'buyer_id': '69123456-7',
            'supplier_id': '76123456-8',
            'pair_id': '76123456-8::69123456-7',
            'product_key': 'CODE:44103103',
            'date': '2026-03-03',
            'status': 'PURCHASED',
            'process_id': '2000-5-SE26',
            'order_id': '2000-5-SE26',
            'modality': 'SE',
            'source': 'MERCADO_PUBLICO_BULK_ORDERS',
        },
        # Exact duplicate must not inflate evidence.
        {
            'buyer_id': '69123456-7',
            'supplier_id': '76123456-8',
            'pair_id': '76123456-8::69123456-7',
            'product_key': 'CODE:44103103',
            'date': '2026-03-03',
            'status': 'PURCHASED',
            'process_id': '2000-5-SE26',
            'order_id': '2000-5-SE26',
            'modality': 'SE',
            'source': 'MERCADO_PUBLICO_BULK_ORDERS',
        },
        # Different buyer: not part of the targeted case universe.
        {
            'buyer_id': '69999999-9',
            'product_key': 'CODE:44103103',
            'date': '2026-02-11',
            'status': 'DESERTED',
            'process_id': '999-1-LE26',
        },
        # Correct buyer, but outside the validated lifecycle window.
        {
            'buyer_id': '69123456-7',
            'product_key': 'CODE:44103103',
            'date': '2025-12-31',
            'status': 'DESERTED',
            'process_id': '998-1-LE25',
        },
        # Invalid purchase order identifier must not enter route evidence.
        {
            'buyer_id': '69123456-7',
            'supplier_id': '76123456-8',
            'product_key': 'CODE:44103103',
            'date': '2026-04-01',
            'status': 'PURCHASED',
            'process_id': 'bad order id',
            'order_id': 'bad order id',
        },
    ]

    selected, stats = collect_targeted_route_events(
        rows,
        target_buyers=buyers,
        start_serial=start,
        end_serial=end,
    )
    events = list(selected.values())

    assert len(events) == 2
    assert stats['DUPLICATE_EVENT'] == 1
    assert stats['NON_TARGET_BUYER'] == 1
    assert stats['OUTSIDE_EVENT_WINDOW'] == 1
    assert stats['INVALID_ORDER_ID'] == 1
    assert all('payload' not in row for row in events)

    doc = route_document(
        events,
        expected_months=31,
        scanned_periods=[f'2024-{m:02d}' for m in range(1, 13)]
        + [f'2025-{m:02d}' for m in range(1, 13)]
        + [f'2026-{m:02d}' for m in range(1, 8)],
        target_buyers=1,
        source_details={},
        validation_stats=dict(stats),
        days=180,
    )
    assert doc['coverage']['coverage_complete'] is True
    assert doc['coverage']['storage_semantics'] == 'EPHEMERAL_TARGETED_SOURCE_WINDOW'
    assert doc['guardrails']['raw_route_dataset_persisted'] is False
    assert len(doc['findings']) == 1
    finding = doc['findings'][0]
    assert finding['pair_id'] == '76123456-8::69123456-7'
    assert finding['origin_process_id'] == '1000-1-LE26'
    assert finding['later_process_id'] == '2000-5-SE26'
    assert finding['scoring_eligible'] is False
    assert finding['risk_effect'] == 'NONE'
