from __future__ import annotations

import json
import re
from pathlib import Path

MIN_LONG, MAX_LONG = 420.0, 900.0
MIN_SCENE, MAX_SCENE = 5.0, 60.0
MIN_WORDS, MAX_WORDS = 25, 75
ALLOWED_LAYOUTS = {"hero", "technical", "spec", "comparison", "diagram", "timeline"}
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_MIN, SHORT_MAX = 28.0, 59.0

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _numeric_tokens(text: str) -> set[str]:
    normalized = str(text).translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")
    return set(re.findall(r"\d+(?:[.,]\d+)?", normalized))


def _validate_callouts(callouts, narration, sid):
    errors = []
    narration_numbers = _numeric_tokens(narration)
    for callout in callouts:
        if not isinstance(callout, str):
            errors.append(f"scene {sid} callouts must contain strings")
            continue
        missing = sorted(_numeric_tokens(callout) - narration_numbers)
        if missing:
            errors.append(f"scene {sid} callout introduces unsupported numeric claim(s): {', '.join(missing)}")
    return errors


def _validate_short_titles(data, errors):
    titles = data.get("short_titles", [])
    if not isinstance(titles, list) or len(titles) != 4:
        errors.append("exactly 4 standalone short_titles are required")
        return
    normalized = []
    for i, title in enumerate(titles, 1):
        value = str(title).strip()
        if not 20 <= len(value) <= 80:
            errors.append(f"short title {i} must be 20-80 characters")
        if value.casefold() in {"short 1", "short 2", "short 3", "short 4", "untitled", "untitled story"}:
            errors.append(f"short title {i} is generic")
        if not re.search(r"[\u0600-\u06ff]", value):
            errors.append(f"short title {i} must contain Arabic text")
        normalized.append(value.casefold())
    if len(set(normalized)) != 4:
        errors.append("Short titles must be unique")


def validate_story_data(data: dict) -> bool:
    """Validate an already-parsed story payload before rendering or publishing."""
    if not isinstance(data, dict):
        raise AssertionError("STORY VALIDATION FAILED: root payload must be an object")

    errors = []
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list):
        errors.append("scenes must be a list")
        scenes = []
    if len(scenes) != 25:
        errors.append(f"scene count must be exactly 25, got {len(scenes)}")

    ids = [s.get("id") if isinstance(s, dict) else None for s in scenes]
    if ids != list(range(1, 26)):
        errors.append(f"scene ids must be exactly 1..25, got {ids}")

    numeric_durations = []
    for s in scenes:
        if isinstance(s, dict):
            try:
                numeric_durations.append(float(s.get("duration", 0)))
            except (TypeError, ValueError):
                numeric_durations.append(0.0)
                errors.append(f"scene {s.get('id')} duration is not numeric")
        else:
            numeric_durations.append(0.0)
    total = sum(numeric_durations)
    if not MIN_LONG <= total <= MAX_LONG:
        errors.append(f"planned duration {total:.1f}s outside 420-900")

    layouts, intents = [], []
    callout_scenes = 0
    for index, s in enumerate(scenes, 1):
        if not isinstance(s, dict):
            errors.append(f"scene {index} must be an object")
            continue
        sid = s.get("id")
        for key in ("id", "narration", "visual_intent", "layout", "duration"):
            if s.get(key) in (None, "", []): errors.append(f"scene {sid} missing {key}")
        try:
            duration = float(s.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
        if not MIN_SCENE <= duration <= MAX_SCENE: errors.append(f"scene {sid} duration {duration:.1f}s outside 5-60")
        narration = str(s.get("narration", "")).strip()
        intent = str(s.get("visual_intent", "")).strip()
        layout = str(s.get("layout", "")).strip().lower()
        words = _words(narration)
        if words < MIN_WORDS or words > MAX_WORDS: errors.append(f"scene {sid} narration must be 25-75 words (got {words})")
        if not re.search(r"[\u0600-\u06ff]", narration): errors.append(f"scene {sid} narration must contain Arabic text")
        if _words(intent) < 4: errors.append(f"scene {sid} visual intent too short")
        if layout not in ALLOWED_LAYOUTS: errors.append(f"scene {sid} unsupported layout '{layout}'")
        callouts = s.get("callouts", [])
        if not isinstance(callouts, list):
            errors.append(f"scene {sid} callouts must be a list")
        else:
            if len(callouts) > 5: errors.append(f"scene {sid} has more than 5 callouts")
            if callouts:
                callout_scenes += 1
                errors.extend(_validate_callouts(callouts, narration, sid))
        layouts.append(layout); intents.append(intent.casefold())

    if len(set(layouts)) < 4: errors.append(f"visual layout diversity too low: {len(set(layouts))}/4")
    if callout_scenes < 12: errors.append(f"technical visual coverage too low: {callout_scenes}/25 scenes have callouts")
    if len(set(intents)) < 20: errors.append(f"visual intents too repetitive: {len(set(intents))}/20 unique")

    by_id = {int(s["id"]): s for s in scenes if isinstance(s, dict) and str(s.get("id", "")).isdigit()}
    for group_no, group in enumerate(SHORT_GROUPS, 1):
        if all(i in by_id for i in group):
            try: d = sum(float(by_id[i]["duration"]) for i in group)
            except (TypeError, ValueError, KeyError):
                errors.append(f"Short {group_no} source scene duration is invalid"); continue
            if not SHORT_MIN <= d <= SHORT_MAX: errors.append(f"Short {group_no} source scenes {group} total {d:.1f}s outside 28-59 seconds")

    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    tags = data.get("tags", [])
    if not title or title.casefold() in {"untitled story", "untitled"}: errors.append("weak/missing title")
    if not 20 <= len(title) <= 100: errors.append("title must be 20-100 characters")
    if len(description) < 120: errors.append("description must be at least 120 characters")
    if not isinstance(tags, list) or len(tags) < 5: errors.append("at least 5 tags are required")
    if _words(data.get("narration", "")) < 200: errors.append("aggregate narration is too short")
    _validate_short_titles(data, errors)

    if errors: raise AssertionError("STORY VALIDATION FAILED: " + "; ".join(errors))
    return True


def validate_story(path=Path("work/story.json")):
    if not path.exists(): raise AssertionError(f"story file missing: {path}")
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise AssertionError(f"STORY VALIDATION FAILED: invalid story JSON: {exc}") from exc
    return validate_story_data(data)


if __name__ == "__main__": validate_story()
