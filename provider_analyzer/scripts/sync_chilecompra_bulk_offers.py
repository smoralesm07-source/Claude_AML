#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,shutil,subprocess,tempfile,urllib.parse,urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from intelligence_fusion.sources.chilecompra_bulk_offers import ChileCompraBulkOffersAdapter
from intelligence_fusion.public_procurement_competition import detect_competition

def write(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def jsonl(p,rows):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows),encoding='utf-8')
def allowed_url(url):
    h=(urllib.parse.urlsplit(url).hostname or '').lower()
    return h in {'transparenciachc.blob.core.windows.net'} or h.endswith('.mercadopublico.cl') or h=='mercadopublico.cl' or h.endswith('.chilecompra.cl') or h=='chilecompra.cl'
def download(url,dst):
    if not allowed_url(url):raise ValueError('unexpected bulk download host')
    req=urllib.request.Request(url,headers={'User-Agent':'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req,timeout=180) as r,dst.open('wb') as f:shutil.copyfileobj(r,f)
def extract(src,out):
    out.mkdir(parents=True,exist_ok=True)
    low=src.name.lower()
    if low.endswith('.7z'):
        subprocess.run(['7z','x','-y',str(src),f'-o{out}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    elif low.endswith('.zip'):
        shutil.unpack_archive(str(src),str(out))
    else:shutil.copy2(src,out/src.name)
    csvs=sorted(out.rglob('*.csv'),key=lambda p:p.stat().st_size,reverse=True)
    if not csvs:raise FileNotFoundError('bulk archive contains no CSV')
    return csvs[0]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url');ap.add_argument('--file',type=Path);ap.add_argument('--out',type=Path,default=Path('runtime/provider_analyzer'));ap.add_argument('--lab-out',type=Path,default=Path('runtime/provider_analyzer/bulk_competition.json'));ap.add_argument('--max-rows',type=int,default=250000,help='0 = full source file');args=ap.parse_args()
    url=args.url or os.environ.get('CHILECOMPRA_BULK_LICITACIONES_URL','').strip();now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    if not url and not args.file:
        health={'schema':'PROVIDER_ANALYZER_SOURCE_HEALTH_V1','source_id':'CHILECOMPRA_BULK_OFFERS','generated_at':now,'status':'YELLOW','detail':{'reason':'bulk_url_not_configured'}};write(args.out/'bulk_offers_health.json',health);write(args.lab_out,{'schema':'PROVIDER_ANALYZER_BULK_COMPETITION_V1','generated_at':now,'health':health,'counts':{},'coverage':{},'tenders':[]});print(health);return
    adapter=ChileCompraBulkOffersAdapter();limit=None if args.max_rows<=0 else args.max_rows
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);src=args.file
        if url:
            suffix=Path(urllib.parse.urlsplit(url).path).suffix or '.7z';src=td/f'bulk{suffix}';download(url,src)
        csv_path=extract(src,td/'x') if src.suffix.lower() in ('.7z','.zip') else src
        rows,meta=adapter.read_path(csv_path,limit=limit);tenders=adapter.normalize(rows,meta);signals=detect_competition(tenders);cov=adapter.coverage(tenders,meta)
    cov['sample_limited']=limit is not None;cov['row_limit']=limit
    by=defaultdict(list)
    for s in signals:by[s.get('tender_id')].append(s)
    ranked=[]
    for t in tenders:
        ss=by.get(t.get('tender_id'),[])
        if ss:ranked.append({'tender_id':t.get('tender_id'),'title':t.get('title'),'buyer':(t.get('buyer') or {}).get('name'),'bid_count':len(t.get('bids') or []),'award_count':len(t.get('awards') or []),'signal_types':sorted({s.get('signal_type') for s in ss}),'signals':ss})
    ranked.sort(key=lambda x:(len(x['signal_types']),len(x['signals']),x['bid_count']),reverse=True)
    status='GREEN' if cov.get('tenders') and ('supplier_rut' in cov.get('resolved_columns',[]) or 'supplier_name' in cov.get('resolved_columns',[])) else 'YELLOW'
    health={'schema':'PROVIDER_ANALYZER_SOURCE_HEALTH_V1','source_id':'CHILECOMPRA_BULK_OFFERS','generated_at':now,'status':status,'detail':{'rows_read':len(rows),'signals':len(signals),'coverage':cov,'delimiter':meta.get('delimiter'),'encoding':meta.get('encoding')}}
    jsonl(args.out/'bulk_tenders_latest.jsonl',tenders);jsonl(args.out/'bulk_competition_signals_latest.jsonl',signals);write(args.out/'bulk_offers_health.json',health)
    write(args.lab_out,{'schema':'PROVIDER_ANALYZER_BULK_COMPETITION_V1','generated_at':now,'health':health,'counts':{'rows_read':len(rows),'tenders_scanned':len(tenders),'signals':len(signals),'flagged_tenders':len(ranked)},'coverage':cov,'tenders':ranked[:150],'guardrails':{'price_difference_is_not_wrongdoing':True,'award_may_use_non_price_criteria':True,'human_review_required':True,'public_integrity_modifies_aml_score':False}})
    print({'rows':len(rows),'tenders':len(tenders),'signals':len(signals),'flagged':len(ranked),'coverage':cov})
if __name__=='__main__':main()
