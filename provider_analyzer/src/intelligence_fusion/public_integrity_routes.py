from __future__ import annotations

from .sources.common import norm_text


def derive_tender_negative_events(tenders:dict)->tuple[list[dict],dict]:
    """Derive conservative negative tender-line events from normalized monthly tender state."""
    events=[];skipped_missing_final_date=0;skipped_no_award_evidence=0;final_tenders=0;line_count=0
    for t in tenders.values():
        status=norm_text(t.get('status')).lower();is_deserted='desiert' in status;is_awarded='adjudic' in status
        if not (is_deserted or is_awarded):continue
        final_tenders+=1
        event_date=t.get('awarded_at') or t.get('closed_at')
        if not event_date:
            skipped_missing_final_date+=1;continue
        if is_awarded and not t.get('has_selected_evidence'):
            skipped_no_award_evidence+=1;continue
        for line in (t.get('lines') or {}).values():
            line_count+=1
            if line.get('selected'):continue
            if not line.get('product_code') or not t.get('buyer_id'):continue
            if is_awarded and not line.get('bidders'):continue
            events.append({
                'buyer_id':t['buyer_id'],'product_key':'CODE:'+line['product_code'],'date':event_date,
                'status':'DESERTED' if is_deserted else 'NOT_AWARDED','tender_id':t['tender_id'],'process_id':t['tender_id'],
                'modality':t.get('modality') or 'LICITACION','source':'MERCADO_PUBLICO_BULK_TENDERS','line':line.get('item_id') or None,
                'bidder_count':len(line.get('bidders') or []),'evidence':'FINAL_STATUS_DESERTED' if is_deserted else 'FINAL_STATUS_WITH_SELECTED_OFFER_EVIDENCE',
                'semantic_class':'INTEGRITY_REVIEW','scoring_eligible':False,'risk_effect':'NONE'
            })
    return events,{
        'final_tenders':final_tenders,'lines_evaluated':line_count,'negative_events':len(events),
        'skipped_missing_final_date':skipped_missing_final_date,
        'skipped_awarded_tenders_without_selected_offer_evidence':skipped_no_award_evidence,
    }
