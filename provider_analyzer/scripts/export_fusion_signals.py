#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,time,urllib.parse,urllib.request
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
def sha(obj):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def lines(path):return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def chunks(rows,n):
    for i in range(0,len(rows),n):yield rows[i:i+n]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--signals',type=Path,required=True);ap.add_argument('--priority',type=Path,required=True);ap.add_argument('--period',required=True);ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args();signals=lines(args.signals);priority=json.loads(args.priority.read_text(encoding='utf-8'));by={str(x.get('review_key') or ''):x for x in priority.get('review_cases') or []};run_id=os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S');export=[];db=[]
    for s in signals:
        pair=str(s.get('provider_buyer_pair_id') or s.get('pair_id') or '');p=by.get(pair) or {};row={'signal_id':str(s.get('signal_id')),'signal_type':str(s.get('signal_type') or 'UNKNOWN'),'semantic_class':'INTEGRITY_REVIEW','supplier_id':s.get('supplier_id'),'buyer_id':s.get('buyer_id'),'pair_id':pair or None,'period':args.period,'review_priority':p.get('review_priority'),'review_tier':p.get('tier'),'evidence_count':len(s.get('evidence_ids') or []),'source_system':'PROVIDER_ANALYZER','source_ref':f'Claude_AML/provider_analyzer/exports/{args.period}','scoring_eligible':False,'risk_effect':'CONTEXT','reason':s.get('reason'),'metrics':s.get('metrics') or {},'guardrails':{'signal_is_not_wrongdoing_probability':True,'review_priority_is_not_aml_risk_score':True,'public_integrity_modifies_aml_score':False}};export.append(row);db_payload={**row,'raw_signal':s};db.append({'signal_id':row['signal_id'],'signal_type':row['signal_type'],'period':args.period,'supplier_id':row['supplier_id'],'buyer_id':row['buyer_id'],'pair_id':row['pair_id'],'review_priority':row['review_priority'],'severity_band':row['review_tier'],'scoring_eligible':False,'risk_effect':'CONTEXT','evidence_count':row['evidence_count'],'payload':db_payload,'semantic_hash':sha(db_payload),'source_run_id':str(run_id)})
    export.sort(key=lambda x:(-(float(x.get('review_priority') or 0)),x['signal_id']));args.output_dir.mkdir(parents=True,exist_ok=True);jsonl=''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in export);(args.output_dir/'provider_signals_v1.jsonl').write_text(jsonl,encoding='utf-8');content_hash=hashlib.sha256(jsonl.encode()).hexdigest();manifest={'schema':'PROVIDER_ANALYZER_EXPORT_V1','generated_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'period':args.period,'signal_count':len(export),'content_sha256':content_hash,'source_system':'PROVIDER_ANALYZER','contract':{'semantic_class':'INTEGRITY_REVIEW','scoring_eligible':False,'risk_effect':'CONTEXT'},'guardrails':{'contains_no_raw_procurement_dataset':True,'signal_is_not_wrongdoing_probability':True,'review_priority_is_not_aml_risk_score':True,'fusion_may_use_as_context_only':True}};(args.output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for b in chunks(db,400):post({'kind':'signal_batch','rows':b})
    post({'kind':'export_batch','row':{'export_id':f'{args.period}:{content_hash[:20]}','schema_version':'PROVIDER_ANALYZER_EXPORT_V1','source_run_id':str(run_id),'signal_count':len(export),'content_sha256':content_hash,'status':'READY','detail':manifest}});post({'kind':'state','row':{'pipeline':'LATEST_EXPORT','status':'SUCCESS','source_digest':content_hash,'detail':manifest}});print(json.dumps({'period':args.period,'signals':len(export),'sha256':content_hash},ensure_ascii=False))
if __name__=='__main__':main()
