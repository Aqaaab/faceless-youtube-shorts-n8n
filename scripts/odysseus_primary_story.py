#!/usr/bin/env python3
"""Odysseus-first story generation with Aqaaab AI Router fallback.

Odysseus is the primary intelligence/orchestration layer. The existing
free-only Aqaaab AI Router is constructed lazily and is used only as a
same-slot fallback when the Odysseus request fails validation or transport.
Provider credentials are never sent to Odysseus.
"""
from __future__ import annotations

import json
import os
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

ROOT = Path(__file__).resolve().parent
ENABLED = os.getenv("ODYSSEUS_GATEWAY_ENABLED", "true").lower() == "true"
BASE_URL = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
API_KEY = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
MODEL = os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story").strip()
TIMEOUT = int(os.getenv("ODYSSEUS_GATEWAY_TIMEOUT", "180"))


def _chat_url() -> str:
    if not BASE_URL:
        raise RuntimeError("Odysseus base URL is not configured")
    if BASE_URL.endswith("/api/v1/chat"):
        return BASE_URL
    if BASE_URL.endswith("/api/v1"):
        return BASE_URL + "/chat"
    if BASE_URL.endswith("/api"):
        return BASE_URL + "/v1/chat"
    return BASE_URL + "/api/v1/chat"


def _extract_response(payload):
    if isinstance(payload, dict):
        # /api/v1/chat returns {response, session_id, model}.
        for key in ("response", "analysis", "result", "reply", "content", "text"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value, payload.get("session_id")
            if isinstance(value, str) and value.strip():
                text = value.strip()
                a, b = text.find("{"), text.rfind("}")
                if a >= 0 and b > a:
                    text = text[a:b + 1]
                try:
                    return json.loads(text), payload.get("session_id")
                except json.JSONDecodeError:
                    from json_repair import repair_json
                    obj = repair_json(text, return_objects=True)
                    if isinstance(obj, dict):
                        return obj, payload.get("session_id")
    raise ValueError("Odysseus returned no valid JSON object")



def odysseus_call(prompt, session_id=None):
    payload = {
        "message": prompt,
        "model": MODEL,
    }
    if session_id:
        payload["session"] = session_id

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        _chat_url(),
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
    if not ENABLED:
        return False
    missing = []
    if not BASE_URL:
        missing.append("ODYSSEUS_GATEWAY_BASE_URL")
    if not API_KEY:
        missing.append("ODYSSEUS_GATEWAY_API_KEY")
    if missing:
        raise SystemExit("ODYSSEUS_PRIMARY_CONFIGURATION_MISSING:" + ",".join(missing))
    return True


def _build_fallback_router():
    """Construct the provider router only when Odysseus needs a fallback."""
    from ai_router import build_long_story_router

    router = build_long_story_router()
    try:
        from compatible_provider_pool import extend_router
        router = extend_router(router)
    except Exception as exc:
        print(f"COMPATIBLE_PROVIDER_POOL_INIT_SKIP reason={exc}")
    if not getattr(router, "providers", None):
        raise SystemExit("NO_ELIGIBLE_LONG_STORY_PROVIDERS")
    return router


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

    odysseus_active = _odysseus_ready()
    print("ODYSSEUS_PRIMARY=ACTIVE" if odysseus_active else "ODYSSEUS_PRIMARY=DISABLED")

    # The router is deliberately lazy: Primary Odysseus must not require
    # provider keys just to start a production run.
    router = None
    all_scenes = []
    slot_results = []
    prior_tail = []
    odysseus_session_id = None

    for slot in SLOTS:
        excluded = set()
        slot_error = ""
        completed = False
        attempt = 0
        last = None
        while not completed:
            attempt += 1
            prompt = _slot_prompt(base_context, slot, prior_tail, slot_error)

            # Primary: Odysseus. Provider API keys are never sent to it.
            if odysseus_active:
                try:
                    result, returned_session_id = odysseus_call(prompt, odysseus_session_id)
                    scenes, words = validate_slot(result, slot)
                    if returned_session_id:
                        odysseus_session_id = returned_session_id
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
                    print(f"ODYSSEUS_SLOT_FAIL slot={slot['slot_id']} attempt={attempt}: {exc}")

            # Fallback: construct and use the existing free-only router only
            # after the primary actually fails. Fallback remains same-slot.
            if router is None:
                router = _build_fallback_router()
                print(f"ODYSSEUS_FALLBACK_ROUTER_READY providers={len(router.providers)}")

            provider = None
            try:
                router.clear_expired_cooldowns()
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
