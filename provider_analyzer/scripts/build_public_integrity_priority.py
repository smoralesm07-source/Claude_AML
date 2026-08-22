#!/usr/bin/env python3
from __future__ import annotations
import argparse,gzip,json
from pathlib import Path
from intelligence_fusion.public_integrity_prioritization import build_provider_buyer_history,detect_alternative_purchase_routes,prioritize_review_cases

def read_text(p:Path)->str:
    if p.name.endswith('.gz'):
        with gzip.open(p,'rt',encoding='utf-8') as fh:return fh.read()
    return p.read_text(encoding='utf-8')
def load(path:str|None):
    if not path:return []
    p=Path(path)
    if not p.exists():return []
    text=read_text(p).strip()
    if not text:return []
    if p.name.endswith('.jsonl') or p.name.endswith('.jsonl.gz'):return [json.loads(x) for x in text.splitlines() if x.strip()]
    data=json.loads(text)
    if isinstance(data,list):return data
    for key in ('signals','orders','events','findings','rows','items'):
        if isinstance(data.get(key),list):return data[key]
    return []
def load_history_bundle(path:str|None)->tuple[dict,dict]:
    if not path:return {},{'status':'NOT_LOADED','missing_is_not_zero':True}
    p=Path(path)
    if not p.exists():return {},{'status':'NOT_FOUND','path':str(p),'missing_is_not_zero':True}
    data=json.loads(read_text(p));histories=data.get('histories') if isinstance(data,dict) else None;coverage=data.get('coverage') if isinstance(data,dict) else None
    if not isinstance(histories,dict):return {},{'status':'INVALID','path':str(p),'missing_is_not_zero':True}
    cov={'status':'LOADED',**(coverage or {}),'missing_is_not_zero':True};return histories,cov
def load_route_bundle(path:str|None)->tuple[list,dict]:
    if not path:return [],{'status':'NOT_LOADED','missing_is_not_zero':True}
    p=Path(path)
    if not p.exists():return [],{'status':'NOT_FOUND','path':str(p),'missing_is_not_zero':True}
    try:data=json.loads(read_text(p))
    except (json.JSONDecodeError,OSError):return [],{'status':'INVALID','path':str(p),'missing_is_not_zero':True}
    if isinstance(data,list):return data,{'status':'LOADED','records':len(data),'missing_is_not_zero':True}
    findings=data.get('findings') if isinstance(data,dict) else None
    if not isinstance(findings,list):return [],{'status':'INVALID','path':str(p),'missing_is_not_zero':True}
    cov={'status':'LOADED',**(data.get('coverage') or {}),'records':len(findings),'missing_is_not_zero':True};return findings,cov
def history_priority_eligible(cov:dict,min_coverage:float)->bool:
    if cov.get('status')!='LOADED':return False
    value=cov.get('month_coverage')
    try:value=float(value)
    except (TypeError,ValueError):return False
    return value>=min_coverage

def main():
    ap=argparse.ArgumentParser(description='Build explainable provider review priorities (SHADOW only).');ap.add_argument('--signals',required=True);ap.add_argument('--histories');ap.add_argument('--routes');ap.add_argument('--as-of');ap.add_argument('--years',type=int,default=5);ap.add_argument('--min-history-coverage',type=float,default=.80);ap.add_argument('--output',required=True);args=ap.parse_args();signals=load(args.signals);history_context,history_coverage=load_history_bundle(args.histories);routes,route_coverage=load_route_bundle(args.routes);use_history=history_priority_eligible(history_coverage,args.min_history_coverage);history_coverage['priority_eligible']=use_history;history_coverage['min_required_coverage']=args.min_history_coverage;histories_for_priority=history_context if use_history else {};ranked=prioritize_review_cases(signals,histories_for_priority,routes)
    for row in ranked:
        key=str(row.get('review_key') or '');ctx=history_context.get(key) or {};row['history_context']=ctx;row['history_used_for_priority']=bool(use_history and ctx)
        if ctx and not row['history_used_for_priority']:row['history_context_guardrail']='Contexto histórico parcial; se muestra pero no aporta puntos a la prioridad.'
    out={'schema':'PROVIDER_ANALYZER_REVIEW_PRIORITY_V1','mode':'SHADOW','as_of':args.as_of,'window_years':args.years,'coverage':{'history':history_coverage,'routes':route_coverage},'counts':{'signals':len(signals),'pair_histories_context':len(history_context),'pair_histories_used_for_priority':len(histories_for_priority),'alternative_routes':len(routes),'review_cases':len(ranked)},'review_cases':ranked,'guardrails':{'review_priority_is_not_wrongdoing_probability':True,'partial_history_does_not_increase_priority':True,'history_missing_does_not_mean_no_relationship':True,'route_is_not_wrongdoing_probability':True,'public_integrity_modifies_aml_score':False,'missing_is_not_zero':True}}
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'review_cases':len(ranked),'high':sum(1 for x in ranked if x['tier']=='HIGH'),'medium':sum(1 for x in ranked if x['tier']=='MEDIUM'),'routes':len(routes),'history_priority_eligible':use_history},ensure_ascii=False))
if __name__=='__main__':main()
