from __future__ import annotations

import json, os, re, unicodedata
from pathlib import Path
from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
MIN_WORDS = 40
MAX_WORDS = 75
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))
COMMON_ENGLISH_IN_ARABIC = {
    "the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at", "of",
    "to", "for", "with", "from", "flame", "fire", "secret", "story", "city", "found", "people", "street",
}
ARABIC_COMMON_MISTAKES = {"فالقائز": "الفائز", "القائز": "الفائز", "يسام من": "يعاني من", "سيارة دعم قائمة": "سيارة دعم"}


def words(s: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", s))


def _safe_youtube_text(value: object, limit: int) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    cleaned = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in "\n\r\t" or not category.startswith("C"):
            cleaned.append(ch)
    text = "".join(cleaned).replace("\r\n", "\n").replace("\r", "\n").strip()
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
    result = []
    seen = set()
    for item in value[:15]:
        tag = _safe_youtube_text(item, 500).lstrip("#").strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return result


def _arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip()
    arabic_chars = len(re.findall(r"[\u0600-\u06ff]", value))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value))
    latin_words = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", value)]
    bad_common = sum(w in COMMON_ENGLISH_IN_ARABIC for w in latin_words)
    return arabic_chars >= 12 and (arabic_chars / max(1, letters)) >= 0.60 and bad_common == 0


def _arabic_errors(text: str) -> list[str]:
    value = str(text or "")
    errors = [f"{bad}->{good}" for bad, good in ARABIC_COMMON_MISTAKES.items() if bad in value]
    return errors


def _visual_query_ok(sc: dict) -> bool:
    query = str(sc.get("pexels_query", "")).strip()
    subject = str(sc.get("visual_subject", "")).strip()
    if not (3 <= len(query.split()) <= 9 and len(query) >= 12 and subject):
        return False
    abstract = {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"}
    if all(word.casefold() in abstract for word in query.split()):
        return False
    return True


def validate_scene(sc: dict, index: int) -> None:
    required = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")
    if not isinstance(sc, dict) or not all(str(sc.get(k, "")).strip() for k in required):
        raise ValueError(f"scene {index} missing required fields")
    n = words(sc["text_en"])
    if not MIN_WORDS <= n <= MAX_WORDS:
        raise ValueError(f"scene {index} has invalid English word count: {n}")
    if re.search(r"[\u0600-\u06ff]", sc["text_en"]):
        raise ValueError(f"scene {index} English contains Arabic")
    if not _arabic_quality_ok(sc["text_ar"]):
        errors = _arabic_errors(sc["text_ar"])
        raise ValueError(f"scene {index} Arabic translation quality check failed{': ' + ', '.join(errors) if errors else ''}")
    if not _visual_query_ok(sc):
        raise ValueError(f"scene {index} visual query is too abstract or underspecified")


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
            "title": "specific curiosity-driven English YouTube title, 45-85 chars when possible; never generic",
            "description": "natural searchable English description, plain text only, no control characters",
            "tags": "8-15 relevant English search tags, unique",
            "scenes": 25,
            "scene_words": "45-70 target; 40-75 accepted only as validator tolerance",
            "language": "English narration + native-quality, faithful Arabic translation for subtitles",
            "arabic_rule": "text_ar must be fluent Modern Standard Arabic written from the final English meaning. Never translate word-for-word. Preserve natural Arabic syntax, tense, gender, idioms and historical terminology. No ordinary English vocabulary such as street, flame, fire, secret, story, city, found. Proper names may remain as established names only when Arabic transliteration would reduce clarity.",
            "arabic_proofread": "Before returning JSON, proofread every Arabic scene as if for publication. Correct spelling, grammar, punctuation and awkward literal translations. Do not invent facts to make Arabic smoother.",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "beats": ["hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending"],
            "visual_rule": "pexels_query must describe concrete cinematic footage matching the visible action, object, person, location or environment in the scene. Use 3-9 concrete searchable words. For historical stories, prefer period-relevant objects, architecture, landscapes, documents, crowds or reenactment-like visuals; do not use modern sports footage for historical events unless the scene explicitly needs a modern comparison.",
            "hook_rule": "Scene 1 must open with a high-curiosity statement, question, contradiction or shocking consequence; never begin with a date, dry definition or 'In 19xx'.",
            "shorts_rule": "Scenes 1, 7, 13 and 19 are the openings of four independent Shorts; each opening must immediately hook a viewer and the six-scene block that follows must resolve a complete mini-story without requiring another Part.",
            "pacing_rule": "Use short spoken sentences, concrete nouns and escalating stakes. Put the strongest reveal late, but seed a reason to keep watching every scene.",
            "accuracy_rule": "Do not generalize a claim about one person to a group. Keep historical claims precise and avoid sensational wording that changes the factual meaning.",
        },
        "output": "JSON object with title, description, tags, and scenes array",
        "strict": "Return exactly 25 scenes. Count English words before returning JSON. text_ar must faithfully translate final text_en in natural Arabic. Do not use 'Part 1/2/3/4' in any title or scene text. Return JSON only.",
    }, ensure_ascii=False)


