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
    run('youtube_trend_scanner.py')
    run('story_pattern_analyzer.py')
    run('github_assistant_registry.py')
    run('daily_content_planner.py')
    run('patent_story_engine.py')
    run('viral_engine.py')
    plan=json.loads((RUN_DIR/'daily_plan.json').read_text())
    story=json.loads((RUN_DIR/'long_story.json').read_text())
    viral=json.loads((RUN_DIR/'viral_plan.json').read_text())
    assistants=json.loads((RUN_DIR/'github_assistants.json').read_text())
    assert plan['daily_long_video']['count']==1
    assert plan['daily_shorts']['count']==4
    assert plan['trend_research']['enabled'] is True
    assert story['format']=='patent'
    assert 7 <= story['duration_target_minutes'][0] <= 15
    assert 1050 <= story['script_words'] <= 2100
    assert len(viral['shorts'])==4
    assert all(0 <= float(x['score']) <= 100 for x in viral['shorts'])
    assert assistants['assistants'] and plan['github_assistants']['external_production_dependency'] is False
    manifest={'schema_version':'2.0','daily_plan':'daily_plan.json','trend_candidates':'trend_candidates.json','story_pattern':'story_pattern.json','long_story':'long_story.json','viral_plan':'viral_plan.json','github_assistants':'github_assistants.json','long_video_count':1,'short_count':4,'external_assistant':'optional_later','production_ready':True,'research_first':True}
    (RUN_DIR/'daily_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('DAILY_CONTENT_CONTRACT=PASS long=1 shorts=4 patent=7-15m trend-research=on viral=internal')

if __name__=='__main__': main()
