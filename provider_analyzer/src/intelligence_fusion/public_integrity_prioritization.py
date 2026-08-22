from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
import re
from typing import Any
from .sources.common import clean_rut, norm_text


def _date(v: Any) -> datetime | None:
    if not v:return None
    s=str(v).strip().replace('Z','+00:00')
    for fmt in (None,'%d/%m/%Y','%d-%m-%Y'):
        try:
            d=datetime.fromisoformat(s) if fmt is None else datetime.strptime(s[:10],fmt)
            return d.replace(tzinfo=d.tzinfo or timezone.utc)
        except ValueError:pass
    return None


def _tokens(v: Any)->set[str]:
    return {x for x in re.findall(r'[a-z0-9]+',norm_text(v or '').lower()) if len(x)>=3}


def _jaccard(a:set[str],b:set[str])->float:
    return len(a&b)/len(a|b) if a and b else 0.0


def _party_id(p:dict)->str:
    rut=p.get('rut')
    if rut:return str(clean_rut(rut) or '')
    return str(p.get('id') or p.get('name') or '')


def _product_key(row:dict)->str:
    code=norm_text(row.get('product_code'))
    if code:return f'CODE:{code}'
    text=norm_text(row.get('name') or row.get('description')).lower()
    return f'TEXT:{text}' if text else ''


def assess_comparability(items:list[dict])->dict:
    """Evidence-quality score for price comparability; never an integrity/risk score."""
    rows=[x for x in items if x];score=0;reasons=[];flags=[];n=len(rows)
    if n>=4:score+=20;reasons.append('4+ observaciones comparables')
    elif n==3:score+=16;reasons.append('3 observaciones comparables')
    elif n==2:score+=8;reasons.append('sólo 2 observaciones')
    else:flags.append('INSUFFICIENT_PEERS')
    codes={norm_text(x.get('product_code')) for x in rows if norm_text(x.get('product_code'))};item_ids={norm_text(x.get('item_id')) for x in rows if norm_text(x.get('item_id'))}
    if len(codes)==1 and codes:score+=25;reasons.append('mismo código de producto')
    elif len(item_ids)==1 and item_ids:score+=18;reasons.append('misma línea/ítem de licitación')
    elif codes or item_ids:flags.append('PRODUCT_KEY_CONFLICT')
    units={norm_text(x.get('unit')).lower() for x in rows if norm_text(x.get('unit'))}
    if len(units)==1 and units:score+=20;reasons.append('misma unidad de medida')
    elif not units:score+=6;flags.append('UNIT_MISSING')
    else:flags.append('UNIT_CONFLICT')
    desc=[_tokens(x.get('description')) for x in rows if _tokens(x.get('description'))];sims=[_jaccard(desc[i],desc[j]) for i in range(len(desc)) for j in range(i+1,len(desc))];sim=median(sims) if sims else None
    if sim is None:score+=5;flags.append('DESCRIPTION_MISSING')
    elif sim>=.8:score+=20;reasons.append('descripciones altamente consistentes')
    elif sim>=.6:score+=14;reasons.append('descripciones consistentes')
    elif sim>=.4:score+=7;flags.append('DESCRIPTION_PARTIAL_MATCH')
    else:flags.append('DESCRIPTION_CONFLICT')
    prices=[float(x['unit_price']) for x in rows if x.get('unit_price') not in (None,0)];nominal=[p for p in prices if p<=1]
    if nominal:flags.append('NOMINAL_PRICE')
    if len(prices)==n and prices and not nominal:
        ratio=max(prices)/max(min(prices),1e-9)
        if ratio<=100:score+=15
        elif ratio<=1000:score+=8;flags.append('EXTREME_PRICE_SPREAD')
        else:flags.append('IMPLAUSIBLE_PRICE_SPREAD')
    elif len(prices)<n:flags.append('PRICE_MISSING')
    score=max(0,min(100,int(round(score))));band='INTERPRETABLE' if score>=80 else 'REVIEW_DATA' if score>=60 else 'DATA_QUALITY'
    return {'comparability_index':score,'band':band,'peer_count':n,'description_similarity':None if sim is None else round(sim,4),'reasons':reasons,'data_quality_flags':sorted(set(flags)),'scoring_eligible':False,'risk_effect':'NONE'}


