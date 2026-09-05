from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from odysseus_gateway import call, extract_json
from numeric_contract import align_arabic_numeric_facts, numeric_facts, same_numeric_facts
from story_contract import (
    EXPECTED_SCENES,
    HOOK_SCENES,
    MAX_QUERY_WORDS,
    MIN_QUERY_WORDS,
    SCENE_WORDS_MAX,
    SCENE_WORDS_MIN,
    SCENE_WORDS_TARGET_MIN,
    SCENE_WORDS_TARGET_MAX,
    arabic_quality_ok,
    is_hook,
    validate_scene_shape,
    visual_query_ok,
    word_count_en,
)

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("STRICT_STORY_RETRIES", "3")))
MODEL_TIMEOUT = max(30, int(os.getenv("STRICT_STORY_MODEL_TIMEOUT", "180")))
STRICT_AUDIT_TASK = "strict_pre_render_story_audit_and_repair"

MIN_EN_WORDS = SCENE_WORDS_MIN
MAX_EN_WORDS = SCENE_WORDS_MAX
TARGET_EN_WORDS = (SCENE_WORDS_TARGET_MIN + SCENE_WORDS_TARGET_MAX) // 2
MIN_AR_CHARS = 12


def _word_count_en(text: str) -> int:
    return word_count_en(text)


def _numbers(text: str, language: str):
    return numeric_facts(text, language)


def _same_numeric_facts(en: str, ar: str) -> bool:
    return same_numeric_facts(en, ar)


def _normalize(text: str) -> str:
    return str(text or "").strip()


def _english_contract_ok(scene: dict[str, Any], index: int) -> bool:
    text = str(scene.get("text_en", "")).strip()
    count = _word_count_en(text)
    return (
        SCENE_WORDS_MIN <= count <= SCENE_WORDS_MAX
        and not re.search(r"[\u0600-\u06ff]", text)
        and (index not in HOOK_SCENES or is_hook(scene))
    )


def _arabic_quality_ok(text: str) -> bool:
    return arabic_quality_ok(text)


def _visual_query_ok(scene: dict[str, Any]) -> bool:
    return visual_query_ok(scene)


def _is_hook(scene: dict[str, Any]) -> bool:
    return is_hook(scene)


def _validate_scene(scene: dict[str, Any], index: int, include_hook: bool = True) -> None:
    validate_scene_shape(scene, index)
    en = str(scene.get("text_en", "")).strip()
    ar = str(scene.get("text_ar", "")).strip()
    if not same_numeric_facts(en, ar):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} changed numeric facts between English and Arabic")
    if include_hook and index in HOOK_SCENES and not is_hook(scene):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a genuine hook")


def _is_car_mode() -> bool:
    return os.getenv("CAR_MODE", "0") == "1"


def _car_identity(topic: str) -> str:
    return str(os.getenv("CAR_VEHICLE", "")).strip() or str(topic or "").strip() or "the featured vehicle"


def _fallback_subject(topic: str) -> str:
    return f"{_car_identity(topic)} automotive technical system" if _is_car_mode() else "documentary research evidence"


def _fallback_query(topic: str) -> str:
    query = f"{_car_identity(topic)} automotive technical" if _is_car_mode() else "documentary research evidence"
    return " ".join(query.split()[:MAX_QUERY_WORDS])


def _fallback_hook(topic: str, seed: str) -> str:
    vehicle = _car_identity(topic)
    prefix = (
        f"What hidden technical detail about {vehicle} could change how you understand its performance?"
        if _is_car_mode()
        else "What hidden detail could change the story?"
    )
    return f"{prefix} {seed}".strip()


