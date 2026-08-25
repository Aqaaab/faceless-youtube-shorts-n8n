#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)

def run(name):
    print(f'== {name} ==')
    subprocess.run([sys.executable,str(ROOT/name)],check=True,env=os.environ.copy())

def main():
    for name in ('youtube_trend_scanner.py','story_pattern_analyzer.py','github_assistant_registry.py','daily_content_planner.py','patent_story_engine.py','viral_engine.py'):
        run(name)
    plan=json.loads((RUN_DIR/'daily_plan.json').read_text(encoding='utf-8'))
    story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    viral=json.loads((RUN_DIR/'viral_plan.json').read_text(encoding='utf-8'))
    assistants=json.loads((RUN_DIR/'github_assistants.json').read_text(encoding='utf-8'))
    assert plan['daily_long_video']['count']==1
    assert plan['daily_shorts']['count']==4
    assert plan['trend_research']['enabled'] is True
    assert plan['contracts']['no_deterministic_fallback'] is True
    assert plan['contracts']['require_visual_qa'] is True
    assert story['format']=='patent' and 7 <= story['duration_target_minutes'][0] <= 15
    assert 1050 <= story['script_words'] <= 2100
    assert len(viral['shorts'])==4
    assert len({x['scene_start'] for x in viral['shorts']})==4
    assert all(0 <= float(x['score']) <= 100 for x in viral['shorts'])
    assert assistants['assistants'] and plan['github_assistants']['external_production_dependency'] is False
    rendered=os.environ.get('PRODUCTION_RENDER_COMPLETE','false').lower()=='true'
    manifest={'schema_version':'2.1','daily_plan':'daily_plan.json','trend_candidates':'trend_candidates.json','story_pattern':'story_pattern.json','long_story':'long_story.json','viral_plan':'viral_plan.json','github_assistants':'github_assistants.json','long_video_count':1,'short_count':4,'external_assistant':'optional_later','production_ready':rendered,'research_first':True,'contract_stage':'planning_and_story_generation','production_note':'production_ready becomes true only after the real renderer, QA and publishing stages confirm completion'}
    (RUN_DIR/'daily_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'DAILY_CONTENT_CONTRACT=PASS long=1 shorts=4 patent=7-15m trend-research=on viral=internal production_ready={rendered}')

if __name__=='__main__': main()
