#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from intelligence_fusion.sources.chilecompra_bulk_orders import ChileCompraBulkOrdersAdapter
from intelligence_fusion.sources.common import as_float, norm_text
from intelligence_fusion.sources.validation import plausible_event_date, stable_party_id, valid_chilean_rut, valid_order_id

ALLOWED_HOST = 'transparenciachc.blob.core.windows.net'
ALLOWED_PREFIX = '/oc-da/'


def download(url: str, dst: Path) -> None:
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or (p.hostname or '').lower() != ALLOWED_HOST or not p.path.startswith(ALLOWED_PREFIX):
        raise ValueError('unexpected bulk orders URL')
    req = urllib.request.Request(url, headers={'User-Agent': 'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r, dst.open('wb') as f:
        shutil.copyfileobj(r, f)


def encoding_for(path: Path) -> str:
    raw = path.open('rb').read(65536)
    try:
        raw.decode('utf-8-sig')
        return 'utf-8-sig'
    except UnicodeDecodeError:
        return 'latin-1'


def product_key(row: dict, mapping: dict) -> str:
    def get(key: str):
        return row.get(mapping.get(key)) if mapping.get(key) else None
    code = norm_text(get('product_code'))
    if code:
        return 'CODE:' + code
    text = norm_text(get('product_name') or get('description')).lower()
    return 'TEXT:' + text if text else ''


def official_dialect(sample: str, adapter: ChileCompraBulkOrdersAdapter) -> csv.Dialect:
    header = sample.splitlines()[0] if sample.splitlines() else ''
    if ';' in header:
        class Semi(csv.excel):
            delimiter = ';'
        return Semi()
    return adapter.sniff(sample)


def row_shape_reason(row: dict) -> str | None:
    if None in row:
        return 'EXTRA_COLUMNS'
    if any(value is None for value in row.values()):
        return 'MISSING_COLUMNS'
    return None


def choose_event_date(row: dict, mapping: dict) -> tuple[str, str, int]:
    """Use acceptance when available, then creation, then modification.

    The archive month is preserved as the source cohort. The lifecycle date is a
    separate analytical axis and must never be overwritten by the archive period.
    """
    invalid_candidates = 0
    for key in ('accepted_at', 'created_at', 'modified_at'):
        col = mapping.get(key)
        raw = row.get(col) if col else None
        if raw in (None, ''):
            continue
        parsed = plausible_event_date(raw)
        if parsed:
            return parsed, key, invalid_candidates
        invalid_candidates += 1
    return '', '', invalid_candidates


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--month', type=int, required=True)
    ap.add_argument('--output-dir', type=Path, default=Path('runtime/provider_analyzer/order_history_month'))
    ap.add_argument('--max-rows', type=int, default=0)
    ap.add_argument('--max-quarantine-rate', type=float, default=0.05)
    args = ap.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    adapter = ChileCompraBulkOrdersAdapter()
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    quarantine_path = out / 'order_quarantine.jsonl.gz'

    with tempfile.TemporaryDirectory() as td_raw:
        td = Path(td_raw)
        archive = td / 'orders.zip'
        extract = td / 'x'
        download(args.url, archive)
        shutil.unpack_archive(str(archive), str(extract))
        csvs = sorted(extract.rglob('*.csv'), key=lambda p: p.stat().st_size, reverse=True)
        if not csvs:
            raise FileNotFoundError('bulk order archive contains no CSV')
        src = csvs[0]
        enc = encoding_for(src)

        with src.open('r', encoding=enc, newline='') as fh, gzip.open(quarantine_path, 'wt', encoding='utf-8') as qh:
            sample = fh.read(12000)
            fh.seek(0)
            dialect = official_dialect(sample, adapter)
            reader = csv.DictReader(fh, dialect=dialect)
            mapping = adapter.resolve_columns(reader.fieldnames)
            raw_columns = list(reader.fieldnames or [])
            if 'order_id' not in mapping:
                raise RuntimeError('missing required column: order_id')
            if not ({'buyer_rut', 'buyer_name'} & set(mapping)):
                raise RuntimeError('missing buyer identity columns')
            if not ({'supplier_rut', 'supplier_name'} & set(mapping)):
                raise RuntimeError('missing supplier identity columns')

            orders: dict[str, dict] = {}
            events: dict[tuple[str, str], dict] = {}
            rows_read = 0
            structurally_valid_rows = 0
            quarantined_rows = 0
            quarantine_reasons: Counter[str] = Counter()
            date_source_counts: Counter[str] = Counter()
            invalid_date_candidates = 0
            rows_without_valid_date = 0

            def get(row: dict, key: str):
                return row.get(mapping.get(key)) if mapping.get(key) else None

            for row in reader:
                rows_read += 1
                if args.max_rows and rows_read > args.max_rows:
                    break
                reason = row_shape_reason(row)
                oid = str(get(row, 'order_id') or '').strip()
                buyer_id, _ = stable_party_id(get(row, 'buyer_rut'), get(row, 'buyer_name'))
                supplier_id, _ = stable_party_id(get(row, 'supplier_rut'), get(row, 'supplier_name'))
                if reason is None and not valid_order_id(oid):
                    reason = 'INVALID_ORDER_ID'
                if reason is None and not buyer_id:
                    reason = 'INVALID_BUYER_IDENTITY'
                if reason is None and not supplier_id:
                    reason = 'INVALID_SUPPLIER_IDENTITY'
                if reason:
                    quarantined_rows += 1
                    quarantine_reasons[reason] += 1
                    qh.write(json.dumps({'stage':'ORDER_CSV_ROW','reason':reason,'source':'CHILECOMPRA_OC_DA','source_year':args.year,'source_month':args.month,'row_number':rows_read,'payload':row}, ensure_ascii=False, separators=(',', ':')) + '\n')
                    continue

                structurally_valid_rows += 1
                event_date, event_date_source, bad_dates = choose_event_date(row, mapping)
                invalid_date_candidates += bad_dates
                if not event_date:
                    rows_without_valid_date += 1
                elif event_date_source:
                    date_source_counts[event_date_source] += 1

                order = orders.setdefault(oid, {'order_id':oid,'buyer_id':'','supplier_id':'','buyer_rut_valid':False,'supplier_rut_valid':False,'date':'','date_source':'','amount_clp':0.0,'modality':'','status':'','tender_id':''})
                order['buyer_id'] = buyer_id or order['buyer_id']
                order['supplier_id'] = supplier_id or order['supplier_id']
                order['buyer_rut_valid'] = order['buyer_rut_valid'] or valid_chilean_rut(get(row, 'buyer_rut')) is not None
                order['supplier_rut_valid'] = order['supplier_rut_valid'] or valid_chilean_rut(get(row, 'supplier_rut')) is not None
                if not order['date'] and event_date:
                    order['date'] = event_date
                    order['date_source'] = event_date_source
                clp = as_float(get(row, 'total_amount_clp'))
                raw = as_float(get(row, 'total_amount'))
                if clp not in (None, 0):
                    order['amount_clp'] = float(clp)
                elif raw not in (None, 0) and str(get(row, 'currency') or '').strip().upper() in {'CLP','PESO CHILENO','PESOS CHILENOS','$'}:
                    order['amount_clp'] = float(raw)
                order['modality'] = order['modality'] or str(get(row, 'modality') or '')
                order['status'] = order['status'] or str(get(row, 'status') or '')
                order['tender_id'] = order['tender_id'] or str(get(row, 'tender_id') or '')
                pk = product_key(row, mapping)
                if pk:
                    events[(oid, pk)] = {'order_id': oid, 'product_key': pk}

    quarantine_rate = quarantined_rows / max(rows_read, 1)
    if not args.max_rows and quarantine_rate > args.max_quarantine_rate:
        raise RuntimeError(f'quarantine rate {quarantine_rate:.4%} exceeds threshold {args.max_quarantine_rate:.4%}')

    buyer_totals = defaultdict(float)
    buyer_orders = defaultdict(int)
    pairs: dict[str, dict] = {}
    identified_orders = 0
    amount_orders = 0
    orders_with_valid_date = 0
    orders_with_valid_ruts = 0
    for order in orders.values():
        if order['buyer_id']:
            buyer_totals[order['buyer_id']] += order['amount_clp']
            buyer_orders[order['buyer_id']] += 1
        if order['amount_clp'] > 0:
            amount_orders += 1
        if order['date']:
            orders_with_valid_date += 1
        if order['buyer_rut_valid'] and order['supplier_rut_valid']:
            orders_with_valid_ruts += 1
        if not order['buyer_id'] or not order['supplier_id']:
            continue
        identified_orders += 1
        key = f"{order['supplier_id']}::{order['buyer_id']}"
        pair = pairs.setdefault(key, {'pair_id':key,'buyer_id':order['buyer_id'],'supplier_id':order['supplier_id'],'order_count':0,'amount_total_clp':0.0,'modalities':set(),'first_seen':None,'last_seen':None})
        pair['order_count'] += 1
        pair['amount_total_clp'] += order['amount_clp']
        if order['modality']:
            pair['modalities'].add(order['modality'])
        d = order['date'] or None
        if d:
            pair['first_seen'] = d if pair['first_seen'] is None or d < pair['first_seen'] else pair['first_seen']
            pair['last_seen'] = d if pair['last_seen'] is None or d > pair['last_seen'] else pair['last_seen']

    pair_rows = []
    for pair in pairs.values():
        buyer_total = buyer_totals.get(pair['buyer_id'], 0.0)
        pair['buyer_amount_total_clp'] = buyer_total
        pair['buyer_share_month'] = pair['amount_total_clp'] / buyer_total if buyer_total else None
        pair['modalities'] = sorted(pair['modalities'])
        pair['year'] = args.year
        pair['month'] = args.month
        pair_rows.append(pair)
    pair_rows.sort(key=lambda x: (-x['amount_total_clp'], x['pair_id']))

    with gzip.open(out / 'purchase_events.jsonl.gz', 'wt', encoding='utf-8') as fh:
        for (oid, pk), _ in events.items():
            order = orders.get(oid) or {}
            if not order.get('buyer_id') or not order.get('supplier_id') or not order.get('date'):
                continue
            status = norm_text(order.get('status')).lower()
            if any(x in status for x in ('cancel', 'anulad', 'rechaz')):
                continue
            record = {'buyer_id':order['buyer_id'],'supplier_id':order['supplier_id'],'pair_id':f"{order['supplier_id']}::{order['buyer_id']}",'product_key':pk,'date':order.get('date'),'date_source':order.get('date_source'),'status':'PURCHASED','order_id':oid,'tender_id':order.get('tender_id'),'process_id':order.get('tender_id') or oid,'modality':order.get('modality'),'source':'MERCADO_PUBLICO_BULK_ORDERS','source_year':args.year,'source_month':args.month}
            fh.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')

    sample_limited = bool(args.max_rows)
    order_count = len(orders)
    summary = {'schema':'PROVIDER_ANALYZER_ORDER_HISTORY_MONTH_V2','generated_at':now,'mode':'SHADOW','year':args.year,'month':args.month,'source_period_semantics':'CHILECOMPRA_ARCHIVE_MONTH','event_date_semantics':'ACCEPTED_AT_ELSE_CREATED_AT_ELSE_MODIFIED_AT','source_url':args.url,'csv':{'encoding':enc,'delimiter':dialect.delimiter,'raw_column_count':len(raw_columns),'raw_columns':raw_columns,'resolved_mapping':mapping},'coverage':{'rows_read':rows_read,'structurally_valid_rows':structurally_valid_rows,'quarantined_rows':quarantined_rows,'quarantine_rate':round(quarantine_rate,6),'quarantine_reasons':dict(quarantine_reasons),'orders':order_count,'orders_with_buyer_and_supplier':identified_orders,'identity_coverage':round(identified_orders/max(order_count,1),6),'orders_with_valid_buyer_and_supplier_rut':orders_with_valid_ruts,'rut_identity_coverage':round(orders_with_valid_ruts/max(order_count,1),6),'orders_with_clp_amount':amount_orders,'clp_amount_coverage':round(amount_orders/max(order_count,1),6),'orders_with_valid_event_date':orders_with_valid_date,'event_date_coverage':round(orders_with_valid_date/max(order_count,1),6),'event_date_source_counts':dict(date_source_counts),'invalid_date_candidates':invalid_date_candidates,'rows_without_valid_date':rows_without_valid_date,'pair_count':len(pair_rows),'purchase_event_keys':len(events),'sample_limited':sample_limited,'source_month_fully_scanned':not sample_limited},'buyer_totals_clp':dict(buyer_totals),'buyer_order_counts':dict(buyer_orders),'pairs':pair_rows,'guardrails':{'historical_concentration_is_not_wrongdoing_probability':True,'missing_is_not_zero':True,'amounts_use_clp_when_available':True,'source_period_is_not_event_period':True,'source_period_is_archive_cohort':True,'invalid_rows_are_quarantined':True,'dates_normalized_iso':True,'public_integrity_modifies_aml_score':False}}
    (out / 'history_month.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'year':args.year,'month':args.month,'rows':rows_read,'orders':order_count,'identity_coverage':summary['coverage']['identity_coverage'],'rut_identity_coverage':summary['coverage']['rut_identity_coverage'],'clp_amount_coverage':summary['coverage']['clp_amount_coverage'],'event_date_coverage':summary['coverage']['event_date_coverage'],'quarantined_rows':quarantined_rows,'quarantine_rate':summary['coverage']['quarantine_rate'],'pairs':len(pair_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
