from __future__ import annotations

import pytest

from intelligence_fusion.public_procurement_competition import detect_competition


def test_line_level_award_signals_have_unique_stable_ids():
    tender = {
        'tender_id': '1000-1-LE26',
        'buyer': {'id': '69123456-7', 'name': 'Comprador de prueba'},
        'bids': [
            {
                'supplier_id': '76111111-1',
                'items': [
                    {'item_id': '1', 'unit_price': 300, 'product_code': 'A', 'unit': 'UN'},
                    {'item_id': '2', 'unit_price': 350, 'product_code': 'B', 'unit': 'UN'},
                ],
            },
            {
                'supplier_id': '76222222-2',
                'items': [
                    {'item_id': '1', 'unit_price': 100, 'product_code': 'A', 'unit': 'UN'},
                    {'item_id': '2', 'unit_price': 110, 'product_code': 'B', 'unit': 'UN'},
                ],
            },
            {
                'supplier_id': '76333333-3',
                'items': [
                    {'item_id': '1', 'unit_price': 110, 'product_code': 'A', 'unit': 'UN'},
                    {'item_id': '2', 'unit_price': 120, 'product_code': 'B', 'unit': 'UN'},
                ],
            },
        ],
        'awards': [
            {'status': 'active', 'suppliers': [{'id': '76111111-1'}]},
        ],
    }

    first = [x for x in detect_competition([tender]) if x['signal_type'] == 'INT-PB-005']
    second = [x for x in detect_competition([tender]) if x['signal_type'] == 'INT-PB-005']

    assert len(first) == 2
    assert {x['metrics']['item_id'] for x in first} == {'1', '2'}
    assert len({x['signal_id'] for x in first}) == 2
    assert [x['signal_id'] for x in first] == [x['signal_id'] for x in second]
    assert all(x['scoring_eligible'] is False and x['risk_effect'] == 'NONE' for x in first)


def test_duplicate_signal_ids_fail_before_any_database_write():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / 'scripts' / 'persist_provider_base_signals.py'
    spec = importlib.util.spec_from_file_location('persist_provider_base_signals_unique', script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    signal = {
        'signal_id': 'SIG-DUP',
        'signal_type': 'INT-PB-005',
        'supplier_id': '76111111-1',
        'buyer_id': '69123456-7',
        'provider_buyer_pair_id': '76111111-1::69123456-7',
        'metrics': {'item_id': '1'},
    }
    with pytest.raises(ValueError, match='DUPLICATE_SIGNAL_ID:SIG-DUP'):
        module.build_base_signal_rows(
            [signal, {**signal, 'metrics': {'item_id': '2'}}],
            {'review_cases': []},
            '2026-07',
            run_id='1',
            updated_at='2026-08-24T00:00:00Z',
        )
