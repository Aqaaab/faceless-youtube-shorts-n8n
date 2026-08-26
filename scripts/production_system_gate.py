#!/usr/bin/env python3
"""Central architecture gate for the daily production system."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def require_file(path: str) -> None:
    if not (ROOT / path).is_file():
        errors.append(f"missing-file:{path}")


def require_json(path: str) -> dict:
    p = ROOT / path
    if not p.is_file():
        errors.append(f"missing-json:{path}")
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid-json:{path}:{exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"json-not-object:{path}")
        return {}
    return value


def main() -> int:
    required = [
        ".github/workflows/daily-production.yml",
        "config/ai-router.json",
        "config/provider-activation-plan.json",
        "config/provider-mesh.json",
        "config/production-contract.json",
        "config/odysseus-gateway.json",
        "config/long-story-slots.json",
        "scripts/odysseus_gateway.py",
        "scripts/odysseus_primary_story.py",
        "scripts/ai_router.py",
        "scripts/daily_content_orchestrator.py",
        "scripts/produce.sh",
    ]
    for path in required:
        require_file(path)

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
        stale_patterns = (
            r"endpoint['\"]\s*==\s*['\"]/api/chat['\"]",
            r"endpoint['\"]\s*:\s*['\"]/api/chat['\"]",
            r"_url\b",
        )
        if any(re.search(pattern, text) for pattern in stale_patterns):
            errors.append("workflow:stale-odysseus-api-or-symbol")

    primary = ROOT / "scripts/odysseus_primary_story.py"
    if primary.is_file():
        text = primary.read_text(encoding="utf-8")
        for token in (
            "_chat_url",
            "odysseus_call",
            "_build_fallback_router",
            "router_fallback",
            "/api/v1/chat",
        ):
            if token not in text:
                errors.append(f"primary:missing:{token}")

    gateway = ROOT / "scripts/odysseus_gateway.py"
    if gateway.is_file():
        text = gateway.read_text(encoding="utf-8")
        for token in ("def chat_url", "def chat(", "def extract_response", "/api/v1/chat"):
            if token not in text:
                errors.append(f"gateway:missing:{token}")

    router = require_json("config/ai-router.json")
    if router:
        if router.get("free_only") is not True:
            errors.append("router:not-free-only")
        if router.get("fail_closed") is not True:
            errors.append("router:not-fail-closed")
        long_story = router.get("tasks", {}).get("long_story", {})
        if long_story.get("mode") != "fixed_slots":
            errors.append("router:long-story-not-fixed-slots")
        if long_story.get("slot_count") != 5:
            errors.append("router:slot-count-not-5")

    odysseus = require_json("config/odysseus-gateway.json")
    if odysseus:
        if odysseus.get("enabled") is not True:
            errors.append("odysseus:disabled")
        if odysseus.get("mode") != "primary_with_router_fallback":
            errors.append("odysseus:wrong-mode")
        if odysseus.get("endpoint") != "/api/v1/chat":
            errors.append("odysseus:wrong-endpoint")
        if odysseus.get("never_expose_provider_keys") is not True:
            errors.append("odysseus:provider-keys-not-hidden")
        runtime = odysseus.get("runtime", {})
        if runtime.get("lifecycle") != "ephemeral":
            errors.append("odysseus:not-ephemeral")
        if runtime.get("start_before_story") is not True:
            errors.append("odysseus:not-start-before-story")
        if runtime.get("stop_after_production") is not True:
            errors.append("odysseus:not-stop-after-production")

    contract = require_json("config/production-contract.json")
    if contract:
        production = contract.get("production", {})
        if production.get("long_video_count") != 1:
            errors.append("contract:long-video-count")
        if production.get("short_count") != 4:
            errors.append("contract:short-count")
        if production.get("long_duration_seconds") != {"min": 420, "max": 900}:
            errors.append("contract:long-duration")
        if production.get("short_resolution") != [1080, 1920]:
            errors.append("contract:short-resolution")

    slots = require_json("config/long-story-slots.json")
    if slots:
        actual = [[x.get("start_scene"), x.get("end_scene")] for x in slots.get("slots", [])]
        expected = [[1, 5], [6, 10], [11, 15], [16, 20], [21, 25]]
        if actual != expected:
            errors.append(f"slots:wrong-ranges:{actual}")
        rules = slots.get("rules", {})
        if rules.get("fallback_stays_in_same_slot") is not True:
            errors.append("slots:fallback-escapes-slot")
        if rules.get("never_skip_failed_slot") is not True:
            errors.append("slots:failed-slot-can-be-skipped")

    if errors:
        print("PRODUCTION_SYSTEM_GATE=FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("PRODUCTION_SYSTEM_GATE=PASS")
    print("ODYSSEUS_PRIMARY=PASS")
    print("ROUTER_FALLBACK=PASS")
    print("FIXED_LONG_STORY_SLOTS=PASS")
    print("LONG_VIDEO=1x_420_900s")
    print("SHORTS=4x_1080x1920")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