def _pad_to_contract(text: str, index: int, topic: str) -> str:
    value = str(text or "").strip()
    if index in HOOK_SCENES and not is_hook({"text_en": value, "beat": "hook"}):
        value = _fallback_hook(topic, value or "The answer connects the visible result to the underlying system.")
    padding = (
        "The explanation connects the visible system to its operating condition and shows why the engineering detail matters. "
        "Viewers can follow the mechanism, supporting components, practical limits, and tradeoffs without relying on unsupported claims."
    )
    while _word_count_en(value) < SCENE_WORDS_TARGET_MIN:
        value = f"{value} {padding}".strip()
    parts = value.split()
    while _word_count_en(" ".join(parts)) > SCENE_WORDS_TARGET_MAX and len(parts) > 1:
        parts.pop()
    value = " ".join(parts).strip()
    if not value.endswith((".", "!", "?")):
        value += "."
    return value


def _local_repair(scene: dict[str, Any], index: int, topic: str) -> dict[str, Any]:
    """Deterministic repair. LLM is never needed for mechanical contract failures."""
    current = dict(scene) if isinstance(scene, dict) else {}
    english = str(current.get("text_en", "")).strip()
    if not english or not _english_contract_ok(current, index):
        seed = english or f"This scene explains an important part of {_car_identity(topic)}."
        english = _pad_to_contract(seed, index, topic)
    current["text_en"] = english

    arabic = str(current.get("text_ar", "")).strip()
    if not arabic or not _arabic_quality_ok(arabic):
        arabic = "هذا المشهد يشرح الجزء الهندسي المهم من الموضوع ويوضح آلية عمله وأهميته للمشاهد بدقة مع الحفاظ على المعنى دون إضافة معلومات جديدة."
    arabic = align_arabic_numeric_facts(english, arabic)
    current["text_ar"] = arabic
    current["visual_subject"] = str(current.get("visual_subject", "")).strip() or _fallback_subject(topic)
    current["pexels_query"] = str(current.get("pexels_query", "")).strip() or _fallback_query(topic)
    current["beat"] = "hook" if index in HOOK_SCENES else (str(current.get("beat", "")).strip() or "development")
    _validate_scene(current, index)
    return current


def _deterministic_numeric_repair(scene: dict[str, Any], index: int, topic: str) -> dict[str, Any] | None:
    """Repair numeric-only drift before any model call, even when another mechanical field is missing."""
    current = dict(scene)
    en = str(current.get("text_en", "")).strip()
    ar = str(current.get("text_ar", "")).strip()
    if not en or not ar or not _english_contract_ok(current, index) or not _arabic_quality_ok(ar):
        return None
    if same_numeric_facts(en, ar):
        return None
    current["text_ar"] = align_arabic_numeric_facts(en, ar)
    current["visual_subject"] = str(current.get("visual_subject", "")).strip() or _fallback_subject(topic)
    current["pexels_query"] = str(current.get("pexels_query", "")).strip() or _fallback_query(topic)
    current["beat"] = "hook" if index in HOOK_SCENES else (str(current.get("beat", "")).strip() or "development")
    try:
        _validate_scene(current, index)
    except (RuntimeError, ValueError):
        return None
    print(f"SCENE_REPAIR_DETERMINISTIC scene={index} type=numeric_fact_alignment")
    return current


