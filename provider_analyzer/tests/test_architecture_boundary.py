from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent

def test_provider_analyzer_does_not_target_atlas_supabase():
    forbidden='ldmtlwzqaqmegedktlxr'
    for p in ROOT.rglob('*'):
        if p.is_file() and p.suffix in {'.py','.toml','.md','.yml','.yaml','.json'}:
            assert forbidden not in p.read_text(encoding='utf-8',errors='ignore'), p

def test_export_contract_stays_context_only():
    script=(ROOT/'scripts'/'export_fusion_signals.py').read_text(encoding='utf-8')
    assert "'source_system':'PROVIDER_ANALYZER'" in script
    assert "'scoring_eligible':False" in script
    assert "'risk_effect':'CONTEXT'" in script

def test_workflows_do_not_write_intelligence_fusion_layer():
    wf=REPO/'.github'/'workflows'
    for name in ('provider-analyzer-monthly.yml','provider-analyzer-backfill.yml'):
        p=wf/name
        if p.exists():
            text=p.read_text(encoding='utf-8')
            assert 'Intelligence_Fusion_Layer' not in text
            assert 'ldmtlwzqaqmegedktlxr' not in text
