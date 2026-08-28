from __future__ import annotations

import json, os, re, unicodedata
from pathlib import Path
from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
MIN_WORDS = 40
MAX_WORDS = 75
TARGET_MIN_WORDS = 45
TARGET_MAX_WORDS = 70
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))


def words(s: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", s))


def _safe_youtube_text(value: object, limit: int) -> str:
    """Return metadata safe for YouTube's UTF-16 based text limits."""
    text = unicodedata.normalize("NFC", str(value or ""))
    out: list[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        # Keep normal printable Unicode plus whitespace needed for descriptions.
        if ch in "\n\r\t" or not category.startswith("C"):
            out.append(ch)
    text = "".join(out).replace("\r\n", "\n").replace("\r", "\n").strip()
    units = len(text.encode("utf-16-le")) // 2
    if units > limit:
        encoded = text.encode("utf-16-le")[: limit * 2]
        # Never leave a dangling high surrogate after truncation.
        if len(encoded) >= 2 and 0xD800 <= int.from_bytes(encoded[-2:], "little") <= 0xDBFF:
            encoded = encoded[:-2]
        text = encoded.decode("utf-16-le", errors="ignore").rstrip()
    return text


def _safe_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:15]:
        tag = _safe_youtube_text(item, 500)
        if tag:
            result.append(tag)
    return result


def validate_scene(sc: dict, index: int) -> None:
    required = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")
    if not isinstance(sc, dict) or not all(str(sc.get(k, "")).strip() for k in required):
        raise ValueError(f"scene {index} missing required fields")
    n = words(sc["text_en"])
    if not MIN_WORDS <= n <= MAX_WORDS:
        raise ValueError(f"scene {index} has invalid English word count: {n}")
    if re.search(r"[\u0600-\u06ff]", sc["text_en"]):
        raise ValueError(f"scene {index} English contains Arabic")
    if not re.search(r"[\u0600-\u06ff]", sc["text_ar"]):
        raise ValueError(f"scene {index} Arabic missing")


def validate_story(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != CFG["production"]["long_scene_count"]:
        raise ValueError("story must contain exactly 25 scenes")
    title = str(story.get("title", "")).strip()
    description = str(story.get("description", "")).strip()
    tags = story.get("tags")
    if not title or title.lower() in {"untitled", "untitled story", "story"}:
        raise ValueError("story title is missing or generic")
    if not description:
        raise ValueError("story description is missing")
    if not isinstance(tags, list) or not tags:
        raise ValueError("story tags are missing")
    for i, scene in enumerate(scenes, 1):
        validate_scene(scene, i)


def prompt(topic: str) -> str:
    return json.dumps({
        "task": "long_story",
        "topic": topic,
        "contract": {
            "title": "specific curiosity-driven YouTube title, never generic",
            "description": "natural searchable description with the core topic; plain text only, no control characters",
            "tags": "8-15 relevant search tags",
            "scenes": 25,
            "scene_words": "45-70 target; 40-75 accepted only as validator tolerance",
            "language": "en narrative + ar translation",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "beats": ["hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending"],
            "visual_rule": "pexels_query must describe concrete, searchable footage matching the scene meaning; avoid abstract queries",
        },
        "output": "JSON object with title, description, tags, and scenes array",
        "strict": "Return exactly 25 scenes. Every text_en scene should contain 45-70 English words. Count words before returning JSON. text_ar must faithfully translate text_en.",
    }, ensure_ascii=False)


def repair_story(story: dict, topic: str) -> dict:
    expected = CFG["production"]["long_scene_count"]
    message = json.dumps({
        "task": "repair_story_structure",
        "topic": topic,
        "contract": {
            "exact_scene_count": expected,
            "scene_words": "45-70 target; 40-75 accepted only as validator tolerance",
            "language": "en narrative + ar translation",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "beats": ["hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending"],
            "visual_rule": "pexels_query must describe concrete, searchable footage matching the scene meaning; avoid abstract queries",
        },
        "story": story,
        "instruction": (
            f"Return the complete story JSON with exactly {expected} scenes. "
            "Preserve the strongest existing narrative facts and chronological order. "
            "If scenes are missing, split or expand existing narrative beats naturally; "
            "if there are extra scenes, merge redundant beats without losing important facts. "
            "Do not duplicate scenes merely to reach the count. Keep every scene concrete and visually searchable. "
            "Aim for 50-60 English words per scene and count them before returning. "
            "Keep text_ar faithful to the final text_en. Return JSON only."
        ),
    }, ensure_ascii=False)
    body = call(message, model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    repaired = extract_json(body)
    if not isinstance(repaired, dict):
        raise ValueError("story structure repair returned invalid JSON")
    return repaired


def repair_scene(scene: dict, index: int, topic: str) -> dict:
    message = json.dumps({
        "task": "repair_scene",
        "topic": topic,
        "scene_number": index,
        "contract": {
            "text_en_words": "45-70 target; never below 40 or above 75",
            "text_en_language": "English only",
            "text_ar_language": "Arabic translation",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "visual_rule": "pexels_query must match the scene's concrete action or subject",
        },
        "scene": scene,
        "instruction": "Return JSON for this scene only. Preserve meaning and beat. Improve visual specificity. Aim for 50-60 English words, then count the words before returning. Keep the Arabic translation faithful to the final English text.",
    }, ensure_ascii=False)
    body = call(message, model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    repaired = extract_json(body)
    if isinstance(repaired, dict) and isinstance(repaired.get("scenes"), list):
        repaired = repaired["scenes"][0] if repaired["scenes"] else {}
    if not isinstance(repaired, dict):
        raise ValueError(f"scene {index} repair returned invalid JSON")
    return repaired


def normalize_metadata(story: dict, topic: str) -> dict:
    title = _safe_youtube_text(story.get("title", ""), 100)
    if not title or title.lower() in {"untitled", "untitled story", "story"}:
        title = _safe_youtube_text(topic.strip().rstrip("."), 100) or "The Hidden Story Behind a Surprising Event"
    story["title"] = title

    description = _safe_youtube_text(story.get("description", ""), 5000)
    if not description:
        description = f"Discover the hidden story behind {title}. A fast-paced history story with key evidence, context, and a final reveal."
    story["description"] = _safe_youtube_text(description, 5000)

    tags = _safe_tags(story.get("tags"))
    if not tags:
        tags = ["history", "historical facts", "mystery", "did you know", "shorts", "history shorts"]
    story["tags"] = tags
    return story


def normalize_story(story: dict, topic: str) -> dict:
    expected = CFG["production"]["long_scene_count"]
    for attempt in range(REPAIR_RETRIES + 1):
        scenes = story.get("scenes") if isinstance(story, dict) else None
        if isinstance(scenes, list) and len(scenes) == expected:
            break
        if attempt >= REPAIR_RETRIES:
            raise ValueError(f"story must contain exactly {expected} scenes")
        print(f"STORY_STRUCTURE_REPAIR attempt={attempt + 1}/{REPAIR_RETRIES} expected={expected}")
        story = repair_story(story if isinstance(story, dict) else {}, topic)

    story = normalize_metadata(story, topic)
    scenes = story["scenes"]
    for index, scene in enumerate(scenes, 1):
        for attempt in range(REPAIR_RETRIES + 1):
            try:
                validate_scene(scene, index)
                break
            except ValueError:
                if attempt >= REPAIR_RETRIES:
                    raise
                scene = repair_scene(scene, index, topic)
                scenes[index - 1] = scene
    validate_story(story)
    return story


def generate() -> dict:
    run = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
    run.mkdir(parents=True, exist_ok=True)
    topic = os.getenv("VIDEO_TOPIC", "The hidden story behind a surprising historical event")
    body = call(prompt(topic), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    story = extract_json(body)
    story = normalize_story(story, topic)
    story["provider"] = body.get("provider", "Odysseus")
    payload = json.dumps(story, ensure_ascii=False, indent=2) + "\n"
    (run / "long_story.json").write_text(payload, encoding="utf-8")
    metadata = {"title": story["title"], "description": story["description"], "tags": story["tags"]}
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORY_GENERATION=PASS provider={story['provider']} scenes={len(story['scenes'])} metadata=normalized")
    return story


if __name__ == "__main__":
    generate()
