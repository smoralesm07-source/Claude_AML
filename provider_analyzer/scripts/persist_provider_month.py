#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from intelligence_fusion.sources.validation import plausible_event_date, valid_order_id

EDGE_URL=os.environ.get('PROVIDER_ANALYZER_INGEST','https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest')
AUDIENCE='provider-analyzer-ingest';_TOKEN=None;_AT=0.0
ROUTE_BATCH_SIZE=1000
TRANSIENT_HTTP={429,500,502,503,504}

def token():
    global _TOKEN,_AT
    if _TOKEN and time.time()-_AT<120:return _TOKEN
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'];sep='&' if '?' in url else '?'
    req=urllib.request.Request(url+sep+urllib.parse.urlencode({'audience':AUDIENCE}),headers={'Authorization':'bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(req,timeout=30) as r:_TOKEN=json.load(r)['value']
    _AT=time.time();return _TOKEN

def _retryable_http(exc:urllib.error.HTTPError,body:str)->bool:
    low=body.lower()
    return exc.code in TRANSIENT_HTTP or (exc.code==403 and ('statement timeout' in low or '57014' in low or 'canceling statement due to statement timeout' in low))

def post(body,timeout=180,attempts=4):
    payload=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
    last=None
    for attempt in range(attempts):
        req=urllib.request.Request(EDGE_URL,data=payload,method='POST',headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json','User-Agent':'Provider-Anomaly-Analyzer/1.0'})
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
        except urllib.error.HTTPError as exc:
            raw=exc.read().decode('utf-8','replace')
            last=RuntimeError(f'HTTP {exc.code}: {raw[:400]}')
            if not _retryable_http(exc,raw) or attempt+1>=attempts:raise last from exc
        except (urllib.error.URLError,TimeoutError) as exc:
            last=exc
            if attempt+1>=attempts:raise
        time.sleep(2**attempt)
    if last:raise last
    raise RuntimeError('POST_FAILED_WITHOUT_ERROR')

def chunks(rows,n):
    for i in range(0,len(rows),n):yield rows[i:i+n]

def h(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def gz_rows(path:Path|None):
    if not path or not path.exists():return []
    with gzip.open(path,'rt',encoding='utf-8') as fh:return [json.loads(x) for x in fh if x.strip()]

def exact_decimal(value)->Decimal:
    try:return Decimal(str(value if value not in (None,'') else 0))
    except (InvalidOperation,ValueError,TypeError) as exc:raise ValueError(f'INVALID_DECIMAL:{value!r}') from exc

def decimal_text(value:Decimal)->str:
    return format(value,'f')

def economic_rows(hist:dict,year:int,month:int,now:str)->tuple[list[dict],list[dict]]:
    """Build buyer and pair rows from the same exact pair amounts."""
    raw_pairs=hist.get('pairs') or []
    buyer_amounts:dict[str,Decimal]=defaultdict(Decimal)
    buyer_orders:dict[str,int]=defaultdict(int)
    normalized=[]
    for r in raw_pairs:
        buyer=str(r.get('buyer_id') or '').strip();supplier=str(r.get('supplier_id') or '').strip();pair_id=str(r.get('pair_id') or '').strip()
        if not buyer or not supplier or not pair_id:raise ValueError('INVALID_ECONOMIC_PAIR')
        amount=exact_decimal(r.get('amount_total_clp'));orders=int(r.get('order_count') or 0)
        if orders<0:raise ValueError('INVALID_ORDER_COUNT')
        buyer_amounts[buyer]+=amount;buyer_orders[buyer]+=orders
        normalized.append((r,buyer,supplier,pair_id,amount,orders))
    expected_orders=sum(int(v or 0) for v in (hist.get('buyer_order_counts') or {}).values())
    actual_orders=sum(buyer_orders.values())
    if expected_orders!=actual_orders:raise ValueError(f'ECONOMIC_ORDER_RECONCILIATION_FAILED:{expected_orders}!={actual_orders}')
    buyers=[{'year':year,'month':month,'buyer_id':bid,'amount_total_clp':decimal_text(buyer_amounts[bid]),'order_count':buyer_orders[bid],'source':'CHILECOMPRA_OC_DA','loaded_at':now} for bid in sorted(buyer_amounts)]
    pairs=[]
    for r,buyer,supplier,pair_id,amount,orders in normalized:
        pairs.append({'year':year,'month':month,'pair_id':pair_id,'buyer_id':buyer,'supplier_id':supplier,'order_count':orders,'amount_total_clp':decimal_text(amount),'buyer_amount_total_clp':decimal_text(buyer_amounts[buyer]),'modalities':r.get('modalities') or [],'first_seen':r.get('first_seen'),'last_seen':r.get('last_seen'),'source':'CHILECOMPRA_OC_DA','loaded_at':now})
    return buyers,pairs

def quarantine_record(raw:dict,*,reason:str,source_year:int,source_month:int,stage:str='ROUTE_EVENT')->dict:
    core={'stage':stage,'reason':reason,'source':raw.get('source') or 'CHILECOMPRA','source_year':source_year,'source_month':source_month,'payload':raw}
    return {'quarantine_id':'QEVT-'+h(core)[:28],'stage':stage,'reason':reason,'source':core['source'],'source_year':source_year,'source_month':source_month,'payload':raw,'semantic_hash':h(core),'created_at':datetime.now(timezone.utc).isoformat()}

def normalize_route_event(e:dict,*,source_year:int,source_month:int,now:str)->tuple[dict|None,str|None]:
    event_date=plausible_event_date(e.get('date'));buyer=str(e.get('buyer_id') or '').strip();product=str(e.get('product_key') or '').strip();status=str(e.get('status') or '').strip();order_id=str(e.get('order_id') or '').strip()
    if not event_date:return None,'INVALID_EVENT_DATE'
    if len(buyer)<3:return None,'INVALID_BUYER_ID'
    if not product:return None,'MISSING_PRODUCT_KEY'
    if not status:return None,'MISSING_STATUS'
    if status.upper()=='PURCHASED' and not valid_order_id(order_id):return None,'INVALID_ORDER_ID'
    d=date.fromisoformat(event_date)
    core={'date':event_date,'buyer_id':buyer,'supplier_id':e.get('supplier_id'),'pair_id':e.get('pair_id'),'product_key':product,'status':status,'process_id':e.get('process_id') or e.get('tender_id'),'order_id':order_id or None,'modality':e.get('modality'),'source':e.get('source') or 'CHILECOMPRA'}
    eid='REVT-'+h(core)[:28];payload=dict(e);payload['source_year']=source_year;payload['source_month']=source_month
    return {'event_id':eid,'year':d.year,'month':d.month,'source_year':source_year,'source_month':source_month,'event_date':event_date,'buyer_id':buyer,'supplier_id':e.get('supplier_id'),'pair_id':e.get('pair_id'),'product_key':product,'status':status,'process_id':core['process_id'],'order_id':order_id or None,'modality':e.get('modality'),'source':core['source'],'semantic_hash':h(payload),'payload':payload,'loaded_at':now},None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--history-month',type=Path,required=True);ap.add_argument('--purchase-events',type=Path,required=True);ap.add_argument('--tender-health',type=Path,required=True);ap.add_argument('--tender-events',type=Path,required=True);ap.add_argument('--order-quarantine',type=Path);args=ap.parse_args()
    hist=json.loads(args.history_month.read_text(encoding='utf-8'));th=json.loads(args.tender_health.read_text(encoding='utf-8'));year=int(hist['year']);month=int(hist['month']);now=datetime.now(timezone.utc).isoformat();print(post({'kind':'ping'}))
    buyers,pairs=economic_rows(hist,year,month,now)
    for b in chunks(buyers,800):post({'kind':'buyer_month_batch','rows':b})
    for b in chunks(pairs,800):post({'kind':'pair_month_batch','rows':b})
    oc=hist.get('coverage') or {};lc=th.get('coverage') or {};coverage=[{'source':'CHILECOMPRA_OC_DA','year':year,'month':month,'rows_read':int(oc.get('rows_read') or 0),'orders':int(oc.get('orders') or 0),'identity_coverage':oc.get('identity_coverage'),'amount_coverage':oc.get('clp_amount_coverage'),'detail':oc,'loaded_at':now},{'source':'CHILECOMPRA_LIC_DA','year':year,'month':month,'rows_read':int(lc.get('rows_read') or 0),'orders':int(lc.get('tenders') or 0),'identity_coverage':None,'amount_coverage':None,'detail':lc,'loaded_at':now}];post({'kind':'coverage_batch','rows':coverage})
    quarantine=[];order_quarantine=args.order_quarantine or (args.history_month.parent/'order_quarantine.jsonl.gz')
    for raw in gz_rows(order_quarantine):quarantine.append(quarantine_record(raw.get('payload') or raw,reason=str(raw.get('reason') or 'ORDER_ROW_QUARANTINE'),source_year=year,source_month=month,stage=str(raw.get('stage') or 'ORDER_CSV_ROW')))
    events=[]
    for raw in gz_rows(args.purchase_events)+gz_rows(args.tender_events):
        normalized,reason=normalize_route_event(raw,source_year=year,source_month=month,now=now)
        if reason:quarantine.append(quarantine_record(raw,reason=reason,source_year=year,source_month=month));continue
        events.append(normalized)
    written=0
    for b in chunks(events,ROUTE_BATCH_SIZE):written+=int(post({'kind':'route_event_batch','rows':b}).get('written') or 0)
    qwritten=0
    for b in chunks(quarantine,500):qwritten+=int(post({'kind':'quarantine_event_batch','rows':b}).get('written') or 0)
    period=f'{year:04d}-{month:02d}';post({'kind':'state','row':{'pipeline':'MONTHLY_DATA_'+period.replace('-','_'),'status':'SUCCESS','source_digest':h({'history':hist.get('coverage'),'tender':th.get('coverage')}),'detail':{'period':period,'buyers':len(buyers),'pairs':len(pairs),'route_events':len(events),'route_events_written':written,'route_batch_size':ROUTE_BATCH_SIZE,'transient_retry_attempts':4,'quarantine_events':len(quarantine),'quarantine_events_written':qwritten,'economic_amount_semantics':'DECIMAL_PAIR_RECONCILED','route_partition_semantics':'EVENT_DATE','source_partition_semantics':'CHILECOMPRA_ARCHIVE_MONTH'}}})
    print(json.dumps({'period':period,'buyers':len(buyers),'pairs':len(pairs),'route_events':len(events),'route_events_written':written,'route_batch_size':ROUTE_BATCH_SIZE,'quarantine_events':len(quarantine),'quarantine_events_written':qwritten},ensure_ascii=False))
if __name__=='__main__':main()
