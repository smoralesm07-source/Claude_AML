#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

EDGE_URL = os.environ.get(
    'PROVIDER_ANALYZER_INGEST',
    'https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest',
)
AUDIENCE = 'provider-analyzer-ingest'


def github_oidc_token() -> str:
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    sep = '&' if '?' in url else '?'
    req = urllib.request.Request(
        url + sep + urllib.parse.urlencode({'audience': AUDIENCE}),
        headers={'Authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)['value']


def post(body: dict) -> dict:
    req = urllib.request.Request(
        EDGE_URL,
        data=json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode(),
        method='POST',
        headers={
            'Authorization': 'Bearer ' + github_oidc_token(),
            'Content-Type': 'application/json',
            'User-Agent': 'Provider-Anomaly-Analyzer/1.1',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pipeline', required=True)
    ap.add_argument('--status', required=True, choices=('RUNNING', 'SUCCESS', 'FAILED'))
    ap.add_argument('--period')
    ap.add_argument('--stage', default='BACKFILL')
    args = ap.parse_args()
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    detail = {
        'stage': args.stage,
        'period': args.period,
        'github_run_id': os.environ.get('GITHUB_RUN_ID'),
        'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'github_sha': os.environ.get('GITHUB_SHA'),
        'event_name': os.environ.get('GITHUB_EVENT_NAME'),
        'heartbeat_at': now,
    }
    result = post({'kind': 'state', 'row': {
        'pipeline': args.pipeline,
        'status': args.status,
        'detail': detail,
    }})
    print(json.dumps({'heartbeat': result, **detail, 'status': args.status}, ensure_ascii=False))


if __name__ == '__main__':
    main()