def repair_story(story: dict, topic: str) -> dict:
    expected = CFG["production"]["long_scene_count"]
    message = json.dumps({
        "task": "repair_story_structure",
        "topic": topic,
        "contract": {
            "exact_scene_count": expected,
            "scene_words": "45-70 target; 40-75 accepted only as validator tolerance",
            "language": "English narration + native-quality Arabic translation",
            "arabic_rule": "Arabic must sound like publication-quality Modern Standard Arabic, not word-for-word translation. No ordinary English words; proofread spelling and grammar.",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "beats": ["hook", "setup", "mystery", "escalation", "evidence", "reveal", "payoff", "ending"],
            "short_openers": [1, 7, 13, 19],
            "visual_rule": "pexels_query must be 3-9 concrete searchable words matching a visible subject/action/location",
            "accuracy_rule": "Do not generalize one person's action to a group; preserve factual scope.",
        },
        "story": story,
        "instruction": (
            f"Return complete story JSON with exactly {expected} scenes. Preserve the strongest facts and chronological order. "
            "Do not add filler scenes. Aim for 50-60 English words per scene. Ensure scenes 1, 7, 13 and 19 are strong standalone hooks. "
            "Rewrite every Arabic translation naturally from the final English meaning and proofread it. Improve visual specificity. Return JSON only."
        ),
    }, ensure_ascii=False)
    repaired = extract_json(call(message, model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
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
            "text_ar_language": "publication-quality Modern Standard Arabic, faithful to the final English meaning",
            "arabic_rule": "Rewrite Arabic naturally rather than word-for-word. Correct spelling, grammar and punctuation. No ordinary English words such as flame, fire, secret, story, city, street.",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "hook": index in {1, 7, 13, 19},
            "visual_rule": "concrete, cinematic, searchable Pexels wording; 3-9 words",
            "accuracy_rule": "Keep the claim scoped to the actual people/events in the source; do not sensationalize beyond the facts.",
        },
        "scene": scene,
        "instruction": (
            "Return JSON for this scene only. Preserve meaning and beat. Improve visual specificity, factual precision and Arabic fluency. "
            "Aim for 50-60 English words. For hook scenes, start with immediate curiosity and never with a date."
        ),
    }, ensure_ascii=False)
    repaired = extract_json(call(message, model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
    if isinstance(repaired, dict) and isinstance(repaired.get("scenes"), list):
        repaired = repaired["scenes"][0] if repaired["scenes"] else {}
    if not isinstance(repaired, dict):
        raise ValueError(f"scene {index} repair returned invalid JSON")
    return repaired


def normalize_metadata(story: dict, topic: str) -> dict:
    title = _safe_youtube_text(story.get("title", ""), 100)
    if not title or title.lower() in {"untitled", "untitled story", "story"}:
        title = _safe_youtube_text(topic.strip().rstrip("."), 100) or "The Hidden Story Behind a Shocking Event"
    story["title"] = title

    description = _safe_youtube_text(story.get("description", ""), 4700)
    description = re.sub(r"(?:^|\s)#[\w-]+", "", description)
    description = re.sub(r"\n{3,}", "\n\n", description).strip()
    if not description:
        description = f"Discover the hidden story behind {title}. A fast-paced historical mystery with evidence, context, and a final reveal."
    hashtags = "#History #Mystery #HistoryFacts"
    story["description"] = _safe_youtube_text(f"{description.rstrip()}\n\n{hashtags}", 5000)

    tags = _safe_tags(story.get("tags"))
    if not tags:
        tags = ["history", "historical facts", "history mystery", "mystery", "did you know", "history documentary", "history shorts"]
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
            except ValueError as exc:
                if attempt >= REPAIR_RETRIES:
                    raise
                print(f"SCENE_REPAIR scene={index} attempt={attempt + 1}/{REPAIR_RETRIES} reason={exc}")
                scene = repair_scene(scene, index, topic)
                scenes[index - 1] = scene
    validate_story(story)
    return story


def generate() -> dict:
    run = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
    run.mkdir(parents=True, exist_ok=True)
    topic = os.getenv("VIDEO_TOPIC", "The hidden story behind a surprising historical event")
    body = call(prompt(topic), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"))
    story = normalize_story(extract_json(body), topic)
    story["provider"] = body.get("provider", "Odysseus")
    (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = {"title": story["title"], "description": story["description"], "tags": story["tags"]}
    (run / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORY_GENERATION=PASS provider={story['provider']} scenes={len(story['scenes'])} metadata=normalized arabic=strict visuals=strict")
    return story


if __name__ == "__main__":
    generate()
