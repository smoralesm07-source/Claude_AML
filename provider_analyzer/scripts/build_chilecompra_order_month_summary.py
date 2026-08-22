#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,json,shutil,tempfile,urllib.parse,urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from intelligence_fusion.sources.chilecompra_bulk_orders import ChileCompraBulkOrdersAdapter
from intelligence_fusion.sources.common import as_float,clean_rut,date_iso,norm_text

ALLOWED_HOST='transparenciachc.blob.core.windows.net';ALLOWED_PREFIX='/oc-da/'

def download(url:str,dst:Path):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or (p.hostname or '').lower()!=ALLOWED_HOST or not p.path.startswith(ALLOWED_PREFIX):raise ValueError('unexpected bulk orders URL')
    req=urllib.request.Request(url,headers={'User-Agent':'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req,timeout=300) as r,dst.open('wb') as f:shutil.copyfileobj(r,f)

def encoding_for(path:Path)->str:
    raw=path.open('rb').read(65536)
    try:raw.decode('utf-8-sig');return 'utf-8-sig'
    except UnicodeDecodeError:return 'latin-1'

def product_key(row:dict,m:dict)->str:
    def get(k):return row.get(m.get(k)) if m.get(k) else None
    code=norm_text(get('product_code'))
    if code:return 'CODE:'+code
    text=norm_text(get('product_name') or get('description')).lower()
    return 'TEXT:'+text if text else ''

def party_id(rut,name):return clean_rut(rut) or norm_text(name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',required=True);ap.add_argument('--year',type=int,required=True);ap.add_argument('--month',type=int,required=True);ap.add_argument('--output-dir',type=Path,default=Path('runtime/provider_analyzer/order_history_month'));ap.add_argument('--max-rows',type=int,default=0);args=ap.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True);adapter=ChileCompraBulkOrdersAdapter();now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);archive=td/'orders.zip';extract=td/'x';download(args.url,archive);shutil.unpack_archive(str(archive),str(extract));csvs=sorted(extract.rglob('*.csv'),key=lambda p:p.stat().st_size,reverse=True)
        if not csvs:raise FileNotFoundError('bulk order archive contains no CSV')
        src=csvs[0];enc=encoding_for(src)
        with src.open('r',encoding=enc,newline='') as fh:
            sample=fh.read(12000);fh.seek(0);dialect=adapter.sniff(sample);reader=csv.DictReader(fh,dialect=dialect);m=adapter.resolve_columns(reader.fieldnames);orders={};events={};rows_read=0;unparsed_dates=0
            def get(row,k):return row.get(m.get(k)) if m.get(k) else None
            for row in reader:
                rows_read+=1
                if args.max_rows and rows_read>args.max_rows:break
                bid=party_id(get(row,'buyer_rut'),get(row,'buyer_name'));oid=str(get(row,'order_id') or '').strip()
                if not oid:continue
                o=orders.setdefault(oid,{'order_id':oid,'buyer_id':'','supplier_id':'','date':'','amount_clp':0.0,'modality':'','status':'','tender_id':''})
                sid=party_id(get(row,'supplier_rut'),get(row,'supplier_name'))
                if bid:o['buyer_id']=bid
                if sid:o['supplier_id']=sid
                raw_date=get(row,'accepted_at') or get(row,'modified_at') or get(row,'created_at') or ''
                if not o['date'] and raw_date:
                    parsed=date_iso(raw_date)
                    if parsed:o['date']=parsed
                    else:unparsed_dates+=1
                clp=as_float(get(row,'total_amount_clp'));raw=as_float(get(row,'total_amount'))
                if clp not in (None,0):o['amount_clp']=float(clp)
                elif raw not in (None,0) and str(get(row,'currency') or '').strip().upper() in {'CLP','PESO CHILENO','PESOS CHILENOS','$'}:o['amount_clp']=float(raw)
                o['modality']=o['modality'] or str(get(row,'modality') or '');o['status']=o['status'] or str(get(row,'status') or '');o['tender_id']=o['tender_id'] or str(get(row,'tender_id') or '')
                pk=product_key(row,m)
                if pk:events[(oid,pk)]={'order_id':oid,'product_key':pk}
    buyer_totals=defaultdict(float);buyer_orders=defaultdict(int);pairs={};identified_orders=0;amount_orders=0
    for o in orders.values():
        if o['buyer_id']:buyer_totals[o['buyer_id']]+=o['amount_clp'];buyer_orders[o['buyer_id']]+=1
        if o['amount_clp']>0:amount_orders+=1
        if not o['buyer_id'] or not o['supplier_id']:continue
        identified_orders+=1;key=f"{o['supplier_id']}::{o['buyer_id']}";p=pairs.setdefault(key,{'pair_id':key,'buyer_id':o['buyer_id'],'supplier_id':o['supplier_id'],'order_count':0,'amount_total_clp':0.0,'modalities':set(),'first_seen':None,'last_seen':None})
        p['order_count']+=1;p['amount_total_clp']+=o['amount_clp']
        if o['modality']:p['modalities'].add(o['modality'])
        d=o['date'] or None
        if d:p['first_seen']=d if p['first_seen'] is None or d<p['first_seen'] else p['first_seen'];p['last_seen']=d if p['last_seen'] is None or d>p['last_seen'] else p['last_seen']
    pair_rows=[]
    for p in pairs.values():
        bt=buyer_totals.get(p['buyer_id'],0.0);p['buyer_amount_total_clp']=bt;p['buyer_share_month']=p['amount_total_clp']/bt if bt else None;p['modalities']=sorted(p['modalities']);p['year']=args.year;p['month']=args.month;pair_rows.append(p)
    pair_rows.sort(key=lambda x:(-x['amount_total_clp'],x['pair_id']))
    ev_path=out/'purchase_events.jsonl.gz'
    with gzip.open(ev_path,'wt',encoding='utf-8') as fh:
        for (oid,pk),_ in events.items():
            o=orders.get(oid) or {}
            if not o.get('buyer_id') or not o.get('supplier_id') or not o.get('date'):continue
            status=norm_text(o.get('status')).lower()
            if any(x in status for x in ('cancel','anulad','rechaz')):continue
            record={'buyer_id':o['buyer_id'],'supplier_id':o['supplier_id'],'pair_id':f"{o['supplier_id']}::{o['buyer_id']}",'product_key':pk,'date':o.get('date'),'status':'PURCHASED','order_id':oid,'tender_id':o.get('tender_id'),'process_id':o.get('tender_id') or oid,'modality':o.get('modality'),'source':'MERCADO_PUBLICO_BULK_ORDERS'}
            fh.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
    sample_limited=bool(args.max_rows)
    summary={'schema':'PROVIDER_ANALYZER_ORDER_HISTORY_MONTH_V1','generated_at':now,'mode':'SHADOW','year':args.year,'month':args.month,'source_url':args.url,'coverage':{'rows_read':rows_read,'orders':len(orders),'orders_with_buyer_and_supplier':identified_orders,'identity_coverage':round(identified_orders/max(len(orders),1),6),'orders_with_clp_amount':amount_orders,'clp_amount_coverage':round(amount_orders/max(len(orders),1),6),'pair_count':len(pair_rows),'purchase_event_keys':len(events),'unparsed_date_rows':unparsed_dates,'sample_limited':sample_limited,'source_month_fully_scanned':not sample_limited},'buyer_totals_clp':dict(buyer_totals),'buyer_order_counts':dict(buyer_orders),'pairs':pair_rows,'guardrails':{'historical_concentration_is_not_wrongdoing_probability':True,'missing_is_not_zero':True,'amounts_use_clp_when_available':True,'dates_normalized_iso':True,'public_integrity_modifies_aml_score':False}}
    (out/'history_month.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'year':args.year,'month':args.month,'rows':rows_read,'orders':len(orders),'identity_coverage':summary['coverage']['identity_coverage'],'clp_amount_coverage':summary['coverage']['clp_amount_coverage'],'pairs':len(pair_rows),'unparsed_date_rows':unparsed_dates},ensure_ascii=False))

if __name__=='__main__':main()
