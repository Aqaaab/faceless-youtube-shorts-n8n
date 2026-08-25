#!/usr/bin/env python3
from __future__ import annotations
import json, py_compile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['scripts/daily_content_orchestrator.py','scripts/council_learning_bridge.py','scripts/idea_generation_council.py','scripts/idea_council_judge.py','scripts/content_intelligence_upgrade.py','scripts/patent_story_engine.py','scripts/viral_engine.py','scripts/short_factory.py','scripts/visual_qa.py','scripts/final_feature_qa.py','config/idea-council.json']
def main():
 for rel in REQUIRED:
  p=ROOT/rel
  if not p.is_file(): raise SystemExit(f'RELIABILITY_MISSING:{rel}')
  if p.suffix=='.py': py_compile.compile(str(p),doraise=True)
 json.loads((ROOT/'config/idea-council.json').read_text(encoding='utf-8'))
 wf=ROOT/'.github/workflows/daily-production.yml'
 text=wf.read_text(encoding='utf-8')
 for marker in ('Idea Generation Council','production_contract.json','short-*.mp4'):
  if marker not in text: raise SystemExit(f'RELIABILITY_WORKFLOW_MARKER_MISSING:{marker}')
 print('PRODUCTION_RELIABILITY_GATE=PASS files=all required python=compiled contracts=present')
if __name__=='__main__': main()
