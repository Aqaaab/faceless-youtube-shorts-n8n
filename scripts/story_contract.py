from __future__ import annotations

import re

SCENE_WORDS_MIN = 55
SCENE_WORDS_MAX = 65
SCENE_WORDS_TARGET_MIN = 56
SCENE_WORDS_TARGET_MAX = 64
EXPECTED_SCENES = 25
HOOK_SCENES = frozenset({1, 7, 13, 19})
MIN_AR_CHARS = 12
MIN_QUERY_WORDS = 3
MAX_QUERY_WORDS = 9

REQUIRED_SCENE_FIELDS = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")

_EN_TOKEN_RE = re.compile(r"\b(?:[A-Za-z][A-Za-z0-9'\-]*|[0-9]+(?:[.,][0-9]+)?)\b")

HOOK_WORDS = frozenset({
    "shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange",
    "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never",
})
COMMON_ENGLISH_IN_ARABIC = frozenset({
    "the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at",
    "of", "to", "for", "with", "from", "story", "city", "found", "people", "street", "fire",
    "flame", "secret", "mystery",
})


def word_count_en(text: str) -> int:
    return len(_EN_TOKEN_RE.findall(str(text or "")))


def english_tokens(text: str) -> list[str]:
    return _EN_TOKEN_RE.findall(str(text or ""))


def arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip()
    arabic = len(re.findall(r"[\u0600-\u06ff]", value))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value))
    latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'\-]*\b", value)]
    return (
        arabic >= MIN_AR_CHARS
        and arabic / max(1, letters) >= 0.60
        and not any(word in COMMON_ENGLISH_IN_ARABIC for word in latin)
    )


def visual_query_ok(scene: dict) -> bool:
    query = str(scene.get("pexels_query", "")).strip()
    subject = str(scene.get("visual_subject", "")).strip()
    abstract = {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"}
    words = query.split()
    return bool(
        subject
        and MIN_QUERY_WORDS <= len(words) <= MAX_QUERY_WORDS
        and len(query) >= 12
        and not all(word.casefold() in abstract for word in words)
    )


def is_hook(scene: dict) -> bool:
    text = str(scene.get("text_en", "")).strip().lower()
    words = re.findall(r"[a-z][a-z'\-]*", text)
    signal = any(word in HOOK_WORDS for word in words) or "?" in text or "!" in text
    open_loop = any(x in text for x in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    return str(scene.get("beat", "")).strip().lower() == "hook" and len(words) >= 18 and (signal or open_loop)


def validate_scene_shape(scene: dict, index: int) -> None:
    if not isinstance(scene, dict):
        raise ValueError(f"scene {index} is not an object")
    if not all(str(scene.get(key, "")).strip() for key in REQUIRED_SCENE_FIELDS):
        raise ValueError(f"scene {index} missing required content")
    text_en = str(scene["text_en"]).strip()
    count = word_count_en(text_en)
    if not SCENE_WORDS_MIN <= count <= SCENE_WORDS_MAX:
        raise ValueError(f"scene {index} has invalid English word count: {count}; required {SCENE_WORDS_MIN}-{SCENE_WORDS_MAX}")
    if re.search(r"[\u0600-\u06ff]", text_en):
        raise ValueError(f"scene {index} English contains Arabic")
    if not arabic_quality_ok(str(scene["text_ar"])):
        raise ValueError(f"scene {index} Arabic translation quality check failed")
    if not visual_query_ok(scene):
        raise ValueError(f"scene {index} visual query is too abstract or underspecified")
    if index in HOOK_SCENES and not is_hook(scene):
        raise ValueError(f"scene {index} must be a genuine hook")


def story_shape_ok(story: dict) -> bool:
    scenes = story.get("scenes") if isinstance(story, dict) else None
    return isinstance(scenes, list) and len(scenes) == EXPECTED_SCENES
