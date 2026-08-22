from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any
from .sources.common import event_id, norm_text

RULES={
 "INT-PB-001":"Precio unitario extremo respecto de comparables",
 "INT-PB-003":"Incremento contractual atípico",
 "INT-PB-004":"Incremento extraordinario de cantidades",
 "INT-PB-006":"Lobby temporalmente próximo a decisión contractual",
 "INT-PB-007":"Coincidencia temática lobby ↔ contratación",
 "INT-PB-008":"Concentración creciente proveedor–comprador",
 "INT-PB-012":"Convergencia multiseñal de integridad",
}

def _date(x:Any)->datetime|None:
    if not x:return None
    s=str(x).replace("Z","+00:00")
    for fmt in (None,"%d/%m/%Y","%d-%m-%Y"):
        try:
            d=datetime.fromisoformat(s) if fmt is None else datetime.strptime(s[:10],fmt)
            return d.replace(tzinfo=d.tzinfo or timezone.utc)
        except ValueError: pass
    return None

def _signal(rule:str,pair:str,evidence:list[str],reason:str,metrics:dict)->dict:
    return {"signal_id":event_id("SIG-INT",rule,pair,*evidence),"signal_type":rule,"semantic_class":"INTEGRITY_REVIEW",
            "scope":"PROVIDER_BUYER_PAIR","pair_id":pair,"evidence_ids":evidence,"reason":reason,"metrics":metrics,
            "scoring_eligible":False,"risk_effect":"NONE"}

def detect(orders:list[dict], previous_by_id:dict[str,dict]|None=None, lobby_events:list[dict]|None=None)->list[dict]:
    previous_by_id=previous_by_id or {}; lobby_events=lobby_events or []; signals=[]
    prices=defaultdict(list)
    for o in orders:
        for i in o.get("items") or []:
            if i.get("product_code") and i.get("unit_price") not in (None,0): prices[i["product_code"]].append(float(i["unit_price"]))
    med={k:median(v) for k,v in prices.items() if len(v)>=4}
    pair_amount=defaultdict(float); total_amount=0.0
    for o in orders:
        pair=o.get("pair_key",""); total=float(o.get("amount_total") or 0); pair_amount[pair]+=total; total_amount+=total
        ev=[f"EVD-MP-{o['order_id']}-{o['record_hash'][:12]}"]
        for i in o.get("items") or []:
            m=med.get(i.get("product_code")); p=i.get("unit_price")
            if m and p and p>=3*m:
                signals.append(_signal("INT-PB-001",pair,ev,f"Precio unitario {p:.2f} ≥ 3× mediana comparable {m:.2f}.",{"unit_price":p,"peer_median":m,"ratio":p/m,"product_code":i.get("product_code")}))
        prev=previous_by_id.get(o["order_id"])
        if prev:
            a0=float(prev.get("amount_total") or 0); a1=total
            if a0>0 and a1/a0>=2: signals.append(_signal("INT-PB-003",pair,ev,f"Monto de OC aumentó {a1/a0:.2f}×.",{"previous":a0,"current":a1,"ratio":a1/a0}))
            q0=sum(float(x.get("quantity") or 0) for x in prev.get("items") or []); q1=sum(float(x.get("quantity") or 0) for x in o.get("items") or [])
            if q0>0 and q1/q0>=2: signals.append(_signal("INT-PB-004",pair,ev,f"Cantidad agregada aumentó {q1/q0:.2f}×.",{"previous":q0,"current":q1,"ratio":q1/q0}))
        od=_date(o.get("modified_at") or o.get("created_at")); sn=norm_text(o["supplier"].get("name")); bn=norm_text(o["buyer"].get("name"))
        for le in lobby_events:
            a=le.get("attributes") or {}; ld=_date((le.get("temporal") or {}).get("valid_from"))
            if not od or not ld: continue
            represented=norm_text(a.get("represented_name")); institution=norm_text(a.get("institution"))
            if represented and sn and (represented in sn or sn in represented) and institution and bn and (institution in bn or bn in institution):
                days=(od-ld).days
                if 0<=days<=180:
                    lev=[*ev,*le.get("evidence_ids",[])]
                    signals.append(_signal("INT-PB-006",pair,lev,f"Audiencia registrada {days} días antes del evento contractual.",{"days":days,"audience_id":a.get("audience_id")}))
                    subject=norm_text(a.get("subject")); desc=norm_text((o.get("description") or "")+" "+(o.get("name") or "")); tokens={t for t in subject.split() if len(t)>=5}; overlap=sorted(t for t in tokens if t in desc)
                    if overlap: signals.append(_signal("INT-PB-007",pair,lev,"Coincidencia léxica entre materia de audiencia y contratación.",{"overlap":overlap[:12],"days":days}))
    if total_amount>0:
        for pair,amt in pair_amount.items():
            share=amt/total_amount
            if amt>0 and share>=0.20: signals.append(_signal("INT-PB-008",pair,[],f"Par concentra {share:.1%} del monto observado en la ventana.",{"pair_amount":amt,"window_total":total_amount,"share":share}))
    by_pair=defaultdict(list)
    for s in signals: by_pair[s["pair_id"]].append(s)
    for pair,rows in by_pair.items():
        types=sorted({x["signal_type"] for x in rows})
        if len(types)>=3:
            ev=sorted({e for x in rows for e in x.get("evidence_ids",[])})
            signals.append(_signal("INT-PB-012",pair,ev,f"Convergen {len(types)} tipos de señal independientes.",{"signal_types":types}))
    return signals
