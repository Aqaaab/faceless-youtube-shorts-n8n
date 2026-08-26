from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('RUN_DIR',str(ROOT/'data/test-story-slots'))


def test_slot_contract_is_fixed_and_contiguous():
    cfg=json.loads((ROOT/'config/long-story-slots.json').read_text(encoding='utf-8'))
    slots=cfg['slots']
    assert cfg['rules']['fixed_scene_ranges'] is True
    assert cfg['rules']['fallback_stays_in_same_slot'] is True
    assert cfg['rules']['never_skip_failed_slot'] is True
    assert len(slots)==5
    assert [s['start_scene'] for s in slots]==[1,6,11,16,21]
    assert [s['end_scene'] for s in slots]==[5,10,15,20,25]
    assert all(s['scene_count']==5 for s in slots)
    assert sum(s['scene_count'] for s in slots)==25


def test_story_engine_and_orchestrator_reference_slot_contract():
    patent=(ROOT/'scripts/patent_story_engine.py').read_text(encoding='utf-8')
    orch=(ROOT/'scripts/daily_content_orchestrator.py').read_text(encoding='utf-8')
    assert 'LONG_STORY_SLOTS_CONFIG' in patent
    assert 'LONG_STORY_SLOT_ABORT' in patent
    assert 'if provider:' in patent
    assert 'config/long-story-slots.json' in orch
    assert '_validate_story_slots' in orch
    assert 'LONG_STORY_FIXED_SLOTS=PASS' in orch


def test_router_uses_slot_output_budget():
    router=(ROOT/'scripts/ai_router.py').read_text(encoding='utf-8')
    pool=(ROOT/'scripts/compatible_provider_pool.py').read_text(encoding='utf-8')
    cfg=json.loads((ROOT/'config/ai-router.json').read_text(encoding='utf-8'))
    assert 'LONG_SLOT_MAX_OUTPUT_TOKENS' in router
    assert 'LONG_SLOT_MAX_OUTPUT_TOKENS' in pool
    assert cfg['tasks']['long_story']['mode']=='fixed_slots'
    assert cfg['tasks']['long_story']['slot_count']==5
    assert cfg['tasks']['long_story']['slot_scene_count']==5
    assert cfg['tasks']['long_story']['max_output_tokens']==1200


def test_validation_failure_is_not_persistently_cooled_down():
    from ai_router import AIRouter, Provider
    p=Provider('Repairable',['long_story'],1,True,lambda prompt:{'ok':True})
    r=AIRouter([p])
    r.report_validation_failure('Repairable',ValueError('S1 scene count invalid'))
    assert r._entry('Repairable')['status']=='SCHEMA_INVALID'
    assert r._entry('Repairable')['cooldown_until']==0
