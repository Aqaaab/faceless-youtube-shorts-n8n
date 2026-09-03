from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
MIN_WORDS = 40
MAX_WORDS = 75
TARGET_MIN_WORDS = 45
TARGET_MAX_WORDS = 70
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))
COMMON_ENGLISH_IN_ARABIC = {"the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at", "of", "to", "for", "with", "from", "flame", "fire", "secret", "story", "city", "found", "people", "street"}
ARABIC_COMMON_MISTAKES = {"فالقائز": "الفائز", "القائز": "الفائز", "يسام من": "يعاني من", "سيارة دعم قائمة": "سيارة دعم"}


def words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", str(text or "")))


def _safe_text(value: object, limit: int) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 > limit:
        encoded = encoded[: limit * 2]
        if len(encoded) >= 2 and 0xD800 <= int.from_bytes(encoded[-2:], "little") <= 0xDBFF:
            encoded = encoded[:-2]
        text = encoded.decode("utf-16-le", errors="ignore").rstrip()
    return text


def _safe_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for item in value[:15]:
        tag = _safe_text(item, 500).lstrip("#").strip()
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            result.append(tag)
    return result


def _arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip()
    arabic = len(re.findall(r"[\u0600-\u06ff]", value))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value))
    latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", value)]
    return arabic >= 12 and arabic / max(1, letters) >= 0.60 and not any(w in COMMON_ENGLISH_IN_ARABIC for w in latin)


def _visual_query_ok(scene: dict) -> bool:
    query = str(scene.get("pexels_query", "")).strip()
    subject = str(scene.get("visual_subject", "")).strip()
    abstract = {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"}
    return bool(subject and 3 <= len(query.split()) <= 9 and len(query) >= 12 and not all(w.casefold() in abstract for w in query.split()))


def validate_scene(scene: dict, index: int) -> None:
    required = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")
    if not isinstance(scene, dict) or not all(str(scene.get(key, "")).strip() for key in required):
        raise ValueError(f"scene {index} missing required fields")
    count = words(scene["text_en"])
    if not MIN_WORDS <= count <= MAX_WORDS:
        raise ValueError(f"scene {index} has invalid English word count: {count}; required {MIN_WORDS}-{MAX_WORDS}")
    if re.search(r"[\u0600-\u06ff]", str(scene["text_en"])):
        raise ValueError(f"scene {index} English contains Arabic")
    if not _arabic_quality_ok(scene["text_ar"]):
        raise ValueError(f"scene {index} Arabic translation quality check failed")
    if not _visual_query_ok(scene):
        raise ValueError(f"scene {index} visual query is too abstract or underspecified")


def validate_story(story: dict) -> None:
    scenes = story.get("scenes")
    expected = CFG["production"]["long_scene_count"]
    if not isinstance(scenes, list) or len(scenes) != expected:
        raise ValueError(f"story must contain exactly {expected} scenes")
    if not str(story.get("title", "")).strip() or not str(story.get("description", "")).strip() or not isinstance(story.get("tags"), list) or not story["tags"]:
        raise ValueError("story metadata is incomplete")
    for index, scene in enumerate(scenes, 1):
        validate_scene(scene, index)


def _story_prompt(topic: str) -> str:
    return json.dumps({"task": "long_story", "topic": topic, "contract": {"scenes": 25, "scene_words": "45-70 target; 40-75 hard limit", "language": "English narration with faithful publication-quality Modern Standard Arabic", "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"], "visual_rule": "pexels_query must be 3-9 concrete searchable words", "arabic_rule": "No ordinary English words in Arabic subtitles; proofread every scene"}, "output": "JSON only with title, description, tags and scenes"}, ensure_ascii=False)


def repair_story(story: dict, topic: str) -> dict:
    expected = CFG["production"]["long_scene_count"]
    payload = {"task": "repair_story_structure", "topic": topic, "story": story, "contract": {"exact_scene_count": expected, "scene_words": "45-70 target; 40-75 hard limit", "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"]}, "instruction": f"Return complete JSON with exactly {expected} scenes. Every English scene must contain {TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} words and never fewer than {MIN_WORDS}. Return JSON only."}
    result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
    if not isinstance(result, dict):
        raise ValueError("story structure repair returned invalid JSON")
    return result


def repair_scene(scene: dict, index: int, topic: str, previous_error: str = "") -> dict:
    current = scene
    last_error = previous_error
    for attempt in range(REPAIR_RETRIES):
        payload = {"task": "repair_scene", "topic": topic, "scene_number": index, "scene": current, "validation_error": last_error, "contract": {"text_en_words": f"{TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} target; {MIN_WORDS}-{MAX_WORDS} hard limit", "text_en_language": "English only", "text_ar_language": "publication-quality Modern Standard Arabic", "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"]}, "instruction": f"Return this scene only. Count the English words before responding. The result MUST contain {MIN_WORDS}-{MAX_WORDS} English words; aim for {TARGET_MIN_WORDS}-{TARGET_MAX_WORDS}. Do not return a short scene. Preserve facts and meaning. Return JSON only."}
        result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
        if isinstance(result, dict) and isinstance(result.get("scenes"), list):
            result = result["scenes"][0] if result["scenes"] else {}
        if not isinstance(result, dict):
            last_error = f"scene {index} repair returned invalid JSON"
            continue
        try:
            validate_scene(result, index)
            return result
        except ValueError as exc:
            current, last_error = result, str(exc)
    raise ValueError(last_error or f"scene {index} repair failed validation")


def normalize_metadata(story: dict, topic: str) -> dict:
    title = _safe_text(story.get("title"), 100)
    story["title"] = title or _safe_text(topic, 100) or "The Hidden Story Behind a Shocking Event"
    description = re.sub(r"(?:^|\s)#[\w-]+", "", _safe_text(story.get("description"), 4700)).strip()
    story["description"] = _safe_text((description or f"Discover the hidden story behind {story['title']}.") + "\n\n#History #Mystery #HistoryFacts", 5000)
    story["tags"] = _safe_tags(story.get("tags")) or ["history", "historical facts", "history mystery", "mystery", "history documentary", "history shorts"]
    return story


def normalize_story(story: dict, topic: str) -> dict:
    expected = CFG["production"]["long_scene_count"]
    for attempt in range(REPAIR_RETRIES + 1):
        if isinstance(story, dict) and isinstance(story.get("scenes"), list) and len(story["scenes"]) == expected:
            break
        if attempt >= REPAIR_RETRIES:
            raise ValueError(f"story must contain exactly {expected} scenes")
        story = repair_story(story if isinstance(story, dict) else {}, topic)
    story = normalize_metadata(story, topic)
    scenes = story["scenes"]
    for index, scene in enumerate(scenes, 1):
        try:
            validate_scene(scene, index)
        except ValueError as exc:
            print(f"SCENE_REPAIR scene={index} reason={exc}")
            scenes[index - 1] = repair_scene(scene, index, topic, str(exc))
    validate_story(story)
    return story


def generate() -> dict:
    run = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
    run.mkdir(parents=True, exist_ok=True)
    topic = os.getenv("VIDEO_TOPIC", "The hidden story behind a surprising historical event")
    body = call(_story_prompt(topic), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    story = normalize_story(extract_json(body), topic)
    story["provider"] = body.get("provider", "Odysseus") if isinstance(body, dict) else "Odysseus"
    (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run / "metadata.json").write_text(json.dumps({"title": story["title"], "description": story["description"], "tags": story["tags"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORY_GENERATION=PASS provider={story['provider']} scenes={len(story['scenes'])} metadata=normalized arabic=strict visuals=strict")
    return story


if __name__ == "__main__":
    generate()
