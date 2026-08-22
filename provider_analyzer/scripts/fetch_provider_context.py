#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,time,urllib.parse,urllib.request
from pathlib import Path
from intelligence_fusion.public_integrity_prioritization import detect_alternative_purchase_routes
QUERY_URL=os.environ.get('PROVIDER_ANALYZER_QUERY','https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-query');AUDIENCE='provider-analyzer-ingest';_TOKEN=None;_AT=0.0
def token():
    global _TOKEN,_AT
    if _TOKEN and time.time()-_AT<120:return _TOKEN
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'];sep='&' if '?' in url else '?';req=urllib.request.Request(url+sep+urllib.parse.urlencode({'audience':AUDIENCE}),headers={'Authorization':'bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(req,timeout=30) as r:_TOKEN=json.load(r)['value']
    _AT=time.time();return _TOKEN
def post(body,timeout=180):
    req=urllib.request.Request(QUERY_URL,data=json.dumps(body,separators=(',',':')).encode(),method='POST',headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json','User-Agent':'Provider-Anomaly-Analyzer/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def period(serial):return serial//12,serial%12+1
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--targets',type=Path,required=True);ap.add_argument('--end-year',type=int,required=True);ap.add_argument('--end-month',type=int,required=True);ap.add_argument('--history-output',type=Path,required=True);ap.add_argument('--routes-output',type=Path,required=True);ap.add_argument('--route-months',type=int,default=7);args=ap.parse_args();targets=json.loads(args.targets.read_text(encoding='utf-8'));pairs=targets.get('pair_ids') or [];buyers=targets.get('buyer_ids') or [];end=args.end_year*12+(args.end_month-1);rsy,rsm=period(end-(args.route_months-1))
    hcov=post({'kind':'coverage_query','sources':['CHILECOMPRA_OC_DA'],'start_year':2024,'start_month':1,'end_year':args.end_year,'end_month':args.end_month});rcov=post({'kind':'coverage_query','sources':['CHILECOMPRA_OC_DA','CHILECOMPRA_LIC_DA'],'start_year':rsy,'start_month':rsm,'end_year':args.end_year,'end_month':args.end_month})
    if pairs:hr=post({'kind':'history_query','pair_ids':pairs,'start_year':2024,'start_month':1,'end_year':args.end_year,'end_month':args.end_month})
    else:hr={'ok':True,'histories':{},'rows':0,'pairs':0}
    if buyers:rr=post({'kind':'route_query','buyer_ids':buyers,'start_year':rsy,'start_month':rsm,'end_year':args.end_year,'end_month':args.end_month,'max_rows':50000})
    else:rr={'ok':True,'events':[],'rows':0,'truncated':False}
    if rr.get('truncated'):raise RuntimeError('Route query truncated; review query capacity before prioritizing')
    hc=(hcov.get('sources') or {}).get('CHILECOMPRA_OC_DA') or {};history={'schema':'PROVIDER_ANALYZER_HISTORY_CONTEXT_V1','mode':'SHADOW','coverage':{'status':'LOADED','expected_months':hc.get('expected_months',0),'available_months':hc.get('available_months',0),'month_coverage':hc.get('month_coverage',0),'history_complete':hc.get('complete') is True,'missing_is_not_zero':True},'histories':hr.get('histories') or {},'guardrails':{'history_is_context_not_wrongdoing_probability':True,'missing_is_not_zero':True,'public_integrity_modifies_aml_score':False}}
    routes=detect_alternative_purchase_routes(rr.get('events') or [],days=180);route={'schema':'PROVIDER_ANALYZER_ALTERNATIVE_ROUTES_V1','mode':'SHADOW','coverage':{'expected_months':args.route_months,'coverage_complete':rcov.get('complete') is True,'sources':rcov.get('sources') or {},'events':len(rr.get('events') or []),'route_findings':len(routes),'missing_is_not_zero':True},'findings':routes,'guardrails':{'finding_is_not_wrongdoing_probability':True,'same_buyer_and_product_required':True,'different_process_required':True,'public_integrity_modifies_aml_score':False}}
    args.history_output.parent.mkdir(parents=True,exist_ok=True);args.history_output.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf-8');args.routes_output.parent.mkdir(parents=True,exist_ok=True);args.routes_output.write_text(json.dumps(route,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'pairs':len(history['histories']),'history_coverage':history['coverage']['month_coverage'],'route_events':route['coverage']['events'],'route_findings':len(routes),'route_complete':route['coverage']['coverage_complete']},ensure_ascii=False))
if __name__=='__main__':main()
