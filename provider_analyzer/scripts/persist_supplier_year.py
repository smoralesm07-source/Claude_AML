#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EDGE_URL = os.environ.get(
    'PROVIDER_ANALYZER_INGEST',
    'https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest',
)
AUDIENCE = 'provider-analyzer-ingest'
_TOKEN = None
_AT = 0.0
TRANSIENT_HTTP = {429, 500, 502, 503, 504}
MAX_BATCH_ROWS = 200
MAX_BATCH_BYTES = 1_500_000


def token() -> str:
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


def post(body: dict, timeout: int = 180, attempts: int = 4) -> dict:
    payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(
            EDGE_URL,
            data=payload,
            method='POST',
            headers={
                'Authorization': 'Bearer ' + token(),
                'Content-Type': 'application/json',
                'User-Agent': 'Provider-Entity-History/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode('utf-8', 'replace')
            last = RuntimeError(f'HTTP {exc.code}: {raw[:500]}')
            if exc.code not in TRANSIENT_HTTP or attempt + 1 >= attempts:
                raise last from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 >= attempts:
                raise
        time.sleep(2**attempt)
    raise RuntimeError(f'POST_FAILED:{last}')


def flush(rows: list[dict]) -> int:
    if not rows:
        return 0
    result = post({'kind': 'supplier_year_batch', 'rows': rows})
    written = int(result.get('written') or 0)
    if written != len(rows):
        raise RuntimeError(f'PARTIAL_WRITE:{written}!={len(rows)}')
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--supplier-year', type=Path, required=True)
    ap.add_argument('--coverage', type=Path, required=True)
    args = ap.parse_args()

    print(post({'kind': 'ping'}))

    written = 0
    batch: list[dict] = []
    batch_bytes = 0
    with gzip.open(args.supplier_year, 'rt', encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            row_bytes = len(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode())
            if batch and (len(batch) >= MAX_BATCH_ROWS or batch_bytes + row_bytes > MAX_BATCH_BYTES):
                written += flush(batch)
                batch = []
                batch_bytes = 0
            batch.append(row)
            batch_bytes += row_bytes
        written += flush(batch)

    coverage_rows = json.loads(args.coverage.read_text(encoding='utf-8'))
    coverage_written = 0
    for i in range(0, len(coverage_rows), 200):
        part = coverage_rows[i:i + 200]
        result = post({'kind': 'coverage_batch', 'rows': part})
        coverage_written += int(result.get('written') or result.get('rows') or len(part))

    summary = {
        'ok': True,
        'supplier_year_rows_written': written,
        'coverage_rows_sent': len(coverage_rows),
        'coverage_rows_written': coverage_written,
        'storage': 'SUPPLIER_YEAR_PACKED_V1',
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
