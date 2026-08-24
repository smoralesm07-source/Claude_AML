from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'persist_provider_base_signals.py'
spec = importlib.util.spec_from_file_location('persist_provider_base_signals', SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def sample_signal():
    return {
        'signal_id': 'SIG-001',
        'signal_type': 'LOW_COMPETITION',
        'supplier_id': '76123456-8',
        'buyer_id': '69123456-7',
        'buyer_name': 'Comprador de prueba',
        'tender_id': '1000-1-LE26',
        'provider_buyer_pair_id': '76123456-8::69123456-7',
        'reason': 'Señal de revisión',
        'metrics': {'comparability_index': 90},
        'evidence_ids': ['raw-evidence-1'],
    }


def sample_priority(score=62.5, tier='MEDIUM'):
    history = {
        'pair_id': '76123456-8::69123456-7',
        'order_count': 5,
        'amount_total_clp': 123456,
    }
    return {
        'review_cases': [{
            'review_key': '76123456-8::69123456-7',
            'review_priority': score,
            'tier': tier,
            'alternative_route_count': 0,
            'components': {'historical_persistence': 4, 'alternative_route': 0},
            'history': history,
            'history_context': history,
            'history_used_for_priority': True,
        }]
    }


def test_base_signal_preserves_stable_id_and_marks_route_pending():
    rows = module.build_base_signal_rows(
        [sample_signal()],
        sample_priority(),
        '2026-07',
        run_id='100',
        updated_at='2026-08-24T01:00:00Z',
    )
    assert len(rows) == 1
    row = rows[0]
    assert row['signal_id'] == 'SIG-001'
    assert row['review_priority'] == 62.5
    assert row['severity_band'] == 'MEDIUM'
    assert row['scoring_eligible'] is False
    assert row['risk_effect'] == 'CONTEXT'
    assert row['payload']['provisional_stage'] == 'BASE_SIGNALS_READY'
    assert row['payload']['route_enrichment_pending'] is True
    assert row['payload']['guardrails']['route_enrichment_pending'] is True
    assert 'raw_signal' not in row['payload']
    assert row['payload']['source_context']['tender_id'] == '1000-1-LE26'
    assert row['payload']['source_context']['buyer_name'] == 'Comprador de prueba'
    assert row['payload']['source_context']['source_evidence_ids'] == ['raw-evidence-1']
    assert 'history' not in row['payload']['priority_context']
    assert row['payload']['priority_context']['history_context']['order_count'] == 5


def test_semantic_hash_is_idempotent_across_run_metadata():
    a = module.build_base_signal_rows(
        [sample_signal()], sample_priority(), '2026-07',
        run_id='100', updated_at='2026-08-24T01:00:00Z'
    )[0]
    b = module.build_base_signal_rows(
        [sample_signal()], sample_priority(), '2026-07',
        run_id='200', updated_at='2026-08-24T02:00:00Z'
    )[0]
    assert a['semantic_hash'] == b['semantic_hash']
    assert a['source_run_id'] != b['source_run_id']
    assert a['updated_at'] != b['updated_at']


def test_priority_change_changes_semantic_hash_for_final_upsert_path():
    a = module.build_base_signal_rows(
        [sample_signal()], sample_priority(62.5, 'MEDIUM'), '2026-07',
        run_id='100', updated_at='2026-08-24T01:00:00Z'
    )[0]
    b = module.build_base_signal_rows(
        [sample_signal()], sample_priority(82.0, 'HIGH'), '2026-07',
        run_id='100', updated_at='2026-08-24T01:00:00Z'
    )[0]
    assert a['semantic_hash'] != b['semantic_hash']


def test_provisional_writer_cannot_publish_final_export_state():
    text = SCRIPT.read_text(encoding='utf-8')
    assert "'export_batch'" not in text
    assert 'LATEST_EXPORT' not in text
