from intelligence_fusion.public_integrity_prioritization import assess_comparability, prioritize_review_cases
from intelligence_fusion.public_procurement_competition import detect_competition

def test_comparability_is_not_risk_score():
    rows=[{'item_id':'1','product_code':'P1','unit':'UN','description':'producto comparable','unit_price':100+i} for i in range(4)]
    out=assess_comparability(rows)
    assert 0 <= out['comparability_index'] <= 100
    assert out['scoring_eligible'] is False
    assert out['risk_effect']=='NONE'

def test_competition_signals_are_review_only():
    tender={'tender_id':'T1','buyer':{'id':'B1','name':'Comprador'},'bids':[
      {'supplier_id':'S1','items':[{'item_id':'A','product_code':'P','unit':'UN','description':'x','unit_price':10},{'item_id':'B','product_code':'Q','unit':'UN','description':'y','unit_price':1000}]},
      {'supplier_id':'S2','items':[{'item_id':'A','product_code':'P','unit':'UN','description':'x','unit_price':100},{'item_id':'B','product_code':'Q','unit':'UN','description':'y','unit_price':100}]},
      {'supplier_id':'S3','items':[{'item_id':'A','product_code':'P','unit':'UN','description':'x','unit_price':110},{'item_id':'B','product_code':'Q','unit':'UN','description':'y','unit_price':110}]},
    ],'awards':[]}
    signals=detect_competition([tender])
    assert signals
    assert all(x['semantic_class']=='INTEGRITY_REVIEW' for x in signals)
    assert all(x['scoring_eligible'] is False and x['risk_effect']=='NONE' for x in signals)

def test_priority_explicitly_is_review_priority():
    rows=[{'signal_type':'INT-PB-002','provider_buyer_pair_id':'S::B','metrics':{'comparability_index':90}}]
    out=prioritize_review_cases(rows)
    assert out[0]['scoring_eligible'] is False
    assert out[0]['risk_effect']=='NONE'
    assert 'no representa probabilidad' in out[0]['guardrail']
