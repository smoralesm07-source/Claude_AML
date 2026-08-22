#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
def read_json(path:Path)->dict:return json.loads(path.read_text(encoding='utf-8'))
def read_jsonl(path:Path)->list[dict]:return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--signals',type=Path,required=True);ap.add_argument('--source-health',type=Path,required=True);ap.add_argument('--targets',type=Path,required=True);ap.add_argument('--history',type=Path,required=True);ap.add_argument('--routes',type=Path,required=True);ap.add_argument('--priority',type=Path,required=True);ap.add_argument('--period',required=True);ap.add_argument('--as-of',required=True);ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args();signals=read_jsonl(args.signals);health=read_json(args.source_health);targets=read_json(args.targets);history=read_json(args.history);routes=read_json(args.routes);priority=read_json(args.priority);source_cov=((health.get('detail') or {}).get('coverage') or {});hc=history.get('coverage') or {};rc=routes.get('coverage') or {};signal_complete=bool(source_cov.get('sample_limited') is False and source_cov.get('tenders'));operational=signal_complete and hc.get('history_complete') is True and rc.get('coverage_complete') is True
    by_pair=defaultdict(list)
    for s in signals:
        key=str(s.get('provider_buyer_pair_id') or s.get('pair_id') or '')
        if key:by_pair[key].append(s)
    cases=[]
    for row in (priority.get('review_cases') or [])[:100]:
        ss=by_pair.get(str(row.get('review_key') or ''),[]);first=ss[0] if ss else {};metrics=[s.get('metrics') or {} for s in ss];cases.append({**row,'buyer_id':first.get('buyer_id'),'buyer_name':first.get('buyer_name'),'supplier_id':first.get('supplier_id'),'tender_ids':sorted({str(s.get('tender_id')) for s in ss if s.get('tender_id')}),'review_reasons':[s.get('reason') for s in ss if s.get('reason')][:5],'max_ratio':max([float(m.get('max_ratio')) for m in metrics if m.get('max_ratio') is not None],default=None)})
    current={'schema':'PROVIDER_ANALYZER_LIVE_V1','mode':'SHADOW','operational_status':'OPERATIONAL_SHADOW' if operational else 'PARTIAL_SHADOW','period':args.period,'as_of':args.as_of,'signal_coverage':source_cov,'history_coverage':hc,'route_coverage':rc,'targets':targets.get('counts'),'counts':priority.get('counts'),'top_review_cases':cases,'guardrails':{'review_priority_is_not_wrongdoing_probability':True,'anomaly_signal_is_not_illicitness':True,'public_integrity_modifies_aml_score':False,'missing_is_not_zero':True}}
    status={'schema':'PROVIDER_ANALYZER_STATUS_V1','operational':operational,'mode':'SHADOW','period':args.period,'signals':len(signals),'target_pairs':(targets.get('counts') or {}).get('provider_buyer_pairs'),'review_cases':len(cases),'alternative_routes':(priority.get('counts') or {}).get('alternative_routes',0),'history_coverage':hc.get('month_coverage'),'route_coverage_complete':rc.get('coverage_complete')}
    args.output_dir.mkdir(parents=True,exist_ok=True);(args.output_dir/'current_priority.json').write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8');(args.output_dir/'analyzer_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(status,ensure_ascii=False))
if __name__=='__main__':main()
