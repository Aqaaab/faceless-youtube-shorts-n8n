#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
RUN_DIR.mkdir(parents=True, exist_ok=True)

def _load_env_file(path: Path) -> None:
    if not path.is_file(): return
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key,value=line.split('=',1); os.environ[key]=value

def _apply_local_provider_state() -> None:
    registry=RUN_DIR/'github_assistants.json'
    if not registry.is_file(): os.environ['ENABLE_FREELLMAPI_PROVIDER']='false'; os.environ['ENABLE_OLLAMA_PROVIDER']='false'; return
    try: data=json.loads(registry.read_text(encoding='utf-8'))
    except Exception: os.environ['ENABLE_FREELLMAPI_PROVIDER']='false'; os.environ['ENABLE_OLLAMA_PROVIDER']='false'; return
    if data.get('local_free_stack_enabled') is True:
        runtime_env=RUN_DIR/'ai_router'/'freellmapi.env'
        if runtime_env.is_file(): _load_env_file(runtime_env)
        else: os.environ['ENABLE_FREELLMAPI_PROVIDER']='false'; os.environ['ENABLE_OLLAMA_PROVIDER']='false'
        return
    os.environ['ENABLE_FREELLMAPI_PROVIDER']='false'; os.environ['ENABLE_OLLAMA_PROVIDER']='false'

def run(name, extra=None):
    print(f'== {name} ==')
    env=os.environ.copy(); env.update(extra or {})
    subprocess.run([sys.executable,str(ROOT/name)],check=True,env=env)
    if name=='github_assistant_registry.py': _apply_local_provider_state()

def _validate_story_slots(story):
    cfg=json.loads((ROOT.parent/'config'/'long-story-slots.json').read_text(encoding='utf-8'))
    slots=cfg['slots']; scenes=story.get('scenes',[])
    assert cfg['rules']['fixed_scene_ranges'] is True
    assert cfg['rules']['fallback_stays_in_same_slot'] is True
    assert cfg['rules']['never_skip_failed_slot'] is True
    assert len(slots)==5 and sum(int(s['scene_count']) for s in slots)==25
    assert len(scenes)==25
    assert len(story.get('slot_results',[]))==5
    for slot in slots:
        block=[x for x in scenes if x.get('slot_id')==slot['slot_id']]
        assert len(block)==slot['scene_count'], f'SLOT_SCENE_COUNT:{slot["slot_id"]}'
        numbers=[int(x['scene_number']) for x in block]
        assert numbers==list(range(slot['start_scene'],slot['end_scene']+1)), f'SLOT_SCENE_RANGE:{slot["slot_id"]}'
        result=[x for x in story['slot_results'] if x.get('slot_id')==slot['slot_id']]
        assert len(result)==1 and result[0].get('start_scene')==slot['start_scene'] and result[0].get('end_scene')==slot['end_scene']
    assert [x['scene_number'] for x in scenes]==list(range(1,26))
    print('LONG_STORY_FIXED_SLOTS=PASS slots=5 scenes=25')

