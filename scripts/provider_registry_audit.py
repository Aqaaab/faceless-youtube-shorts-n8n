#!/usr/bin/env python3
"""Static consistency audit for the Aqaaab AI Router provider registry."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "ai-router.json"
PLAN = ROOT / "config" / "provider-activation-plan.json"
POOL = ROOT / "scripts" / "compatible_provider_pool.py"
WORKFLOW = ROOT / ".github" / "workflows" / "daily-production-v2.yml"


def main() -> int:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    pool = POOL.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    registry = cfg.get("additional_providers", {})
    plan_entries = plan.get("providers", [])
    plan_names = [p["name"] for p in plan_entries]
    dedicated_names = {"FreeLLMAPI", "Ollama"}
    registry_plan_names = [name for name in plan_names if name not in dedicated_names]

    assert cfg["free_only"] is True and cfg["fail_closed"] is True
    assert "GitHubModels" not in registry
    assert "GitHubModels" not in plan_names
    assert "ZAI" not in registry
    assert "ZAI" not in plan_names
    assert "ZAI" not in pool
    assert len(registry) == 9
    assert len(plan_names) == 11
    assert set(registry_plan_names) == set(registry)
    assert plan_names[-2:] == ["FreeLLMAPI", "Ollama"]

    for name, meta in registry.items():
        assert f'"{name}"' in pool, f"adapter missing: {name}"
        assert meta["api_key_env"] in pool, f"secret adapter missing: {meta['api_key_env']}"
        assert meta["api_key_env"] in workflow, f"workflow secret missing: {meta['api_key_env']}"
        flag = f'ENABLE_{name.upper()}_PROVIDER'
        assert flag in workflow, f"workflow enable flag missing: {flag}"

    for name in dedicated_names:
        key = name.lower()
        assert key in cfg, f"dedicated provider config missing: {key}"
        meta = cfg[key]
        assert meta["free_only"] is True
        assert meta["openai_compatible"] is True
        assert meta["live_inference_required"] is True
        assert f'"{name}"' in pool, f"adapter missing: {name}"
        enable_flag = f'ENABLE_{name.upper()}_PROVIDER'
        assert enable_flag in workflow, f"workflow enable flag missing: {enable_flag}"

    route_names = cfg["tasks"]["long_story"]["providers"]
    for name in plan_names:
        assert name in route_names, f"provider not in route order: {name}"

    assert "scripts/compatible_provider_pool.py" in workflow
    assert "scripts/patent_story_engine.py" in workflow
    assert "ALLOW_DETERMINISTIC_FALLBACK: \"false\"" in workflow

    print("PROVIDER_REGISTRY_COUNT=9")
    print("PROVIDER_PLAN_COUNT=11")
    print("PROVIDER_REGISTRY_MATCH=PASS")
    print("PROVIDER_ADAPTER_MATCH=PASS")
    print("DEDICATED_PROVIDER_MATCH=PASS")
    print("WORKFLOW_SECRET_MATCH=PASS")
    print("WORKFLOW_ENABLE_FLAG_MATCH=PASS")
    print("ROUTING_ORDER_MATCH=PASS")
    print("ZAI_REMOVED=PASS")
    print("FREE_ONLY_FAIL_CLOSED=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
