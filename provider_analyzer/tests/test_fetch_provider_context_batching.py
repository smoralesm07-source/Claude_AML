from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).parents[1] / 'scripts' / 'fetch_provider_context.py'
    spec = importlib.util.spec_from_file_location('fetch_provider_context', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_history_query_batches_at_edge_contract_limit():
    module = load_module()
    calls = []

    def fake_post(body):
        calls.append(body)
        ids = body['pair_ids']
        return {
            'ok': True,
            'histories': {pair_id: {'pair_id': pair_id} for pair_id in ids},
            'rows': len(ids) * 2,
            'pairs': len(ids),
            'storage': 'PAIR_MONTH_COMPACT_V2',
        }

    ids = [f'S{i}::B{i}' for i in range(701)]
    result = module.history_query_batched(
        ids,
        end_year=2026,
        end_month=7,
        post_fn=fake_post,
    )

    assert [len(call['pair_ids']) for call in calls] == [300, 300, 101]
    assert result['batches'] == 3
    assert result['requested_pairs'] == 701
    assert result['pairs'] == 701
    assert result['rows'] == 1402
    assert len(result['histories']) == 701
    assert result['storage'] == 'PAIR_MONTH_COMPACT_V2'


def test_history_query_deduplicates_targets_before_batching():
    module = load_module()
    calls = []

    def fake_post(body):
        calls.append(body)
        ids = body['pair_ids']
        return {'ok': True, 'histories': {x: {'pair_id': x} for x in ids}, 'rows': len(ids)}

    result = module.history_query_batched(
        ['A::B', 'A::B', '', 'C::D'],
        end_year=2026,
        end_month=7,
        post_fn=fake_post,
    )

    assert calls[0]['pair_ids'] == ['A::B', 'C::D']
    assert result['requested_pairs'] == 2
    assert result['pairs'] == 2


def test_history_query_rejects_oversized_client_batch():
    module = load_module()
    try:
        module.history_query_batched(
            ['A::B'],
            end_year=2026,
            end_month=7,
            post_fn=lambda body: {},
            batch_size=301,
        )
    except ValueError as exc:
        assert str(exc) == 'INVALID_HISTORY_BATCH_SIZE'
    else:
        raise AssertionError('expected ValueError')
