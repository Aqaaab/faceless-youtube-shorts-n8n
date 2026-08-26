#!/usr/bin/env python3
from __future__ import annotations
import json, py_compile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=['scripts/daily_content_orchestrator.py','scripts/council_learning_bridge.py','scripts/idea_generation_council.py','scripts/idea_council_judge.py','scripts/content_intelligence_upgrade.py','scripts/production_reliability_gate.py','scripts/patent_story_engine.py','scripts/viral_engine.py','scripts/short_factory.py','scripts/visual_qa.py','scripts/final_feature_qa.py','scripts/ai_router.py','scripts/compatible_provider_pool.py','scripts/provider_registry_audit.py','config/idea-council.json','config/ai-router.json','config/provider-activation-plan.json']
def main():
 for rel in REQUIRED:
  p=ROOT/rel
  if not p.is_file(): raise SystemExit(f'RELIABILITY_MISSING:{rel}')
  if p.suffix=='.py': py_compile.compile(str(p),doraise=True)
 c=json.loads((ROOT/'config/idea-council.json').read_text(encoding='utf-8'))
 r=json.loads((ROOT/'config/ai-router.json').read_text(encoding='utf-8'))
 p=json.loads((ROOT/'config/provider-activation-plan.json').read_text(encoding='utf-8'))
 assert c['allow_source_copy'] is False and c['top_k']==5 and len(c['roles'])==5
 assert r['free_only'] is True and r['fail_closed'] is True
 assert 'ZAI' not in r.get('additional_providers',{})
 assert 'GitHubModels' not in r.get('additional_providers',{})
 builtins={'OpenRouter','CloudflareWorkersAI'}
 dedicated={'FreeLLMAPI','Ollama'}
 registry=set(r.get('additional_providers',{}))
 plan_names=[x['name'] for x in p.get('providers',[])]
 assert len(registry)==11
 assert len(plan_names)==11
 assert set(plan_names) == (registry-builtins)
 assert set(plan_names) | builtins == registry
 assert plan_names[-2:] == ['FreeLLMAPI','Ollama']
 assert set(p.get('built_in_free_only_providers',[])) == builtins
 assert r['openrouter']['free_only'] is True and r['openrouter']['default_model'].endswith(':free')
 assert r['cloudflare_workers_ai']['free_only'] is True
 wf=ROOT/'.github/workflows/daily-production-v2.yml'; text=wf.read_text(encoding='utf-8')
 for marker in ('idea_judged.json','long_story.json','daily-production-v2-plan-','preflight:','OPENROUTER_API_KEY','CLOUDFLARE_API_TOKEN'):
  if marker not in text: raise SystemExit(f'RELIABILITY_WORKFLOW_MARKER_MISSING:{marker}')
 print('PRODUCTION_RELIABILITY_GATE=PASS files=all-required python=compiled council=router=registry=contract workflow=v2-checked')
if __name__=='__main__': main()
