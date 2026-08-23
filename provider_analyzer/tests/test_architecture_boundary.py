import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent


def atlas_project_ref():
    # Keep the forbidden identifier out of repository text so the guardrail cannot match itself.
    return 'ldmtlwzqa' + 'qmegedktlxr'


def test_provider_analyzer_does_not_target_atlas_supabase():
    forbidden=atlas_project_ref()
    for p in ROOT.rglob('*'):
        if '__pycache__' in p.parts:
            continue
        if p.is_file() and p.suffix in {'.py','.toml','.md','.yml','.yaml','.json'}:
            assert forbidden not in p.read_text(encoding='utf-8',errors='ignore'), p


def test_export_contract_stays_context_only():
    script=(ROOT/'scripts'/'export_fusion_signals.py').read_text(encoding='utf-8')
    assert "PRODUCER_ID = 'PROVIDER_ANALYZER'" in script
    assert "CONTEXT_SIGNAL_TYPE = 'PROVIDER_REVIEW_SIGNAL'" in script
    assert "'scoring_eligible': False" in script
    assert "'risk_effect': 'NONE'" in script
    assert "'semantics': 'CONTEXT_ONLY'" in script


def test_initial_manifest_never_emits_false_zero():
    manifest=json.loads((ROOT/'exports'/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema']=='PROVIDER_ANALYZER_EXPORT_V1'
    assert manifest['guardrails']['missing_is_not_zero'] is True
    assert manifest['guardrails']['contains_no_raw_procurement_dataset'] is True
    assert manifest['contract']['fusion_semantics']=='CONTEXT_ONLY'
    assert manifest['contract']['scoring_eligible'] is False
    assert manifest['contract']['risk_effect']=='NONE'
    for key in ('evidence','events','context_signals'):
        assert key in manifest['objects']


def test_workflows_do_not_write_intelligence_fusion_layer():
    wf=REPO/'.github'/'workflows'
    forbidden=atlas_project_ref()
    for name in ('provider-analyzer-monthly.yml','provider-analyzer-backfill.yml'):
        p=wf/name
        if p.exists():
            text=p.read_text(encoding='utf-8')
            assert 'Intelligence_Fusion_Layer' not in text
            assert forbidden not in text
