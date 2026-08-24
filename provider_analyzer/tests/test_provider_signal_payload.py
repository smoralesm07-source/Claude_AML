from __future__ import annotations

import json

from intelligence_fusion.provider_signal_payload import compact_priority_context, compact_source_context


def compact_json_size(obj: dict) -> int:
    return len(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())


def test_compact_source_context_keeps_review_identifiers_without_metric_duplication():
    signal = {
        'signal_id': 'SIG-1',
        'tender_id': '1000-1-LE26',
        'buyer_name': 'Comprador',
        'scope': 'SUPPLIER_TENDER',
        'evidence_ids': ['E1'],
        'reason': 'Razón que ya existe en la presentación',
        'metrics': {'lines': [{'item_id': str(i), 'ratio': i / 10} for i in range(100)]},
    }
    ctx = compact_source_context(signal)
    assert ctx == {
        'tender_id': '1000-1-LE26',
        'buyer_name': 'Comprador',
        'scope': 'SUPPLIER_TENDER',
        'source_evidence_ids': ['E1'],
    }
    assert 'metrics' not in ctx
    assert 'reason' not in ctx


def test_compact_priority_context_removes_duplicate_history_but_preserves_explainability():
    history = {
        'pair_id': 'S::B',
        'order_count': 17,
        'amount_total_clp': 114304612.24,
        'months_active': [f'2026-{m:02d}' for m in range(1, 8)],
    }
    priority = {
        'review_key': 'S::B',
        'review_priority': 55.2,
        'tier': 'MEDIUM',
        'signal_types': ['INT-PB-002', 'INT-PB-005'],
        'signal_count': 5,
        'comparability_index_median': 100,
        'history': history,
        'history_context': history,
        'history_used_for_priority': True,
        'alternative_route_count': 0,
        'components': {
            'signal_diversity': 20,
            'evidence_comparability': 25,
            'historical_persistence': 6,
            'buyer_concentration': 4.2,
            'alternative_route': 0,
        },
        'guardrail': 'No representa probabilidad de delito.',
        'scoring_eligible': False,
        'risk_effect': 'NONE',
    }
    compact = compact_priority_context(priority)
    assert 'history' not in compact
    assert compact['history_context'] == history
    assert compact['components']['buyer_concentration'] == 4.2
    assert compact['alternative_route_count'] == 0
    assert compact['history_used_for_priority'] is True


def test_compaction_materially_reduces_representative_database_payload():
    signal = {
        'signal_id': 'SIG-1',
        'tender_id': '1000-1-LE26',
        'buyer_name': 'Comprador',
        'evidence_ids': ['E1'],
        'reason': 'Señal de revisión',
        'metrics': {'lines': [{'item_id': str(i), 'ratio': i / 10, 'description': 'x' * 100} for i in range(120)]},
    }
    history = {'months_active': [f'2025-{m:02d}' for m in range(1, 13)], 'order_count': 20}
    priority = {
        'review_key': 'S::B',
        'review_priority': 50,
        'tier': 'MEDIUM',
        'history': history,
        'history_context': history,
        'components': {'alternative_route': 0},
        'history_used_for_priority': True,
    }
    presentation = {
        'signal_id': 'SIG-1',
        'reason': signal['reason'],
        'metrics': signal['metrics'],
        'review_priority': 50,
    }
    old_payload = {**presentation, 'raw_signal': signal, 'priority_context': priority}
    compact_payload = {
        **presentation,
        'source_context': compact_source_context(signal),
        'priority_context': compact_priority_context(priority),
    }
    assert compact_json_size(compact_payload) < compact_json_size(old_payload) * 0.65