def main():
    for name in ('youtube_trend_scanner.py','story_pattern_analyzer.py','github_assistant_registry.py','daily_content_planner.py','council_learning_bridge.py','idea_generation_council.py','idea_council_judge.py'):
        run(name)
    run('content_intelligence_upgrade.py',{'CONTENT_INTELLIGENCE_PHASE':'pre'})
    run('hook_optimizer.py')
    # Odysseus is the primary intelligence/story gateway. The gateway itself
    # falls back to the existing free-only Aqaaab AI Router within the same slot.
    run('odysseus_primary_story.py')
    run('retention_planner.py')
    run('scene_intelligence.py')
    run('visual_asset_validator.py')
    run('viral_engine.py')
    run('content_intelligence_upgrade.py',{'CONTENT_INTELLIGENCE_PHASE':'post'})
    run('packaging_optimizer.py')
    run('analytics_learning.py')

    required=('daily_plan.json','trend_candidates.json','story_pattern.json','long_story.json','viral_plan.json','github_assistants.json','idea_council.json','idea_judged.json','idea_tournament.json','competitor_intelligence.json','retention_simulation.json','visual_intelligence.json','shorts_intelligence.json','packaging_candidates.json','thumbnail_candidates.json','hook_candidates.json','scene_intelligence.json','visual_qa.json','analytics_learning.json')
    for f in required: assert (RUN_DIR/f).is_file(), f'MISSING_OUTPUT:{f}'

    contract=json.loads((ROOT.parent/'config'/'production-enhancement-plan.json').read_text(encoding='utf-8'))
    plan=json.loads((RUN_DIR/'daily_plan.json').read_text(encoding='utf-8')); story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8')); viral=json.loads((RUN_DIR/'viral_plan.json').read_text(encoding='utf-8')); assistants=json.loads((RUN_DIR/'github_assistants.json').read_text(encoding='utf-8')); council=json.loads((RUN_DIR/'idea_council.json').read_text(encoding='utf-8')); judged=json.loads((RUN_DIR/'idea_judged.json').read_text(encoding='utf-8')); shorts=json.loads((RUN_DIR/'shorts_intelligence.json').read_text(encoding='utf-8')); hook=json.loads((RUN_DIR/'hook_candidates.json').read_text(encoding='utf-8')); retention=json.loads((RUN_DIR/'retention_simulation.json').read_text(encoding='utf-8')); scene=json.loads((RUN_DIR/'scene_intelligence.json').read_text(encoding='utf-8'))
    _validate_story_slots(story)
    assert contract['hard_rules']['shorts_must_be_clips_of_long_video'] is True
    assert plan['daily_long_video']['count']==1 and plan['daily_shorts']['count']==4
    assert 7<=plan['daily_long_video']['duration_min']<=plan['daily_long_video']['duration_max']<=15
    assert plan['trend_research']['enabled'] is True and plan['contracts']['no_deterministic_fallback'] is True and plan['contracts']['require_visual_qa'] is True
    assert story['format']=='patent' and 18<=story['scene_count']<=30 and 1050<=story['script_words']<=2100
    assert story.get('selected_hook')==hook.get('selected_hook') and hook.get('selected_hook')
    assert council.get('winner',{}).get('status')=='winner' and judged.get('winner',{}).get('idea_id')
    assert 0 <= float(hook.get('selected_score',0)) <= 100
    assert retention.get('beat_map') and 0 <= float(retention.get('retention_risk',0)) <= 100
    assert int(scene.get('scene_count',0)) == 25
    assert viral.get('candidate_count')==12 and len(viral['candidates'])==12 and len(viral['shorts'])==4
    assert all(x.get('source')=='long_video' and x.get('source_video')=='video.mp4' for x in viral['shorts'])
    assert len(shorts['selected'])==4 and len({x['scene_start'] for x in viral['shorts']})==4
    assert assistants['assistants'] and plan['github_assistants']['external_production_dependency'] is False

    rendered=os.environ.get('PRODUCTION_RENDER_COMPLETE','false').lower()=='true'
    manifest={'schema_version':'6.0','enhancement_contract':'config/production-enhancement-plan.json','long_story_slots_contract':'config/long-story-slots.json','daily_plan':'daily_plan.json','trend_candidates':'trend_candidates.json','story_pattern':'story_pattern.json','competitor_intelligence':'competitor_intelligence.json','idea_council':'idea_council.json','idea_judged':'idea_judged.json','idea_tournament':'idea_tournament.json','hook_candidates':'hook_candidates.json','retention_simulation':'retention_simulation.json','scene_intelligence':'scene_intelligence.json','visual_qa':'visual_qa.json','long_story':'long_story.json','viral_plan':'viral_plan.json','shorts_intelligence':'shorts_intelligence.json','packaging_candidates':'packaging_candidates.json','thumbnail_candidates':'thumbnail_candidates.json','github_assistants':'github_assistants.json','analytics_learning':'analytics_learning.json','long_video_count':1,'short_count':4,'short_source':'long_video','short_candidate_count':12,'long_story_fixed_slots':True,'long_story_slot_count':5,'long_story_scene_count':25,'production_ready':rendered,'research_first':True,'contract_stage':'trend-council-hook-retention-fixed-story-scene-visual-render-12to4-shorts-qa-publication-learning','enhancements':['trend_intelligence','topic_council','hook_optimizer','retention_planner','scene_intelligence','asset_provenance','fixed_story_slots','same_slot_provider_fallback','auto_regeneration','12_to_4_short_selection','long_video_related_short_linking','publication_gate','checkpoint_resume','analytics_learning','packaging_optimizer','audio_quality_gate','odysseus_primary_intelligence']}
    (RUN_DIR/'daily_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('DAILY_CONTENT_CONTRACT=PASS intelligence=odysseus_primary hook=pre-story retention=on scene=on visual=on slots=5 scenes=25 shorts=4 analytics_learning=on')

if __name__=='__main__': main()
