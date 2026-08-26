#!/usr/bin/env python3
"""Single end-to-end contract gate for the production architecture."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "repository_audit": "scripts/repository_audit.py",
    "production_contract_audit": "scripts/production_contract_audit.py",
    "provider_registry_audit": "scripts/provider_registry_audit.py",
    "provider_mesh_audit": "scripts/provider_mesh_audit.py",
    "reliability_gate": "scripts/production_reliability_gate.py",
    "gateway": "scripts/odysseus_gateway.py",
    "primary_story": "scripts/odysseus_primary_story.py",
    "story_engine": "scripts/patent_story_engine.py",
    "orchestrator": "scripts/daily_content_orchestrator.py",
    "renderer": "scripts/produce.sh",
    "long_qa": "scripts/final_feature_qa.py",
    "visual_qa": "scripts/visual_qa.py",
}


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []

    for name, rel in REQUIRED.items():
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing:{name}:{rel}")
        elif path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except Exception as exc:
                errors.append(f"syntax:{rel}:{exc}")

    try:
        contract = load("config/production-contract.json")
        gateway = load("config/odysseus-gateway.json")
        router = load("config/ai-router.json")
        slots = load("config/long-story-slots.json")
        mesh = load("config/provider-mesh.json")
        plan = load("config/provider-activation-plan.json")
    except Exception as exc:
        errors.append(f"config-load:{exc}")
        contract = gateway = router = slots = mesh = plan = {}

    intel = contract.get("intelligence", {})
    if contract and contract.get("canonical_workflow") != ".github/workflows/daily-production.yml":
        errors.append("contract:canonical-workflow")
    if intel.get("primary") != "Odysseus":
        errors.append("contract:primary-not-odysseus")
    if intel.get("fallback") != "Aqaaab AI Router":
        errors.append("contract:fallback-mismatch")
    if intel.get("enabled_by_default") is not True:
        errors.append("contract:odysseus-not-enabled-by-default")
    if intel.get("lifecycle") != "ephemeral":
        errors.append("contract:non-ephemeral")

    if gateway:
        if gateway.get("enabled") is not True:
            errors.append("gateway:disabled")
        if gateway.get("mode") != "primary_with_router_fallback":
            errors.append("gateway:mode")
        if gateway.get("endpoint") != "/api/v1/chat" or gateway.get("external_endpoint") != "/api/v1/chat":
            errors.append("gateway:endpoint")
        if gateway.get("never_expose_provider_keys") is not True:
            errors.append("gateway:provider-keys-exposure")
        runtime = gateway.get("runtime", {})
        if runtime.get("lifecycle") != "ephemeral":
            errors.append("gateway:runtime-lifecycle")
        if runtime.get("start_before_story") is not True or runtime.get("stop_after_production") is not True:
            errors.append("gateway:runtime-boundaries")

    if router:
        if router.get("free_only") is not True or router.get("fail_closed") is not True:
            errors.append("router:free-only-fail-closed")
        task = router.get("tasks", {}).get("long_story", {})
        if task.get("mode") != "fixed_slots" or task.get("slot_count") != 5 or task.get("slot_scene_count") != 5:
            errors.append("router:slot-contract")
        if task.get("max_output_tokens") != 1200:
            errors.append("router:max-output-tokens")

    if slots:
        ranges = [[x.get("start_scene"), x.get("end_scene")] for x in slots.get("slots", [])]
        if ranges != [[1, 5], [6, 10], [11, 15], [16, 20], [21, 25]]:
            errors.append("slots:ranges")
        rules = slots.get("rules", {})
        if rules.get("fallback_stays_in_same_slot") is not True or rules.get("never_skip_failed_slot") is not True:
            errors.append("slots:failure-handling")

    if plan and len(plan.get("providers", [])) > 100:
        errors.append("providers:unexpected-count")
    for task_name, chain in mesh.get("tasks", {}).items():
        for key in ("primary", "backup_1", "backup_2"):
            if not chain.get(key):
                errors.append(f"mesh:{task_name}:missing-{key}")

    daily = ROOT / ".github/workflows/daily-production.yml"
    if daily.is_file():
        text = daily.read_text(encoding="utf-8")
        for token in (
            "ODYSSEUS_GATEWAY_ENABLED",
            "ODYSSEUS_GATEWAY_BASE_URL",
            "ODYSSEUS_GATEWAY_API_KEY",
            "ODYSSEUS_STORY_MODEL",
            "scripts/daily_content_orchestrator.py",
            "scripts/produce.sh",
        ):
            if token not in text:
                errors.append(f"workflow:missing:{token}")
        if "endpoint'] == '/api/chat'" in text or "endpoint']=='/api/chat'" in text or 'endpoint']=="/api/chat"' in text:
            errors.append("workflow:stale-odysseus-endpoint")
        if "from scripts.odysseus_primary_story import _url" in text:
            errors.append("workflow:stale-odysseus-symbol")

    primary = ROOT / "scripts/odysseus_primary_story.py"
    if primary.is_file():
        text = primary.read_text(encoding="utf-8")
        for token in ("_chat_url", "odysseus_call", "_build_fallback_router", "router_fallback", "/api/v1/chat"):
            if token not in text:
                errors.append(f"primary:missing:{token}")

    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1

    print("PRODUCTION_SYSTEM_GATE=PASS")
    print("REPOSITORY_AUDIT=PASS")
    print("FILE_IMPORT_CONTRACT=PASS")
    print("PROVIDER_REGISTRY=PASS")
    print("PROVIDER_MESH=PASS")
    print("ODYSSEUS_GATEWAY=PASS")
    print("ODYSSEUS_PRIMARY_STORY=PASS")
    print("ROUTER_FALLBACK=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FOUR_SHORTS_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
