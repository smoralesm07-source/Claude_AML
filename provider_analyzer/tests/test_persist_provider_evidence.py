from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    path=Path(__file__).parents[1]/'scripts'/'persist_provider_evidence.py'
    spec=importlib.util.spec_from_file_location('persist_provider_evidence',path)
    module=importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_canonical_evidence_links_to_signal_id():
    mod=load_module();period='2026-07';signal_id='SIG-ABC'
    evidence_id=mod.stable_id('EVD-PA',signal_id,period)
    rows=mod.build_rows([{'signal_id':signal_id}],[{'evidence_id':evidence_id,'source_url':None,'quality_status':'VALID'}],period,'2026-08-23T20:00:00Z')
    assert len(rows)==1
    assert rows[0]['signal_id']==signal_id
    assert rows[0]['evidence_type']=='PROCUREMENT_REVIEW_DERIVATION'
    assert rows[0]['semantic_hash']


def test_unmatched_evidence_is_rejected():
    mod=load_module()
    try:
        mod.build_rows([{'signal_id':'SIG-ABC'}],[{'evidence_id':'EVD-PA-WRONG'}],'2026-07','2026-08-23T20:00:00Z')
    except ValueError as exc:
        assert 'UNMATCHED_CANONICAL_EVIDENCE' in str(exc)
    else:
        raise AssertionError('unmatched evidence must fail closed')