def build_provider_buyer_history(orders:list[dict],years:int=5,as_of:Any=None)->dict[str,dict]:
    end=_date(as_of) or datetime.now(timezone.utc);start=end-timedelta(days=365*years);pairs=defaultdict(list);buyer_totals=defaultdict(float)
    for o in orders:
        when=_date(o.get('modified_at') or o.get('accepted_at') or o.get('created_at') or o.get('date'))
        if not when or when<start or when>end:continue
        buyer=o.get('buyer') or {};supplier=o.get('supplier') or {};bid=_party_id(buyer);sid=_party_id(supplier);pair=str(o.get('pair_key') or f'{sid}::{bid}');amount=float(o.get('amount_total') or o.get('amount') or 0)
        pairs[pair].append((when,amount,o,bid));buyer_totals[bid]+=amount
    out={}
    for pair,rows in pairs.items():
        rows.sort(key=lambda x:x[0]);amount=sum(x[1] for x in rows);bid=rows[0][3];yrs=sorted({x[0].year for x in rows});mods=sorted({str(x[2].get('modality') or x[2].get('procurement_method') or '') for x in rows if x[2].get('modality') or x[2].get('procurement_method')})
        out[pair]={'pair_id':pair,'window_years':years,'order_count':len(rows),'amount_total':amount,'buyer_amount_total':buyer_totals.get(bid,0.0),'buyer_share':amount/buyer_totals[bid] if buyer_totals.get(bid) else 0.0,'years_active':yrs,'active_year_count':len(yrs),'first_seen':rows[0][0].date().isoformat(),'last_seen':rows[-1][0].date().isoformat(),'modalities':mods,'scoring_eligible':False,'risk_effect':'NONE'}
    return out


def derive_purchase_route_events(orders:list[dict],tenders:list[dict])->list[dict]:
    """Create conservative line-level route events from normalized Mercado Público data.

    Negative events require a final/adjudicated tender state and no explicit awarded supplier.
    Positive events come from non-cancelled purchase orders. Exact product code is preferred.
    """
    out=[]
    for t in tenders:
        status=norm_text(t.get('status')).lower();final=bool(t.get('awarded_at')) or any(x in status for x in ('adjudic','desiert','cerrad','cancel'))
        if not final:continue
        buyer=_party_id(t.get('buyer') or {});date=t.get('awarded_at') or t.get('closed_at') or t.get('published_at');tid=str(t.get('tender_id') or '')
        if not buyer or not date:continue
        for item in t.get('items') or []:
            if item.get('awarded_supplier_rut') or item.get('awarded_supplier_name'):continue
            product=_product_key(item)
            if not product:continue
            negative='DESERTED' if 'desiert' in status else 'NOT_AWARDED'
            out.append({'buyer_id':buyer,'product_key':product,'date':date,'status':negative,'tender_id':tid,'process_id':tid,'modality':t.get('type'),'source':'MERCADO_PUBLICO_TENDER','line':item.get('line')})
    for o in orders:
        status=norm_text(o.get('status')).lower()
        if any(x in status for x in ('cancel','anulad','rechaz')):continue
        buyer=_party_id(o.get('buyer') or {});supplier=_party_id(o.get('supplier') or {});date=o.get('accepted_at') or o.get('modified_at') or o.get('created_at');process=str(o.get('tender_id') or o.get('order_id') or '')
        if not buyer or not supplier or not date:continue
        for item in o.get('items') or []:
            product=_product_key(item)
            if not product:continue
            out.append({'buyer_id':buyer,'supplier_id':supplier,'product_key':product,'date':date,'status':'PURCHASED','tender_id':process,'process_id':process,'order_id':o.get('order_id'),'modality':o.get('modality') or o.get('procurement_method'),'source':'MERCADO_PUBLICO_ORDER'})
    return out


