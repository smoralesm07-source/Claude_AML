#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,json,shutil,tempfile,urllib.parse,urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from intelligence_fusion.public_integrity_routes import derive_tender_negative_events
from intelligence_fusion.sources.chilecompra_bulk_offers import ChileCompraBulkOffersAdapter
from intelligence_fusion.sources.common import clean_rut,norm_text
ALLOWED_HOST='transparenciachc.blob.core.windows.net';ALLOWED_PREFIX='/lic-da/'
def download(url:str,dst:Path)->None:
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or (p.hostname or '').lower()!=ALLOWED_HOST or not p.path.startswith(ALLOWED_PREFIX):raise ValueError('unexpected bulk tenders URL')
    req=urllib.request.Request(url,headers={'User-Agent':'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req,timeout=300) as r,dst.open('wb') as f:shutil.copyfileobj(r,f)
def encoding_for(path:Path)->str:
    raw=path.open('rb').read(65536)
    try:raw.decode('utf-8-sig');return 'utf-8-sig'
    except UnicodeDecodeError:return 'latin-1'
def get(row:dict,mapping:dict,key:str):
    col=mapping.get(key);return row.get(col) if col else None
def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument('--url',required=True);ap.add_argument('--year',type=int,required=True);ap.add_argument('--month',type=int,required=True);ap.add_argument('--output-dir',type=Path,default=Path('runtime/provider_analyzer/tender_route_month'));args=ap.parse_args()
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True);adapter=ChileCompraBulkOffersAdapter();now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);archive=td/'tenders.zip';extract=td/'x';download(args.url,archive);shutil.unpack_archive(str(archive),str(extract));csvs=sorted(extract.rglob('*.csv'),key=lambda p:p.stat().st_size,reverse=True)
        if not csvs:raise FileNotFoundError('bulk tender archive contains no CSV')
        src=csvs[0];enc=encoding_for(src)
        with src.open('r',encoding=enc,newline='') as fh:
            sample=fh.read(12000);fh.seek(0);dialect=adapter.sniff(sample);reader=csv.DictReader(fh,dialect=dialect);m=adapter.resolve_columns(reader.fieldnames);tenders={};rows_read=0
            for row in reader:
                rows_read+=1;buyer_id=clean_rut(get(row,m,'buyer_rut')) or norm_text(get(row,m,'buyer_name'));tid=str(get(row,m,'tender_id') or '').strip()
                if not tid:continue
                t=tenders.setdefault(tid,{'tender_id':tid,'status':'','buyer_id':'','published_at':'','closed_at':'','awarded_at':'','modality':'','has_selected_evidence':False,'lines':defaultdict(lambda:{'product_code':'','item_id':'','bidders':set(),'selected':False})})
                t['status']=t['status'] or str(get(row,m,'status') or '');t['buyer_id']=t['buyer_id'] or buyer_id;t['published_at']=t['published_at'] or str(get(row,m,'published_at') or '');t['closed_at']=t['closed_at'] or str(get(row,m,'closed_at') or '');t['awarded_at']=t['awarded_at'] or str(get(row,m,'awarded_at') or '');t['modality']=t['modality'] or str(get(row,m,'modality') or '')
                product=norm_text(get(row,m,'product_code'));item_id=str(get(row,m,'item_id') or '').strip()
                if not product:continue
                line_key=f'{item_id}::{product}' if item_id else product;line=t['lines'][line_key];line['product_code']=product;line['item_id']=item_id;sid=clean_rut(get(row,m,'supplier_rut')) or norm_text(get(row,m,'supplier_name'))
                if sid:line['bidders'].add(sid)
                selected='selected_offer' in m and adapter._truthy(get(row,m,'selected_offer'))
                if selected:line['selected']=True;t['has_selected_evidence']=True
    events,stats=derive_tender_negative_events(tenders);event_path=out/'tender_negative_events.jsonl.gz'
    with gzip.open(event_path,'wt',encoding='utf-8') as fh:
        for e in sorted(events,key=lambda x:(x['date'],x['tender_id'],x.get('line') or '',x['product_key'])):fh.write(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n')
    health={'schema':'PROVIDER_ANALYZER_TENDER_ROUTE_MONTH_V1','generated_at':now,'mode':'SHADOW','year':args.year,'month':args.month,'source_url':args.url,'coverage':{'rows_read':rows_read,'tenders':len(tenders),**stats,'resolved_columns':sorted(m.keys()),'raw_column_count':len(reader.fieldnames or []),'source_month_fully_scanned':True},'guardrails':{'exact_product_code_required':True,'awarded_tender_requires_explicit_selected_offer_evidence':True,'missing_award_evidence_is_not_non_award':True,'public_integrity_modifies_aml_score':False,'missing_is_not_zero':True}}
    (out/'health.json').write_text(json.dumps(health,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'year':args.year,'month':args.month,'rows':rows_read,'tenders':len(tenders),'negative_events':len(events),'skipped_no_award_evidence':stats['skipped_awarded_tenders_without_selected_offer_evidence']},ensure_ascii=False))
if __name__=='__main__':main()
