from __future__ import annotations

import json, os, re
from pathlib import Path
from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
MIN_WORDS = 45
MAX_WORDS = 70
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))


def words(s: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", s))


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
            "description": "natural searchable description with the core topic",
            "tags": "8-15 relevant search tags",
            "scenes": 25,
            "scene_words": "45-70",
            "language": "en narrative + ar translation",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "beats": ["hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending"],
            "visual_rule": "pexels_query must describe concrete, searchable footage matching the scene meaning; avoid abstract queries",
        },
        "output": "JSON object with title, description, tags, and scenes array",
        "strict": "Every text_en scene must contain 45-70 English words. Count words before returning JSON. text_ar must faithfully translate text_en.",
    }, ensure_ascii=False)


def repair_scene(scene: dict, index: int, topic: str) -> dict:
    message = json.dumps({
        "task": "repair_scene",
        "topic": topic,
        "scene_number": index,
        "contract": {
            "text_en_words": "45-70 exactly",
            "text_en_language": "English only",
            "text_ar_language": "Arabic translation",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "visual_rule": "pexels_query must match the scene's concrete action or subject",
        },
        "scene": scene,
        "instruction": "Return JSON for this scene only. Preserve meaning and beat. Improve visual specificity. Count English words and ensure 45-70 before returning.",
    }, ensure_ascii=False)
    body = call(message, model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    repaired = extract_json(body)
    if isinstance(repaired, dict) and isinstance(repaired.get("scenes"), list):
        repaired = repaired["scenes"][0] if repaired["scenes"] else {}
    if not isinstance(repaired, dict):
        raise ValueError(f"scene {index} repair returned invalid JSON")
    return repaired


def normalize_story(story: dict, topic: str) -> dict:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != CFG["production"]["long_scene_count"]:
        raise ValueError("story must contain exactly 25 scenes")
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
    (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORY_GENERATION=PASS provider={story['provider']} scenes={len(story['scenes'])}")
    return story


if __name__ == "__main__":
    generate()
