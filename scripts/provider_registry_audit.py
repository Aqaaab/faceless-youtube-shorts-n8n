#!/usr/bin/env python3
"""Static consistency audit for the Aqaaab AI Router provider registry."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config"/"ai-router.json"; PLAN=ROOT/"config"/"provider-activation-plan.json"; POOL=ROOT/"scripts"/"compatible_provider_pool.py"; DAILY_WORKFLOW=ROOT/".github"/"workflows"/"daily-production-v2.yml"; VALIDATION_WORKFLOW=ROOT/".github"/"workflows"/"ai-router-validation.yml"; ROUTER=ROOT/"scripts"/"ai_router.py"

def main()->int:
 cfg=json.loads(CFG.read_text(encoding="utf-8")); plan=json.loads(PLAN.read_text(encoding="utf-8")); pool=POOL.read_text(encoding="utf-8"); daily_workflow=DAILY_WORKFLOW.read_text(encoding="utf-8"); validation_workflow=VALIDATION_WORKFLOW.read_text(encoding="utf-8"); workflow=daily_workflow+"\n"+validation_workflow; router=ROUTER.read_text(encoding="utf-8")
 registry=cfg.get("additional_providers",{}); plan_entries=plan.get("providers",[]); plan_names=[p["name"] for p in plan_entries]; plan_by_name={p["name"]:p for p in plan_entries}; builtins={"OpenRouter","CloudflareWorkersAI"}; dedicated={"FreeLLMAPI","Ollama"}
 assert cfg["free_only"] is True and cfg["fail_closed"] is True
 assert "GitHubModels" not in registry and "GitHubModels" not in plan_names and "ZAI" not in registry and "ZAI" not in plan_names and "ZAI" not in pool
 assert len(registry)<=int(plan.get("policy",{}).get("max_provider_entries",100))
 assert set(plan_names)==(set(registry)-builtins)|dedicated
 assert set(plan.get("built_in_free_only_providers",[]))==builtins
 assert registry["OpenRouter"]["default_model"].endswith(":free") and registry["CloudflareWorkersAI"]["free_only"] is True
 for name,meta in registry.items():
  if name in builtins:
   continue
  disabled=bool(meta.get("disabled_by_default",False) or plan_by_name.get(name,{}).get("disabled_by_default",False))
  if name not in pool:
   assert disabled, f"adapter missing for enabled provider: {name}"
   continue
  assert meta.get("api_key_env") in pool, f"secret adapter missing: {meta.get('api_key_env')}" if meta.get("api_key_env") else f"secret metadata missing: {name}"
  if not disabled:
   assert meta["api_key_env"] in workflow, f"workflow secret missing: {meta['api_key_env']}"
   flag=f'ENABLE_{name.upper()}_PROVIDER'; assert flag in workflow,f"workflow enable flag missing: {flag}"
 for name in builtins:
  meta=cfg["openrouter"] if name=="OpenRouter" else cfg["cloudflare_workers_ai"]
  assert meta["free_only"] is True and meta["live_inference_required"] is True and name in router
 for name in dedicated: assert name in router
 task_providers={x.split(':',1)[0] for x in cfg["tasks"]["long_story"]["providers"]}
 for name in registry:
  if name in dedicated and name not in task_providers: continue
  if not registry[name].get("disabled_by_default",False): assert name in task_providers or name in builtins, f"enabled provider missing from long_story task: {name}"
 for p in plan_entries:
  name=p["name"]; disabled=bool(p.get("disabled_by_default",False) or registry.get(name,{}).get("disabled_by_default",False))
  assert name in router or disabled or name in dedicated, f"provider adapter/router missing: {name}"
 assert "scripts/compatible_provider_pool.py" in daily_workflow and "scripts/patent_story_engine.py" in daily_workflow and "ALLOW_DETERMINISTIC_FALLBACK: \"false\"" in daily_workflow
 print(f"PROVIDER_REGISTRY_COUNT={len(registry)}"); print(f"PROVIDER_PLAN_COUNT={len(plan_names)}"); print(f"BUILT_IN_FREE_PROVIDER_COUNT={len(builtins)}"); print("PROVIDER_REGISTRY_MATCH=PASS"); print("PROVIDER_ADAPTER_MATCH=PASS"); print("BUILT_IN_FREE_PROVIDER_MATCH=PASS"); print("ZAI_REMOVED=PASS"); print("FREE_ONLY_FAIL_CLOSED=PASS"); return 0
if __name__=="__main__": raise SystemExit(main())