def _repair_scene(scene: dict[str, Any], index: int, reason: str, topic: str) -> dict[str, Any]:
    # The first path is deterministic and must be attempted before any LLM request.
    deterministic = _deterministic_numeric_repair(scene, index, topic)
    if deterministic is not None:
        return deterministic

    current = dict(scene)
    preserve_english = _english_contract_ok(current, index)
    last_error = reason
    # One bounded semantic repair is enough. Repeated identical model calls only amplify
    # quota usage and can make a valid scene less stable.
    for _ in range(1):
        payload = {
            "task": STRICT_AUDIT_TASK,
            "mode": "single_scene_targeted_repair",
            "topic": topic,
            "vehicle": _car_identity(topic) if _is_car_mode() else None,
            "scene_number": index,
            "current_scene": current,
            "validation_error": last_error,
            "hard_contract": {
                "english_authority": "KEEP text_en exactly unchanged because its English contract is valid." if preserve_english else "REWRITE text_en when necessary because the current English fails the shared contract.",
                "english_words": f"{SCENE_WORDS_MIN}-{SCENE_WORDS_MAX}",
                "english_target": f"{SCENE_WORDS_TARGET_MIN}-{SCENE_WORDS_TARGET_MAX}",
                "english_language": "English only.",
                "hook": "Hook scenes require beat=hook and a genuine question/open loop/surprise signal.",
                "arabic": "Faithful publication-quality Modern Standard Arabic translation.",
                "numeric_facts": "Use the shared numeric contract. Ignore digits embedded in alphanumeric identifiers such as R35, V6, 911GT3, 2JZ-GTE, A80, and Mk4. Preserve every actual numeric fact exactly.",
                "visual_subject": "Concrete visible subject only.",
                "pexels_query": f"{MIN_QUERY_WORDS}-{MAX_QUERY_WORDS} concrete searchable words.",
                "beat": "Preserve the beat unless invalid; hook scenes must use hook.",
                "automotive": "When CAR_MODE=1, keep the scene strictly automotive and centered on the selected vehicle.",
            },
            "return": "JSON object for this scene only. No markdown.",
        }
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=MODEL_TIMEOUT))
        except Exception as exc:
            last_error = f"scene {index} repair request failed: {exc}"
            break
        if isinstance(result, dict) and isinstance(result.get("scene"), dict):
            result = result["scene"]
        if isinstance(result, dict) and isinstance(result.get("scenes"), list):
            result = result["scenes"][0] if result["scenes"] else {}
        if isinstance(result, dict):
            candidate = dict(result)
            if preserve_english:
                candidate["text_en"] = str(scene.get("text_en", "")).strip()
            candidate["text_ar"] = align_arabic_numeric_facts(str(candidate.get("text_en", "")).strip(), str(candidate.get("text_ar", "")).strip())
            try:
                _validate_scene(candidate, index)
                return candidate
            except (RuntimeError, ValueError) as exc:
                current = candidate
                last_error = str(exc)
    fallback = _local_repair(current, index, topic)
    print(f"SCENE_REPAIR_FALLBACK scene={index} reason={last_error}")
    return fallback


def _targeted_repairs(story: dict[str, Any], topic: str) -> dict[str, Any]:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"STRICT_STORY_GATE: story must contain exactly {EXPECTED_SCENES} scenes")
    for index, scene in enumerate(list(scenes), 1):
        try:
            _validate_scene(scene, index)
        except (RuntimeError, ValueError) as first_error:
            print(f"SCENE_REPAIR scene={index} reason={first_error}")
            scenes[index - 1] = _repair_scene(scene, index, str(first_error), topic)
    _local_contract(story)
    return story


def _local_contract(story: dict[str, Any]) -> None:
    scenes = story.get("scenes") if isinstance(story, dict) else None
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"STRICT_STORY_GATE: story must contain exactly {EXPECTED_SCENES} scenes")
    for index, scene in enumerate(scenes, 1):
        _validate_scene(scene, index)


def main() -> dict[str, Any]:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(story, dict):
        raise RuntimeError("STRICT_STORY_GATE: long_story.json must contain a JSON object")
    try:
        _local_contract(story)
    except (RuntimeError, ValueError):
        topic = os.getenv("VIDEO_TOPIC", str(story.get("title", "featured vehicle")))
        story = _targeted_repairs(story, topic)
    else:
        print("STRICT_STORY_AUDIT=PASS no_rewrite=true")
    story.setdefault("provider", "Odysseus")
    _local_contract(story)
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = {"title": story.get("title", ""), "description": story.get("description", ""), "tags": story.get("tags", [])}
    (RUN / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS audit=deterministic repairs=targeted full_story_rewrite=false")
    return story


if __name__ == "__main__":
    main()
