#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from intelligence_fusion.sources.chilecompra_bulk_orders import ChileCompraBulkOrdersAdapter
from intelligence_fusion.sources.validation import plausible_event_date, valid_chilean_rut

ALLOWED_HOST = 'transparenciachc.blob.core.windows.net'
ALLOWED_PREFIX = '/oc-da/'
EDGE_URL = os.environ.get(
    'PROVIDER_IDENTITY_INGEST',
    'https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-identity-ingest',
)
AUDIENCE = 'provider-identity-ingest'
_TOKEN = None
_TOKEN_AT = 0.0


def download(url: str, dst: Path) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or (parsed.hostname or '').lower() != ALLOWED_HOST or not parsed.path.startswith(ALLOWED_PREFIX):
        raise ValueError('unexpected bulk orders URL')
    req = urllib.request.Request(url, headers={'User-Agent': 'Provider-Identity/1.0'})
    with urllib.request.urlopen(req, timeout=300) as response, dst.open('wb') as fh:
        shutil.copyfileobj(response, fh)


def encoding_for(path: Path) -> str:
    raw = path.open('rb').read(65536)
    try:
        raw.decode('utf-8-sig')
        return 'utf-8-sig'
    except UnicodeDecodeError:
        return 'latin-1'


def dialect_for(sample: str, adapter: ChileCompraBulkOrdersAdapter) -> csv.Dialect:
    header = sample.splitlines()[0] if sample.splitlines() else ''
    if ';' in header:
        class Semi(csv.excel):
            delimiter = ';'
        return Semi()
    return adapter.sniff(sample)


def clean_label(value: object) -> str:
    return ' '.join(str(value or '').strip().split())


def event_date(row: dict, mapping: dict) -> str | None:
    for key in ('accepted_at', 'created_at', 'modified_at'):
        col = mapping.get(key)
        if not col:
            continue
        parsed = plausible_event_date(row.get(col))
        if parsed:
            return parsed
    return None


def oidc_token() -> str:
    global _TOKEN, _TOKEN_AT
    if _TOKEN and time.time() - _TOKEN_AT < 120:
        return _TOKEN
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    sep = '&' if '?' in url else '?'
    req = urllib.request.Request(
        url + sep + urllib.parse.urlencode({'audience': AUDIENCE}),
        headers={'Authorization': 'bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        _TOKEN = json.load(response)['value']
    _TOKEN_AT = time.time()
    return _TOKEN


def post_rows(rows: list[dict], attempts: int = 4) -> dict:
    payload = json.dumps({'rows': rows}, ensure_ascii=False, separators=(',', ':')).encode()
    last: Exception | None = None
    for attempt in range(attempts):
        req = urllib.request.Request(
            EDGE_URL,
            data=payload,
            method='POST',
            headers={
                'Authorization': 'Bearer ' + oidc_token(),
                'Content-Type': 'application/json',
                'User-Agent': 'Provider-Identity/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode('utf-8', 'replace')
            last = RuntimeError(f'HTTP {exc.code}: {raw[:400]}')
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 >= attempts:
                raise last from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 >= attempts:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError(f'POST_FAILED:{last}')


def choose_label(counter: Counter[str]) -> str:
    if not counter:
        return ''
    return max(counter.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--month', type=int, required=True)
    ap.add_argument('--url')
    ap.add_argument('--persist', action='store_true')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()

    if args.year < 2007 or not 1 <= args.month <= 12:
        raise SystemExit('invalid period')

    url = args.url or f'https://transparenciachc.blob.core.windows.net/oc-da/{args.year}-{args.month}.zip'
    adapter = ChileCompraBulkOrdersAdapter()
    names: dict[str, Counter[str]] = defaultdict(Counter)
    roles: dict[str, set[str]] = defaultdict(set)
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    rows_read = 0
    named_observations = 0

    with tempfile.TemporaryDirectory(prefix=f'provider-identity-{args.year}-{args.month:02d}-') as td_raw:
        td = Path(td_raw)
        archive = td / 'orders.zip'
        extract = td / 'x'
        download(url, archive)
        shutil.unpack_archive(str(archive), str(extract))
        csvs = sorted(extract.rglob('*.csv'), key=lambda p: p.stat().st_size, reverse=True)
        if not csvs:
            raise FileNotFoundError('bulk order archive contains no CSV')
        src = csvs[0]
        enc = encoding_for(src)
        with src.open('r', encoding=enc, newline='') as fh:
            sample = fh.read(12000)
            fh.seek(0)
            dialect = dialect_for(sample, adapter)
            reader = csv.DictReader(fh, dialect=dialect)
            mapping = adapter.resolve_columns(reader.fieldnames)
            if not ({'buyer_rut', 'buyer_name'} & set(mapping)):
                raise RuntimeError('missing buyer identity columns')
            if not ({'supplier_rut', 'supplier_name'} & set(mapping)):
                raise RuntimeError('missing supplier identity columns')

            def get(row: dict, key: str):
                col = mapping.get(key)
                return row.get(col) if col else None

            for row in reader:
                rows_read += 1
                observed = event_date(row, mapping)
                for role, rut_key, name_key in (
                    ('buyer', 'buyer_rut', 'buyer_name'),
                    ('supplier', 'supplier_rut', 'supplier_name'),
                ):
                    party_id = valid_chilean_rut(get(row, rut_key))
                    label = clean_label(get(row, name_key))
                    if not party_id or len(label) < 2:
                        continue
                    names[party_id][label] += 1
                    roles[party_id].add(role)
                    named_observations += 1
                    if observed:
                        first_seen[party_id] = min(first_seen.get(party_id, observed), observed)
                        last_seen[party_id] = max(last_seen.get(party_id, observed), observed)

    identity_rows = [
        {
            'party_id': party_id,
            'canonical_label': choose_label(names[party_id]),
            'roles': sorted(roles[party_id]),
            'first_seen': first_seen.get(party_id),
            'last_seen': last_seen.get(party_id),
            'source': 'CHILECOMPRA_OC_DA',
            'source_year': args.year,
            'source_month': args.month,
        }
        for party_id in sorted(names)
        if choose_label(names[party_id])
    ]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(identity_rows, ensure_ascii=False, indent=2), encoding='utf-8')

    written = 0
    if args.persist:
        for i in range(0, len(identity_rows), 800):
            part = identity_rows[i:i + 800]
            result = post_rows(part)
            written += int(result.get('written') or 0)

    summary = {
        'ok': True,
        'period': f'{args.year:04d}-{args.month:02d}',
        'rows_read': rows_read,
        'named_observations': named_observations,
        'party_identities': len(identity_rows),
        'persisted': args.persist,
        'written': written,
        'source': 'CHILECOMPRA_OC_DA',
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
