from __future__ import annotations

import json
from functools import wraps
from typing import Any, Callable

from numeric_contract import align_arabic_numeric_facts, numeric_facts, same_numeric_facts


def apply_runtime_hardening() -> None:
    """Install deterministic contracts before any LLM-generated story reaches production gates."""
    import story_pipeline
    import strict_story_gate

    # Story length is set to guarantee a genuine 7–15 minute master from 25
    # scenes instead of padding a short render with a frozen final frame.
    story_pipeline.MIN_WORDS = 62
    story_pipeline.MAX_WORDS = 75
    story_pipeline.TARGET_MIN_WORDS = 65
    story_pipeline.TARGET_MAX_WORDS = 75

    original_prompt = story_pipeline._story_prompt
    if not getattr(original_prompt, "_contract_hardened", False):
        @wraps(original_prompt)
        def hardened_prompt(topic: str) -> str:
            value = original_prompt(topic)
            try:
                payload = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return value + "\nNUMERIC POLICY: write factual specifications with explicit digits; do not change numeric values between English and Arabic."
            policy = payload.setdefault("hard_rules", [])
            policy.extend([
                "Any factual specification must use explicit numeric digits, not bare spelled-out count words.",
                "Never invent a numeric specification. Use qualitative wording when a trusted source is unavailable.",
                "The Arabic translation must preserve every explicit numeric value exactly.",
            ])
            payload["contract"]["numeric_rule"] = "Explicit digits are authoritative; model identifiers such as R35 are not numeric facts."
            return json.dumps(payload, ensure_ascii=False)
        hardened_prompt._contract_hardened = True  # type: ignore[attr-defined]
        story_pipeline._story_prompt = hardened_prompt

    # Replace the over-broad legacy numeric parser with the centralized parser.
    strict_story_gate._numbers = numeric_facts
    strict_story_gate._same_numeric_facts = same_numeric_facts
    strict_story_gate._canonicalize_numeric_facts = align_arabic_numeric_facts


def validate_hardening_importable() -> None:
    apply_runtime_hardening()
    import story_pipeline
    import strict_story_gate
    assert story_pipeline.MIN_WORDS == 62
    assert story_pipeline.TARGET_MIN_WORDS == 65
    assert story_pipeline.TARGET_MAX_WORDS == 75
    assert strict_story_gate._numbers("one car", "en") == strict_story_gate._numbers("سيارة واحدة", "ar")
    assert "35" not in strict_story_gate._numbers("Nissan R35", "en")
