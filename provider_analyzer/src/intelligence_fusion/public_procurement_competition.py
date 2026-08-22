from __future__ import annotations
from collections import defaultdict
from statistics import median
from .sources.common import event_id
from .public_integrity_prioritization import assess_comparability

RULES={
 'INT-PB-002':'Oferta económicamente desbalanceada frente a pares',
 'INT-PB-005':'Adjudicación con tratamiento económico diferencial frente a pares',
}

def _sig(rule,tender_id,supplier_id,reason,metrics,evidence=None,buyer_id=None,buyer_name=None):
    tender_pair=f'{supplier_id}::{tender_id}'
    provider_buyer_pair=f'{supplier_id}::{buyer_id}' if supplier_id and buyer_id else None
    return {'signal_id':event_id('SIG-INT',rule,tender_pair),'signal_type':rule,'semantic_class':'INTEGRITY_REVIEW','scope':'SUPPLIER_TENDER','tender_id':tender_id,'supplier_id':supplier_id,'buyer_id':buyer_id,'buyer_name':buyer_name,'provider_buyer_pair_id':provider_buyer_pair,'evidence_ids':evidence or [],'reason':reason,'metrics':metrics,'scoring_eligible':False,'risk_effect':'NONE'}

def detect_competition(tenders:list[dict])->list[dict]:
    out=[]
    for t in tenders:
        tid=t.get('tender_id') or t.get('ocid') or ''
        buyer=t.get('buyer') or {}; buyer_id=buyer.get('id') or buyer.get('name') or ''; buyer_name=buyer.get('name')
        line_prices=defaultdict(list); line_observations=defaultdict(list)
        for b in t.get('bids') or []:
            sid=b.get('supplier_id') or b.get('supplier_name') or ''
            for it in b.get('items') or []:
                iid=it.get('item_id'); p=it.get('unit_price')
                if iid and p not in (None,0):
                    line_prices[iid].append((sid,float(p)))
                    line_observations[iid].append({**it,'supplier_id':sid})
        line_quality={iid:assess_comparability(rows) for iid,rows in line_observations.items()}
        med={iid:median([p for _,p in vals]) for iid,vals in line_prices.items() if len({s for s,_ in vals})>=3}
        for b in t.get('bids') or []:
            sid=b.get('supplier_id') or b.get('supplier_name') or ''
            ratios=[]
            for it in b.get('items') or []:
                iid=it.get('item_id'); p=it.get('unit_price'); m=med.get(iid)
                if iid and p and m: ratios.append((iid,float(p)/m,float(p),m))
            if len(ratios)>=2:
                lo=min(r[1] for r in ratios); hi=max(r[1] for r in ratios)
                if hi>=2.5 and lo<=0.60 and hi/max(lo,0.01)>=5:
                    qualities=[line_quality.get(i,{}) for i,_,_,_ in ratios]
                    ic=median([q.get('comparability_index',0) for q in qualities]) if qualities else 0
                    flags=sorted({f for q in qualities for f in q.get('data_quality_flags',[])})
                    band='INTERPRETABLE' if ic>=80 else 'REVIEW_DATA' if ic>=60 else 'DATA_QUALITY'
                    metrics={'max_ratio':hi,'min_ratio':lo,'spread':hi/max(lo,0.01),'lines':[{'item_id':i,'ratio':r,'unit_price':p,'peer_median':m,'comparability':line_quality.get(i)} for i,r,p,m in ratios],
                             'comparability_index':round(ic,1),'comparability_band':band,'data_quality_flags':flags,'review_eligible':ic>=80}
                    reason=f'Estructura de precios desbalanceada: línea máxima {hi:.2f}× la mediana y mínima {lo:.2f}×.'
                    if ic<80: reason+=f' Comparabilidad {ic:.0f}/100: requiere revisión de datos antes de interpretación económica.'
                    out.append(_sig('INT-PB-002',tid,sid,reason,metrics,buyer_id=buyer_id,buyer_name=buyer_name))
        awarded=set()
        for a in t.get('awards') or []:
            if str(a.get('status') or '').lower() not in ('cancelled','unsuccessful'):
                awarded.update(str(s.get('id') or s.get('name') or '') for s in a.get('suppliers') or [])
        for sid in awarded:
            for iid,vals in line_prices.items():
                mine=[p for s,p in vals if s==sid]
                others=[p for s,p in vals if s!=sid]
                if not mine or len(others)<2: continue
                p=mine[0]; peer=median(others)
                if peer>0 and p/peer>=2.0:
                    cheaper=sum(1 for x in others if x<=p*0.75)
                    if cheaper>=1:
                        quality=line_quality.get(iid) or assess_comparability(line_observations.get(iid,[]))
                        ic=float(quality.get('comparability_index') or 0)
                        metrics={'item_id':iid,'awarded_unit_price':p,'peer_median':peer,'ratio':p/peer,'cheaper_peer_count':cheaper,'peer_count':len(others),
                                 'comparability_index':ic,'comparability_band':quality.get('band'),'data_quality_flags':quality.get('data_quality_flags',[]),'review_eligible':ic>=80}
                        reason=f'Proveedor adjudicado ofertó {p/peer:.2f}× la mediana de pares en una línea con alternativas sustancialmente menores.'
                        if ic<80: reason+=f' Comparabilidad {ic:.0f}/100: no priorizar como anomalía económica sin revisión de datos.'
                        out.append(_sig('INT-PB-005',tid,sid,reason,metrics,buyer_id=buyer_id,buyer_name=buyer_name))
    return out
