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

from intelligence_fusion.provider_signal_payload import compact_priority_context, compact_source_context

EDGE_URL = os.environ.get(
    'PROVIDER_ANALYZER_INGEST',
    'https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest',
)
AUDIENCE = 'provider-analyzer-ingest'
PRODUCER_ID = 'PROVIDER_ANALYZER'
CONTEXT_SIGNAL_TYPE = 'PROVIDER_REVIEW_SIGNAL'
_TOKEN = None
_AT = 0.0


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


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(obj):
    raw = obj.encode() if isinstance(obj, str) else canonical_json(obj).encode()
    return hashlib.sha256(raw).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    raw = '|'.join(str(x or '') for x in parts).encode()
    return f'{prefix}-{hashlib.sha256(raw).hexdigest()[:24].upper()}'


def lines(path: Path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def chunks(rows, n):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def write_jsonl(path: Path, rows: list[dict]) -> str:
    text = ''.join(canonical_json(x) + '\n' for x in rows)
    path.write_text(text, encoding='utf-8')
    return hashlib.sha256(text.encode()).hexdigest()


def month_start(period: str) -> str:
    return f'{period}-01T00:00:00Z'


def evidence_quality(signal: dict) -> str:
    metrics = signal.get('metrics') or {}
    comp = metrics.get('comparability_index')
    try:
        if comp is not None and float(comp) < 80:
            return 'PARTIAL'
    except (TypeError, ValueError):
        return 'PARTIAL'
    if metrics.get('data_quality_flags'):
        return 'PARTIAL'
    return 'VALID'


def build_canonical_records(row: dict, raw_signal: dict, generated_at: str, run_id: str) -> tuple[dict, dict, dict]:
    signal_id = row['signal_id']
    evidence_id = stable_id('EVD-PA', signal_id, row['period'])
    event_id = stable_id('EVT-PA', signal_id, row['period'])
    compact_source = {
        'signal_id': signal_id,
        'signal_type': row['signal_type'],
        'supplier_id': row.get('supplier_id'),
        'buyer_id': row.get('buyer_id'),
        'pair_id': row.get('pair_id'),
        'period': row['period'],
        'review_priority': row.get('review_priority'),
        'review_tier': row.get('review_tier'),
        'reason': row.get('reason'),
        'metrics': row.get('metrics') or {},
    }
    content_hash = sha(compact_source)
    evidence = {
        'evidence_id': evidence_id,
        'producer_id': PRODUCER_ID,
        'source_id': 'PROVIDER_ANALYZER_DERIVATION',
        'ultimate_source_id': 'CHILECOMPRA',
        'source_url': None,
        'source_tier': 'DERIVED_OPEN_SOURCE',
        'capture_method': 'ANALYTIC_DERIVATION',
        'source_run_id': run_id,
        'content_sha256': content_hash,
        'quality_status': evidence_quality(raw_signal),
        'source_published_at': None,
        'retrieved_at': generated_at,
        'ingested_at': generated_at,
        'excerpt': str(row.get('reason') or 'Señal de revisión de contratación pública.')[:1200],
        'schema_version': '1.0',
        'attributes': {
            'period': row['period'],
            'provider_signal_type': row['signal_type'],
            'review_priority': row.get('review_priority'),
            'review_tier': row.get('review_tier'),
            'supplier_ref': row.get('supplier_id'),
            'buyer_ref': row.get('buyer_id'),
            'pair_ref': row.get('pair_id'),
            'derived_only': True,
            'contains_raw_procurement_data': False,
        },
    }
    event = {
        'event_id': event_id,
        'event_type': 'PROCUREMENT_REVIEW_SIGNAL',
        'producer_id': PRODUCER_ID,
        'entity_ids': [],
        'territory_ids': [],
        'sector_ids': [],
        'evidence_ids': [evidence_id],
        'temporal': {
            'valid_from': month_start(row['period']),
            'period': row['period'],
        },
        'attributes': {
            'source_signal_id': signal_id,
            'provider_signal_type': row['signal_type'],
            'supplier_ref': row.get('supplier_id'),
            'buyer_ref': row.get('buyer_id'),
            'pair_ref': row.get('pair_id'),
            'review_priority': row.get('review_priority'),
            'review_tier': row.get('review_tier'),
            'reason': row.get('reason'),
            'scoring_eligible': False,
            'risk_effect': 'NONE',
            'interpretation_guardrail': 'Evento analítico de revisión. No acredita irregularidad, delito ni LA/FT.',
        },
    }
    context = {
        'signal_id': signal_id,
        'signal_type': CONTEXT_SIGNAL_TYPE,
        'producer_id': PRODUCER_ID,
        'semantics': 'CONTEXT_ONLY',
        'scope': {
            'entity_ref': row.get('supplier_id'),
            'buyer_ref': row.get('buyer_id'),
            'pair_ref': row.get('pair_id'),
        },
        'value': row.get('review_priority'),
        'threshold': None,
        'metrics': {
            'provider_signal_type': row['signal_type'],
            'review_tier': row.get('review_tier'),
            'evidence_count': row.get('evidence_count'),
            **(row.get('metrics') or {}),
        },
        'window': {'period': row['period']},
        'rule_version': '1.0',
        'evidence_ids': [evidence_id],
        'event_ids': [event_id],
        'explanation': str(row.get('reason') or 'Señal contextual de revisión de contratación pública.'),
        'interpretation_guardrail': 'Prioridad de revisión contextual; no representa probabilidad de delito, infracción, corrupción ni lavado de activos y no modifica el scoring AML.',
        'scoring_eligible': False,
        'risk_effect': 'NONE',
    }
    return evidence, event, context


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--signals', type=Path, required=True)
    ap.add_argument('--priority', type=Path, required=True)
    ap.add_argument('--period', required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()

    signals = lines(args.signals)
    priority = json.loads(args.priority.read_text(encoding='utf-8'))
    by = {str(x.get('review_key') or ''): x for x in priority.get('review_cases') or []}
    run_id = str(os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    export: list[dict] = []
    db: list[dict] = []
    evidence_rows: list[dict] = []
    event_rows: list[dict] = []
    context_rows: list[dict] = []

    for s in signals:
        pair = str(s.get('provider_buyer_pair_id') or s.get('pair_id') or '')
        p = by.get(pair) or {}
        row = {
            'signal_id': str(s.get('signal_id')),
            'signal_type': str(s.get('signal_type') or 'UNKNOWN'),
            'semantic_class': 'INTEGRITY_REVIEW',
            'supplier_id': s.get('supplier_id'),
            'buyer_id': s.get('buyer_id'),
            'pair_id': pair or None,
            'period': args.period,
            'review_priority': p.get('review_priority'),
            'review_tier': p.get('tier'),
            'evidence_count': len(s.get('evidence_ids') or []),
            'source_system': PRODUCER_ID,
            'source_ref': f'Claude_AML/provider_analyzer/exports/{args.period}',
            'scoring_eligible': False,
            'risk_effect': 'CONTEXT',
            'reason': s.get('reason'),
            'metrics': s.get('metrics') or {},
            'guardrails': {
                'signal_is_not_wrongdoing_probability': True,
                'review_priority_is_not_aml_risk_score': True,
                'public_integrity_modifies_aml_score': False,
            },
        }
        export.append(row)
        db_payload = {
            **row,
            'source_context': compact_source_context(s),
            'priority_context': compact_priority_context(p),
        }
        db.append({
            'signal_id': row['signal_id'],
            'signal_type': row['signal_type'],
            'period': args.period,
            'supplier_id': row['supplier_id'],
            'buyer_id': row['buyer_id'],
            'pair_id': row['pair_id'],
            'review_priority': row['review_priority'],
            'severity_band': row['review_tier'],
            'scoring_eligible': False,
            'risk_effect': 'CONTEXT',
            'evidence_count': row['evidence_count'],
            'payload': db_payload,
            'semantic_hash': sha(db_payload),
            'source_run_id': run_id,
        })
        evd, evt, ctx = build_canonical_records(row, s, generated_at, run_id)
        evidence_rows.append(evd)
        event_rows.append(evt)
        context_rows.append(ctx)

    export.sort(key=lambda x: (-(float(x.get('review_priority') or 0)), x['signal_id']))
    evidence_rows.sort(key=lambda x: x['evidence_id'])
    event_rows.sort(key=lambda x: x['event_id'])
    context_rows.sort(key=lambda x: x['signal_id'])
    args.output_dir.mkdir(parents=True, exist_ok=True)

    provider_sha = write_jsonl(args.output_dir / 'provider_signals_v1.jsonl', export)
    evidence_sha = write_jsonl(args.output_dir / 'provider_evidence_v1.jsonl', evidence_rows)
    events_sha = write_jsonl(args.output_dir / 'provider_events_v1.jsonl', event_rows)
    context_sha = write_jsonl(args.output_dir / 'provider_context_signals_v1.jsonl', context_rows)
    bundle_hash = sha({
        'provider_signals': provider_sha,
        'evidence': evidence_sha,
        'events': events_sha,
        'context_signals': context_sha,
    })

    manifest = {
        'schema': 'PROVIDER_ANALYZER_EXPORT_V1',
        'status': 'READY',
        'generated_at': generated_at,
        'period': args.period,
        'signal_count': len(export),
        'content_sha256': bundle_hash,
        'source_system': PRODUCER_ID,
        'objects': {
            'provider_signals': {'path': 'provider_analyzer/exports/provider_signals_v1.jsonl', 'records': len(export), 'sha256': provider_sha},
            'evidence': {'path': 'provider_analyzer/exports/provider_evidence_v1.jsonl', 'records': len(evidence_rows), 'sha256': evidence_sha},
            'events': {'path': 'provider_analyzer/exports/provider_events_v1.jsonl', 'records': len(event_rows), 'sha256': events_sha},
            'context_signals': {'path': 'provider_analyzer/exports/provider_context_signals_v1.jsonl', 'records': len(context_rows), 'sha256': context_sha},
        },
        'contract': {
            'analyzer_semantic_class': 'INTEGRITY_REVIEW',
            'fusion_semantics': 'CONTEXT_ONLY',
            'scoring_eligible': False,
            'risk_effect': 'NONE',
        },
        'guardrails': {
            'contains_no_raw_procurement_dataset': True,
            'signal_is_not_wrongdoing_probability': True,
            'review_priority_is_not_aml_risk_score': True,
            'fusion_may_use_as_context_only': True,
            'missing_is_not_zero': True,
        },
    }
    (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    for b in chunks(db, 200):
        post({'kind': 'signal_batch', 'rows': b})
    post({'kind': 'export_batch', 'row': {
        'export_id': f'{args.period}:{bundle_hash[:20]}',
        'schema_version': 'PROVIDER_ANALYZER_EXPORT_V1',
        'source_run_id': run_id,
        'signal_count': len(export),
        'content_sha256': bundle_hash,
        'status': 'READY',
        'detail': manifest,
    }})
    post({'kind': 'state', 'row': {
        'pipeline': 'LATEST_EXPORT',
        'status': 'SUCCESS',
        'source_digest': bundle_hash,
        'detail': manifest,
    }})
    print(json.dumps({'period': args.period, 'signals': len(export), 'bundle_sha256': bundle_hash, 'signal_batch_size': 200}, ensure_ascii=False))


if __name__ == '__main__':
    main()
