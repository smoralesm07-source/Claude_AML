#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EDGE_URL=os.environ.get('PROVIDER_ANALYZER_INGEST','https://bzqxvidggykkdouotylg.supabase.co/functions/v1/provider-analyzer-ingest')
AUDIENCE='provider-analyzer-ingest';_TOKEN=None;_AT=0.0


def token():
    global _TOKEN,_AT
    if _TOKEN and time.time()-_AT<120:return _TOKEN
    url=os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'];sep='&' if '?' in url else '?'
    req=urllib.request.Request(url+sep+urllib.parse.urlencode({'audience':AUDIENCE}),headers={'Authorization':'bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']})
    with urllib.request.urlopen(req,timeout=30) as r:_TOKEN=json.load(r)['value']
    _AT=time.time();return _TOKEN


def post(body,timeout=180):
    req=urllib.request.Request(EDGE_URL,data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode(),method='POST',headers={'Authorization':'Bearer '+token(),'Content-Type':'application/json','User-Agent':'Provider-Anomaly-Analyzer/1.1'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)


def canonical_json(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(obj):return hashlib.sha256(canonical_json(obj).encode()).hexdigest()
def stable_id(prefix:str,*parts:object)->str:
    raw='|'.join(str(x or '') for x in parts).encode()
    return f'{prefix}-{hashlib.sha256(raw).hexdigest()[:24].upper()}'
def lines(path:Path)->list[dict]:return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
def chunks(rows,n):
    for i in range(0,len(rows),n):yield rows[i:i+n]


def build_rows(signals:list[dict],evidence:list[dict],period:str,updated_at:str)->list[dict]:
    signal_by_evidence={stable_id('EVD-PA',str(s.get('signal_id') or ''),period):str(s.get('signal_id') or '') for s in signals if s.get('signal_id')}
    rows=[]
    for e in evidence:
        evidence_id=str(e.get('evidence_id') or '')
        signal_id=signal_by_evidence.get(evidence_id)
        if not evidence_id or not signal_id:
            raise ValueError(f'UNMATCHED_CANONICAL_EVIDENCE:{evidence_id}')
        rows.append({'evidence_id':evidence_id,'signal_id':signal_id,'evidence_type':'PROCUREMENT_REVIEW_DERIVATION','source_url':e.get('source_url'),'payload':e,'semantic_hash':sha(e),'updated_at':updated_at})
    if len(rows)!=len(signal_by_evidence):
        raise ValueError(f'EVIDENCE_SIGNAL_COUNT_MISMATCH:{len(rows)}!={len(signal_by_evidence)}')
    return rows


def main():
    ap=argparse.ArgumentParser(description='Persist canonical provider evidence after signals have been materialized.')
    ap.add_argument('--signals',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True)
    ap.add_argument('--period',required=True)
    args=ap.parse_args()
    signals=lines(args.signals);evidence=lines(args.evidence);now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    rows=build_rows(signals,evidence,args.period,now);written=0
    for batch in chunks(rows,400):written+=int(post({'kind':'evidence_batch','rows':batch}).get('written') or 0)
    print(json.dumps({'period':args.period,'evidence':len(rows),'evidence_written':written},ensure_ascii=False))


if __name__=='__main__':main()
