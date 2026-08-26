#!/usr/bin/env python3
"""Odysseus-first story generation with Aqaaab AI Router fallback.

Odysseus is an intelligence/orchestration layer, not the video renderer. It owns
story-slot generation when configured; the existing free-only router remains the
same-slot fallback and still enforces provider health, quota and schema rules.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from patent_story_engine import (
    MAX_COOLDOWN_WAIT,
    OUT,
    SLOTS,
    _normalize_metadata,
    _slot_prompt,
    _wait_for_ready,
    council_context,
    validate_final,
    validate_slot,
)
from ai_router import build_long_story_router

ROOT = Path(__file__).resolve().parent
ENABLED = os.getenv("ODYSSEUS_GATEWAY_ENABLED", "true").lower() == "true"
BASE_URL = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
API_KEY = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
MODEL = os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story").strip()
TIMEOUT = int(os.getenv("ODYSSEUS_GATEWAY_TIMEOUT", "180"))


def _url() -> str:
    if not BASE_URL:
        raise RuntimeError("Odysseus base URL is not configured")
    return BASE_URL if BASE_URL.endswith("/api") else BASE_URL + "/api"


def _extract_response(payload):
    if isinstance(payload, dict):
        for key in ("analysis", "result", "reply", "content", "text"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                text = value.strip()
                a, b = text.find("{"), text.rfind("}")
                if a >= 0 and b > a:
                    text = text[a:b + 1]
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    from json_repair import repair_json
                    obj = repair_json(text, return_objects=True)
                    if isinstance(obj, dict):
                        return obj
    raise ValueError("Odysseus returned no valid JSON object")


def odysseus_call(prompt):
    payload = {
        "ask": prompt,
        "model": MODEL,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        _url() + "/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        raise RuntimeError(f"Odysseus HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Odysseus transport failure: {exc}") from exc
    return _extract_response(body)


def _odysseus_ready():
    return ENABLED and bool(BASE_URL) and bool(API_KEY)


def generate():
    winner = council_context()
    base_context = json.dumps(
        {
            "topic": winner.get("topic"),
            "core_question": winner.get("core_question"),
            "hook": winner.get("hook"),
            "selected_hook": winner.get("selected_hook"),
            "novel_angle": winner.get("novel_angle"),
        },
        ensure_ascii=False,
    )

    router = build_long_story_router()
    try:
        from compatible_provider_pool import extend_router
        router = extend_router(router)
    except Exception as exc:
        print(f"COMPATIBLE_PROVIDER_POOL_INIT_SKIP reason={exc}")

    if not getattr(router, "providers", None):
        raise SystemExit("NO_ELIGIBLE_LONG_STORY_PROVIDERS")

    odysseus_active = _odysseus_ready()
    print(
        "ODYSSEUS_PRIMARY=" + ("ACTIVE" if odysseus_active else "UNAVAILABLE_FALLBACK_ROUTER")
    )

    all_scenes = []
    slot_results = []
    prior_tail = []

    for slot in SLOTS:
        excluded = set()
        slot_error = ""
        completed = False
        attempt = 0
        last = None
        max_attempts = max(
            4, min(int(os.getenv("LONG_SLOT_ATTEMPTS", "8")), len(router.providers) * 2)
        )

        while attempt < max_attempts and not completed:
            attempt += 1
            router.clear_expired_cooldowns()
            prompt = _slot_prompt(base_context, slot, prior_tail, slot_error)

            # Primary: Odysseus. It is intentionally outside the provider router so
            # provider API keys never need to be passed into Odysseus.
            if odysseus_active:
                try:
                    result = odysseus_call(prompt)
                    scenes, words = validate_slot(result, slot)
                    for offset, scene in enumerate(scenes):
                        scene["scene_number"] = slot["start_scene"] + offset
                        scene["slot_id"] = slot["slot_id"]
                        scene["provider"] = "Odysseus"
                    all_scenes.extend(scenes)
                    slot_results.append(
                        {
                            "slot_id": slot["slot_id"],
                            "start_scene": slot["start_scene"],
                            "end_scene": slot["end_scene"],
                            "provider": "Odysseus",
                            "model": MODEL,
                            "attempt": attempt,
                            "words": words,
                            "status": "PASS",
                            "route": "primary",
                        }
                    )
                    prior_tail = scenes[-2:]
                    completed = True
                    print(
                        f"LONG_STORY_SLOT_PASS slot={slot['slot_id']} provider=Odysseus route=primary attempt={attempt}"
                    )
                    continue
                except Exception as exc:
                    last = exc
                    slot_error = str(exc)
                    print(
                        f"ODYSSEUS_SLOT_FAIL slot={slot['slot_id']} attempt={attempt}: {exc}"
                    )

            # Fallback: existing free-only Aqaaab AI Router, same slot only.
            provider = None
            try:
                result, provider, model = router.route(
                    prompt,
                    exclude=excluded,
                    wait_for_ready=True,
                    max_wait_seconds=MAX_COOLDOWN_WAIT,
                )
                scenes, words = validate_slot(result, slot)
                for offset, scene in enumerate(scenes):
                    scene["scene_number"] = slot["start_scene"] + offset
                    scene["slot_id"] = slot["slot_id"]
                    scene["provider"] = provider
                all_scenes.extend(scenes)
                slot_results.append(
                    {
                        "slot_id": slot["slot_id"],
                        "start_scene": slot["start_scene"],
                        "end_scene": slot["end_scene"],
                        "provider": provider,
                        "model": model,
                        "attempt": attempt,
                        "words": words,
                        "status": "PASS",
                        "route": "router_fallback",
                    }
                )
                prior_tail = scenes[-2:]
                completed = True
                print(
                    f"LONG_STORY_SLOT_PASS slot={slot['slot_id']} provider={provider} route=router_fallback attempt={attempt}"
                )
            except Exception as exc:
                last = exc
                slot_error = str(exc)
                print(f"LONG_STORY_SLOT_FAIL slot={slot['slot_id']} attempt={attempt}: {exc}")
                if provider:
                    excluded.add(provider)
                    try:
                        router.report_validation_failure(provider, exc)
                    except Exception:
                        pass
                    print(
                        f"LONG_STORY_SLOT_PROVIDER_QUARANTINE slot={slot['slot_id']} provider={provider}"
                    )
                if len(excluded) >= len(router.providers):
                    excluded.clear()
                    if not _wait_for_ready(router, excluded):
                        break

        if not completed:
            raise SystemExit(
                f"LONG_STORY_SLOT_ABORT slot={slot['slot_id']} failed without advancing to next slot: {last}"
            )

    if len(all_scenes) != sum(int(s["scene_count"]) for s in SLOTS):
        raise SystemExit("LONG_STORY_SLOT_MERGE_COUNT_MISMATCH")

    title, description, tags = _normalize_metadata(winner)
    merged = {
        "title": title,
        "description": description,
        "tags": tags,
        "topic": winner.get("topic"),
        "category": "Stories",
        "selected_hook": winner.get("selected_hook"),
        "scenes": all_scenes,
        "slot_results": slot_results,
        "router": "Odysseus Primary Intelligence Gateway",
        "router_task": "long_story_slots",
        "provider": "multi_provider_slots",
        "model": "odysseus_primary_with_router_fallback",
        "story_mode": "fixed_slots",
        "idea_council_winner": winner,
    }
    validate_final(merged)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"LONG_STORY_PASS mode=fixed_slots intelligence=odysseus_primary slots={len(SLOTS)} scenes={merged['scene_count']} words={merged['script_words']} hook_injected={bool(merged.get('selected_hook'))}"
    )


if __name__ == "__main__":
    generate()
