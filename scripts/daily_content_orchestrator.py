#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
def run(name, extra=None):
 print(f'== {name} =='); env=os.environ.copy(); env.update(extra or {}); subprocess.run([sys.executable,str(ROOT/name)],check=True,env=env)
def main():
 for name in ('youtube_trend_scanner.py','story_pattern_analyzer.py','github_assistant_registry.py','daily_content_planner.py','council_learning_bridge.py','idea_generation_council.py','idea_council_judge.py'):
  run(name)
 run('content_intelligence_upgrade.py',{'CONTENT_INTELLIGENCE_PHASE':'pre'})
 run('patent_story_engine.py')
 run('viral_engine.py')
 run('content_intelligence_upgrade.py',{'CONTENT_INTELLIGENCE_PHASE':'post'})
 required=('daily_plan.json','trend_candidates.json','story_pattern.json','long_story.json','viral_plan.json','github_assistants.json','idea_council.json','idea_judged.json','idea_tournament.json','competitor_intelligence.json','retention_simulation.json','visual_intelligence.json','shorts_intelligence.json','packaging_candidates.json','thumbnail_candidates.json')
 for f in required: assert (RUN_DIR/f).is_file(), f'MISSING_OUTPUT:{f}'
 plan=json.loads((RUN_DIR/'daily_plan.json').read_text(encoding='utf-8')); story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8')); viral=json.loads((RUN_DIR/'viral_plan.json').read_text(encoding='utf-8')); assistants=json.loads((RUN_DIR/'github_assistants.json').read_text(encoding='utf-8')); council=json.loads((RUN_DIR/'idea_council.json').read_text(encoding='utf-8')); judged=json.loads((RUN_DIR/'idea_judged.json').read_text(encoding='utf-8')); shorts=json.loads((RUN_DIR/'shorts_intelligence.json').read_text(encoding='utf-8'))
 assert plan['daily_long_video']['count']==1 and plan['daily_shorts']['count']==4
 assert plan['trend_research']['enabled'] is True and plan['contracts']['no_deterministic_fallback'] is True and plan['contracts']['require_visual_qa'] is True
 assert story['format']=='patent' and 7<=story['duration_target_minutes'][0]<=15 and 1050<=story['script_words']<=2100
 assert council.get('winner',{}).get('status')=='winner' and judged.get('winner',{}).get('idea_id')
 assert len(viral['shorts'])==4 and len(shorts['selected'])==4 and len({x['scene_start'] for x in viral['shorts']})==4
 assert assistants['assistants'] and plan['github_assistants']['external_production_dependency'] is False
 rendered=os.environ.get('PRODUCTION_RENDER_COMPLETE','false').lower()=='true'
 manifest={'schema_version':'3.0','daily_plan':'daily_plan.json','trend_candidates':'trend_candidates.json','story_pattern':'story_pattern.json','competitor_intelligence':'competitor_intelligence.json','idea_council':'idea_council.json','idea_judged':'idea_judged.json','idea_tournament':'idea_tournament.json','long_story':'long_story.json','retention_simulation':'retention_simulation.json','visual_intelligence':'visual_intelligence.json','viral_plan':'viral_plan.json','shorts_intelligence':'shorts_intelligence.json','packaging_candidates':'packaging_candidates.json','thumbnail_candidates':'thumbnail_candidates.json','github_assistants':'github_assistants.json','long_video_count':1,'short_count':4,'production_ready':rendered,'research_first':True,'contract_stage':'council-story-production-intelligence','enhancements':['competitor_intelligence','idea_tournament','retention_simulator','visual_intelligence','shorts_intelligence','thumbnail_tournament','packaging_engine','production_reliability']}
 (RUN_DIR/'daily_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('DAILY_CONTENT_CONTRACT=PASS council=on tournament=on retention=on visual=on shorts=on packaging=on thumbnail=on reliability=workflow-gated')
if __name__=='__main__': main()