def detect_alternative_purchase_routes(events:list[dict],days:int=180)->list[dict]:
    rows=[]
    for e in events:
        d=_date(e.get('date') or e.get('event_date') or e.get('created_at'))
        if d:rows.append({**e,'_date':d})
    rows.sort(key=lambda x:x['_date']);out=[];seen=set();negative={'NOT_AWARDED','UNSUCCESSFUL','DESERTED','CANCELLED','SIN_ADJUDICACION','DESIERTA'};positive={'AWARDED','PURCHASED','ORDERED','ACTIVE','ADJUDICADA','COMPRADA'}
    for origin in rows:
        if str(origin.get('status') or '').upper() not in negative:continue
        buyer=str(origin.get('buyer_id') or origin.get('buyer_name') or '');product=norm_text(origin.get('product_key') or origin.get('product_code') or origin.get('description')).lower()
        if not buyer or not product:continue
        for later in rows:
            if later['_date']<=origin['_date']:continue
            delta=(later['_date']-origin['_date']).days
            if delta>days:break
            lb=str(later.get('buyer_id') or later.get('buyer_name') or '');lp=norm_text(later.get('product_key') or later.get('product_code') or later.get('description')).lower()
            if lb!=buyer or lp!=product or str(later.get('status') or '').upper() not in positive:continue
            op=str(origin.get('tender_id') or origin.get('process_id') or '');np=str(later.get('tender_id') or later.get('process_id') or '')
            if op and np and op==np:continue
            supplier=str(later.get('supplier_id') or later.get('supplier_name') or '');pair=f'{supplier}::{buyer}' if supplier else None
            dedupe=(buyer,product,op,np,supplier,later.get('order_id'))
            if dedupe in seen:continue
            seen.add(dedupe)
            om=str(origin.get('modality') or '');lm=str(later.get('modality') or '')
            out.append({'finding_type':'ALTERNATIVE_PURCHASE_ROUTE','semantic_class':'INTEGRITY_REVIEW','pair_id':pair,'buyer_id':buyer,'product_key':product,'origin_process_id':op or None,'origin_status':origin.get('status'),'origin_modality':origin.get('modality'),'origin_line':origin.get('line'),'origin_evidence':origin.get('evidence'),'later_process_id':np or None,'later_order_id':later.get('order_id'),'later_modality':later.get('modality'),'later_supplier_id':supplier or None,'days_after':delta,'modality_changed':bool(om and lm and norm_text(om).lower()!=norm_text(lm).lower()),'review_reason':'Una línea no adjudicada reaparece como compra/adjudicación posterior del mismo comprador y producto.','scoring_eligible':False,'risk_effect':'NONE'});break
    return out


def prioritize_review_cases(signals:list[dict],histories:dict[str,dict]|None=None,route_findings:list[dict]|None=None)->list[dict]:
    histories=histories or {};route_findings=route_findings or [];grouped=defaultdict(list)
    for s in signals:
        key=str(s.get('provider_buyer_pair_id') or s.get('pair_id') or s.get('supplier_id') or s.get('tender_id') or '')
        if key:grouped[key].append(s)
    route_by_pair=defaultdict(int)
    for r in route_findings:
        pair=str(r.get('pair_id') or '')
        if pair:route_by_pair[pair]+=1
    ranked=[]
    for key,rows in grouped.items():
        types=sorted({str(x.get('signal_type') or '') for x in rows if x.get('signal_type')});diversity=min(35,len(types)*10);ics=[float((x.get('metrics') or {}).get('comparability_index')) for x in rows if (x.get('metrics') or {}).get('comparability_index') is not None];ic=median(ics) if ics else 50.0;evidence=min(25,max(0,ic/4));history=histories.get(key) or {};persistence=min(10,float(history.get('active_year_count') or 0)*2);concentration=min(10,float(history.get('buyer_share') or 0)*20);route=min(15,route_by_pair.get(key,0)*10);penalty=sum(5 for x in rows for f in ((x.get('metrics') or {}).get('data_quality_flags') or []) if f in {'NOMINAL_PRICE','UNIT_CONFLICT','IMPLAUSIBLE_PRICE_SPREAD'});priority=max(0,min(100,round(diversity+evidence+persistence+concentration+route-penalty,1)));tier='HIGH' if priority>=70 else 'MEDIUM' if priority>=45 else 'LOW'
        ranked.append({'review_key':key,'review_priority':priority,'tier':tier,'signal_types':types,'signal_count':len(rows),'comparability_index_median':round(ic,1),'history':history,'alternative_route_count':route_by_pair.get(key,0),'components':{'signal_diversity':diversity,'evidence_comparability':round(evidence,1),'historical_persistence':round(persistence,1),'buyer_concentration':round(concentration,1),'alternative_route':route,'data_quality_penalty':penalty},'guardrail':'Prioridad de revisión explicable; no representa probabilidad de delito, infracción ni LA/FT.','scoring_eligible':False,'risk_effect':'NONE'})
    return sorted(ranked,key=lambda x:(-x['review_priority'],x['review_key']))
