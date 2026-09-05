from __future__ import annotations

import json
from functools import wraps

from numeric_contract import align_arabic_numeric_facts, numeric_facts, same_numeric_facts
from story_contract import SCENE_WORDS_MAX, SCENE_WORDS_MIN, SCENE_WORDS_TARGET_MAX, SCENE_WORDS_TARGET_MIN


def apply_runtime_hardening() -> None:
    """Install the canonical contracts before any LLM-generated story reaches production gates."""
    import story_pipeline
    import strict_story_gate

    story_pipeline.MIN_WORDS = SCENE_WORDS_MIN
    story_pipeline.MAX_WORDS = SCENE_WORDS_MAX
    story_pipeline.TARGET_MIN_WORDS = SCENE_WORDS_TARGET_MIN
    story_pipeline.TARGET_MAX_WORDS = SCENE_WORDS_TARGET_MAX

    original_prompt = story_pipeline._story_prompt
    if not getattr(original_prompt, "_contract_hardened", False):
        @wraps(original_prompt)
        def hardened_prompt(topic: str) -> str:
            value = original_prompt(topic)
            try:
                payload = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return value + "\nNUMERIC POLICY: explicit factual digits are authoritative; model identifiers are not facts."
            policy = payload.setdefault("hard_rules", [])
            for rule in (
                "Any factual specification must use explicit numeric digits, not bare spelled-out count words.",
                "Never invent a numeric specification. Use qualitative wording when a trusted source is unavailable.",
                "The Arabic translation must preserve every explicit numeric value exactly.",
                "Digits embedded inside alphanumeric identifiers such as R35, V6, 911GT3, 2JZ-GTE, A80, and Mk4 are identifiers, not numeric facts.",
            ):
                if rule not in policy:
                    policy.append(rule)
            payload.setdefault("contract", {})["numeric_rule"] = "Explicit standalone digits are authoritative; embedded identifier digits are ignored."
            payload["contract"]["scene_words"] = f"{SCENE_WORDS_TARGET_MIN}-{SCENE_WORDS_TARGET_MAX} target; {SCENE_WORDS_MIN}-{SCENE_WORDS_MAX} hard limit"
            return json.dumps(payload, ensure_ascii=False)
        hardened_prompt._contract_hardened = True  # type: ignore[attr-defined]
        story_pipeline._story_prompt = hardened_prompt

    strict_story_gate._numbers = numeric_facts
    strict_story_gate._same_numeric_facts = same_numeric_facts
    strict_story_gate._canonicalize_numeric_facts = align_arabic_numeric_facts


def validate_hardening_importable() -> None:
    apply_runtime_hardening()
    import story_pipeline
    import strict_story_gate
    assert story_pipeline.MIN_WORDS == SCENE_WORDS_MIN
    assert story_pipeline.MAX_WORDS == SCENE_WORDS_MAX
    assert story_pipeline.TARGET_MIN_WORDS == SCENE_WORDS_TARGET_MIN
    assert story_pipeline.TARGET_MAX_WORDS == SCENE_WORDS_TARGET_MAX
    assert strict_story_gate._numbers("one car", "en") == strict_story_gate._numbers("سيارة واحدة", "ar")
    assert strict_story_gate._numbers("Nissan R35", "en") == numeric_facts("Nissan R35", "en")
    assert "35" not in strict_story_gate._numbers("Nissan R35", "en")
