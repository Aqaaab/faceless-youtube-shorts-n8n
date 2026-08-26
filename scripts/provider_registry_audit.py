#!/usr/bin/env python3
"""Static consistency audit for the Aqaaab AI Router provider registry."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "ai-router.json"
PLAN = ROOT / "config" / "provider-activation-plan.json"
POOL = ROOT / "scripts" / "compatible_provider_pool.py"
DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "daily-production-v2.yml"
VALIDATION_WORKFLOW = ROOT / ".github" / "workflows" / "ai-router-validation.yml"
ROUTER = ROOT / "scripts" / "ai_router.py"


def main() -> int:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    pool = POOL.read_text(encoding="utf-8")
    daily_workflow = DAILY_WORKFLOW.read_text(encoding="utf-8")
    validation_workflow = VALIDATION_WORKFLOW.read_text(encoding="utf-8")
    workflow = daily_workflow + "\n" + validation_workflow
    router = ROUTER.read_text(encoding="utf-8")

    registry = cfg.get("additional_providers", {})
    registry_names = set(registry)
    plan_names = {p["name"] for p in plan.get("providers", [])}
    builtins = set(plan.get("built_in_free_only_providers", []))
    dedicated = {"FreeLLMAPI", "Ollama"}
    activation_order = plan.get("activation_order", [])

    assert cfg["free_only"] is True and cfg["fail_closed"] is True
    assert len(registry_names) <= int(plan["policy"]["max_provider_entries"])
    assert "GitHubModels" not in registry_names and "GitHubModels" not in plan_names
    assert "ZAI" not in registry_names and "ZAI" not in plan_names and "ZAI" not in pool

    # Canonical relationship between the two registries:
    # additional_providers = non-local plan providers + built-in gateways.
    assert registry_names == (plan_names - dedicated) | builtins
    assert builtins == {"OpenRouter", "CloudflareWorkersAI"}
    assert dedicated <= plan_names
    assert dedicated.isdisjoint(registry_names)
    assert builtins <= registry_names
    assert builtins.isdisjoint(dedicated)
    assert set(activation_order) == plan_names
    assert len(activation_order) == len(plan_names)

    # Every registry provider must have an adapter, unless explicitly disabled by default.
    for name, meta in registry.items():
        if name in builtins:
            continue
        if name not in pool:
            assert meta.get("disabled_by_default") is True, f"adapter missing and not disabled: {name}"
            continue
        api_env = meta.get("api_key_env") or meta.get("api_token_env")
        if api_env:
            assert api_env in pool, f"secret adapter missing: {name}/{api_env}"
            assert api_env in workflow, f"workflow secret missing: {name}/{api_env}"
        flag = f"ENABLE_{name.upper()}_PROVIDER"
        assert flag in workflow, f"workflow enable flag missing: {flag}"

    for name in builtins:
        meta = cfg["openrouter"] if name == "OpenRouter" else cfg["cloudflare_workers_ai"]
        assert meta["free_only"] is True
        assert meta["live_inference_required"] is True
        assert name in router

    for name in dedicated:
        assert name in router

    for name in plan_names:
        assert name in pool or name in router, f"provider adapter missing: {name}"

    task_providers = set(cfg["tasks"]["long_story"]["providers"])
    task_plain = {p.split(":", 1)[0] for p in task_providers}
    assert registry_names <= task_plain
    assert plan_names <= task_plain

    assert "scripts/compatible_provider_pool.py" in daily_workflow
    assert "scripts/patent_story_engine.py" in daily_workflow
    assert 'ALLOW_DETERMINISTIC_FALLBACK: "false"' in daily_workflow

    print(f"PROVIDER_REGISTRY_COUNT={len(registry_names)}")
    print(f"PROVIDER_PLAN_COUNT={len(plan_names)}")
    print(f"BUILT_IN_FREE_PROVIDER_COUNT={len(builtins)}")
    print("PROVIDER_REGISTRY_MATCH=PASS")
    print("PROVIDER_ADAPTER_MATCH=PASS")
    print("BUILT_IN_FREE_PROVIDER_MATCH=PASS")
    print("ZAI_REMOVED=PASS")
    print("FREE_ONLY_FAIL_CLOSED=PASS")
    print("FIXED_SLOT_PROVIDER_COVERAGE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
