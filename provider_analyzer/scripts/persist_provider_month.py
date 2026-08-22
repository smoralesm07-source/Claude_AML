#!/usr/bin/env python3
from __future__ import annotations
import argparse,gzip,hashlib,json,os,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
EDGE_URL=os.environ.get('PROVIDER_ANALYZER_INGEST','https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest');AUDIENCE='provider-analyzer-ingest';_TOKEN=None;_AT=0.0
def token():
    global _TOKEN,_AT
    if _TOKEN and time.time()-_AT<120:return _TOKEN
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'];sep='&' if '?' in url else '?';req=urllib.request.Request(url+sep+urllib.parse.urlencode({'audience':AUDIENCE}),headers={'Authorization':'bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(req,timeout=30) as r:_TOKEN=json.load(r)['value']
    _AT=time.time();return _TOKEN
def post(body,timeout=180):
    req=urllib.request.Request(EDGE_URL,data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode(),method='POST',headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json','User-Agent':'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def chunks(rows,n):
    for i in range(0,len(rows),n):yield rows[i:i+n]
def h(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def gz_rows(path:Path):
    if not path.exists():return []
    with gzip.open(path,'rt',encoding='utf-8') as fh:return [json.loads(x) for x in fh if x.strip()]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--history-month',type=Path,required=True);ap.add_argument('--purchase-events',type=Path,required=True);ap.add_argument('--tender-health',type=Path,required=True);ap.add_argument('--tender-events',type=Path,required=True);args=ap.parse_args();hist=json.loads(args.history_month.read_text(encoding='utf-8'));th=json.loads(args.tender_health.read_text(encoding='utf-8'));year=int(hist['year']);month=int(hist['month']);now=datetime.now(timezone.utc).isoformat();print(post({'kind':'ping'}))
    buyers=[{'year':year,'month':month,'buyer_id':bid,'amount_total_clp':float(amt or 0),'order_count':int((hist.get('buyer_order_counts') or {}).get(bid) or 0),'source':'CHILECOMPRA_OC_DA','loaded_at':now} for bid,amt in (hist.get('buyer_totals_clp') or {}).items()]
    pairs=[]
    for r in hist.get('pairs') or []:pairs.append({'year':year,'month':month,'pair_id':r['pair_id'],'buyer_id':r['buyer_id'],'supplier_id':r['supplier_id'],'order_count':int(r.get('order_count') or 0),'amount_total_clp':float(r.get('amount_total_clp') or 0),'buyer_amount_total_clp':float(r.get('buyer_amount_total_clp') or 0),'modalities':r.get('modalities') or [],'first_seen':r.get('first_seen'),'last_seen':r.get('last_seen'),'source':'CHILECOMPRA_OC_DA','loaded_at':now})
    for b in chunks(buyers,800):post({'kind':'buyer_month_batch','rows':b})
    for b in chunks(pairs,800):post({'kind':'pair_month_batch','rows':b})
    oc=hist.get('coverage') or {};lc=th.get('coverage') or {};coverage=[{'source':'CHILECOMPRA_OC_DA','year':year,'month':month,'rows_read':int(oc.get('rows_read') or 0),'orders':int(oc.get('orders') or 0),'identity_coverage':oc.get('identity_coverage'),'amount_coverage':oc.get('clp_amount_coverage'),'detail':oc,'loaded_at':now},{'source':'CHILECOMPRA_LIC_DA','year':year,'month':month,'rows_read':int(lc.get('rows_read') or 0),'orders':int(lc.get('tenders') or 0),'identity_coverage':None,'amount_coverage':None,'detail':lc,'loaded_at':now}];post({'kind':'coverage_batch','rows':coverage})
    events=[]
    for e in gz_rows(args.purchase_events)+gz_rows(args.tender_events):
        event_date=str(e.get('date') or '')[:10];buyer=str(e.get('buyer_id') or '').strip();product=str(e.get('product_key') or '').strip();status=str(e.get('status') or '').strip()
        if not event_date or not buyer or not product or not status:continue
        core={'date':event_date,'buyer_id':buyer,'supplier_id':e.get('supplier_id'),'pair_id':e.get('pair_id'),'product_key':product,'status':status,'process_id':e.get('process_id') or e.get('tender_id'),'order_id':e.get('order_id'),'modality':e.get('modality'),'source':e.get('source') or 'CHILECOMPRA'};eid='REVT-'+h(core)[:28];events.append({'event_id':eid,'year':year,'month':month,'event_date':event_date,'buyer_id':buyer,'supplier_id':e.get('supplier_id'),'pair_id':e.get('pair_id'),'product_key':product,'status':status,'process_id':core['process_id'],'order_id':e.get('order_id'),'modality':e.get('modality'),'source':core['source'],'semantic_hash':h(e),'payload':e,'loaded_at':now})
    written=0
    for b in chunks(events,400):written+=int(post({'kind':'route_event_batch','rows':b}).get('written') or 0)
    period=f'{year:04d}-{month:02d}';post({'kind':'state','row':{'pipeline':'MONTHLY_DATA_'+period.replace('-','_'),'status':'SUCCESS','source_digest':h({'history':hist.get('coverage'),'tender':th.get('coverage')}),'detail':{'period':period,'buyers':len(buyers),'pairs':len(pairs),'route_events':len(events),'route_events_written':written}}})
    print(json.dumps({'period':period,'buyers':len(buyers),'pairs':len(pairs),'route_events':len(events),'route_events_written':written},ensure_ascii=False))
if __name__=='__main__':main()
