#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EDGE_URL = os.environ.get(
    'PROVIDER_ANALYZER_INGEST',
    'https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest',
)
AUDIENCE = 'provider-analyzer-ingest'
PRODUCER_ID = 'PROVIDER_ANALYZER'
BASE_STAGE = 'BASE_SIGNALS_READY'
_TOKEN = None
_AT = 0.0


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(obj):
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def chunks(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def token():
    global _TOKEN, _AT
    if _TOKEN and time.time() - _AT < 120:
        return _TOKEN
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    sep = '&' if '?' in url else '?'
    req = urllib.request.Request(
        url + sep + urllib.parse.urlencode({'audience': AUDIENCE}),
        headers={'Authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        _TOKEN = json.load(r)['value']
    _AT = time.time()
    return _TOKEN


def post(body, timeout=180):
    req = urllib.request.Request(
        EDGE_URL,
        data=json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode(),
        method='POST',
        headers={
            'Authorization': 'Bearer ' + token(),
            'Content-Type': 'application/json',
            'User-Agent': 'Provider-Anomaly-Analyzer/1.1',
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def build_base_signal_rows(
    signals: list[dict],
    priority_doc: dict,
    period: str,
    *,
    run_id: str,
    updated_at: str,
) -> list[dict]:
    priority_by_key = {
        str(x.get('review_key') or ''): x
        for x in (priority_doc.get('review_cases') or [])
        if str(x.get('review_key') or '')
    }
    rows: list[dict] = []
    seen_signal_ids: set[str] = set()
    for signal in signals:
        signal_id = str(signal.get('signal_id') or '')
        if not signal_id:
            raise ValueError('SIGNAL_ID_REQUIRED')
        if signal_id in seen_signal_ids:
            raise ValueError(f'DUPLICATE_SIGNAL_ID:{signal_id}')
        seen_signal_ids.add(signal_id)
        pair = str(signal.get('provider_buyer_pair_id') or signal.get('pair_id') or '')
        priority = priority_by_key.get(pair) or {}
        presentation = {
            'signal_id': signal_id,
            'signal_type': str(signal.get('signal_type') or 'UNKNOWN'),
            'semantic_class': 'INTEGRITY_REVIEW',
            'supplier_id': signal.get('supplier_id'),
            'buyer_id': signal.get('buyer_id'),
            'pair_id': pair or None,
            'period': period,
            'review_priority': priority.get('review_priority'),
            'review_tier': priority.get('tier'),
            'evidence_count': len(signal.get('evidence_ids') or []),
            'source_system': PRODUCER_ID,
            'source_ref': f'Claude_AML/provider_analyzer/exports/{period}',
            'scoring_eligible': False,
            'risk_effect': 'CONTEXT',
            'reason': signal.get('reason'),
            'metrics': signal.get('metrics') or {},
            'provisional_stage': BASE_STAGE,
            'route_enrichment_pending': True,
            'guardrails': {
                'signal_is_not_wrongdoing_probability': True,
                'review_priority_is_not_aml_risk_score': True,
                'public_integrity_modifies_aml_score': False,
                'route_enrichment_pending': True,
            },
        }
        payload = {
            **presentation,
            'raw_signal': signal,
            'priority_context': priority,
        }
        rows.append({
            'signal_id': signal_id,
            'signal_type': presentation['signal_type'],
            'period': period,
            'supplier_id': presentation['supplier_id'],
            'buyer_id': presentation['buyer_id'],
            'pair_id': presentation['pair_id'],
            'review_priority': presentation['review_priority'],
            'severity_band': presentation['review_tier'],
            'scoring_eligible': False,
            'risk_effect': 'CONTEXT',
            'evidence_count': presentation['evidence_count'],
            'payload': payload,
            'semantic_hash': sha(payload),
            'source_run_id': run_id,
            'updated_at': updated_at,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(
        description='Persist provisional provider signals after governed history, before route enrichment.'
    )
    ap.add_argument('--signals', type=Path, required=True)
    ap.add_argument('--priority', type=Path, required=True)
    ap.add_argument('--period', required=True)
    args = ap.parse_args()

    signals = lines(args.signals)
    priority_doc = json.loads(args.priority.read_text(encoding='utf-8'))
    run_id = str(os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    updated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    rows = build_base_signal_rows(
        signals,
        priority_doc,
        args.period,
        run_id=run_id,
        updated_at=updated_at,
    )

    written = 0
    unchanged = 0
    for batch in chunks(rows, 400):
        result = post({'kind': 'signal_batch', 'rows': batch})
        written += int(result.get('written') or 0)
        unchanged += int(result.get('unchanged') or 0)

    print(json.dumps({
        'period': args.period,
        'stage': BASE_STAGE,
        'signals': len(rows),
        'written': written,
        'unchanged': unchanged,
        'route_enrichment_pending': True,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
