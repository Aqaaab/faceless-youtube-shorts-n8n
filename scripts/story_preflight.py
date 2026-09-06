from __future__ import annotations

import json
import os
import re
from pathlib import Path

from story_integrity_lock import force_numeric_alignment
from strict_story_gate import _same_numeric_facts, MAX_EN_WORDS

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
HOOK_SCENES = {1, 7, 13, 19}


def _word_count(text: str) -> int:
    return len(re.findall(r"\b(?:[A-Za-z][A-Za-z0-9'\-]*|[0-9]+(?:[.,][0-9]+)?)\b", str(text or "")))


def _trim_preserving_facts(text: str, max_words: int) -> str:
    tokens = str(text or "").strip().split()
    if _word_count(" ".join(tokens)) <= max_words:
        return " ".join(tokens)
    original_facts = None
    from numeric_contract import numeric_facts
    original_facts = numeric_facts(" ".join(tokens), "en")
    while _word_count(" ".join(tokens)) > max_words:
        removed = False
        for idx in range(len(tokens) - 1, -1, -1):
            candidate_tokens = tokens[:idx] + tokens[idx + 1:]
            candidate = " ".join(candidate_tokens)
            if numeric_facts(candidate, "en") == original_facts:
                tokens = candidate_tokens
                removed = True
                break
        if not removed:
            break
    return " ".join(tokens).strip()


def _repair_hook(text: str, index: int, vehicle: str) -> str:
    text = str(text or "").strip()
    if index not in HOOK_SCENES:
        return text
    lower = text.lower()
    signals = {"shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange", "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never"}
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", text)
    has_signal = any(w in signals for w in re.findall(r"[a-z]+", lower)) or "?" in text or "!" in text
    open_loop = any(x in lower for x in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    if len(words) >= 18 and (has_signal or open_loop):
        return re.sub(r"[.!?]+\s*$", "?", text).strip()
    prefix = f"What hidden detail about {vehicle} could change how you understand its performance?"
    merged = f"{prefix} {text}".strip()
    merged = _trim_preserving_facts(merged, MAX_EN_WORDS)
    return re.sub(r"[.!?]+\s*$", "?", merged).strip()


def main() -> None:
    path = RUN / "long_story.json"
    story = json.loads(path.read_text(encoding="utf-8"))
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("STORY_PREFLIGHT: expected exactly 25 scenes")
    vehicle = os.getenv("CAR_VEHICLE", str(story.get("title", "the featured vehicle")))
    numeric_repairs = 0
    hook_repairs = 0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"STORY_PREFLIGHT: scene {index} is not an object")
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        if not en or not ar:
            raise RuntimeError(f"STORY_PREFLIGHT: scene {index} missing EN/AR text")
        repaired_hook = _repair_hook(en, index, vehicle)
        if repaired_hook != en or index in HOOK_SCENES:
            scene["text_en"] = repaired_hook
            scene["beat"] = "hook"
            hook_repairs += 1 if repaired_hook != en else 0
            en = repaired_hook
        if not _same_numeric_facts(en, ar):
            scene["text_ar"] = force_numeric_alignment(en, ar)
            numeric_repairs += 1
        if not _same_numeric_facts(en, str(scene.get("text_ar", ""))):
            raise RuntimeError(f"STORY_PREFLIGHT: scene {index} numeric alignment failed")
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"STORY_PREFLIGHT=PASS numeric_repairs={numeric_repairs} hook_repairs={hook_repairs}")


if __name__ == "__main__":
    main()
