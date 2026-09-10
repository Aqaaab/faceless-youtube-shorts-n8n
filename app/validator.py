from __future__ import annotations
import json, re
from pathlib import Path

MIN_LONG, MAX_LONG = 420.0, 900.0
MIN_SCENE, MAX_SCENE = 5.0, 60.0
MIN_WORDS, MAX_WORDS = 25, 75
ALLOWED_LAYOUTS = {"hero", "technical", "spec", "comparison", "diagram", "timeline"}
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_MIN, SHORT_MAX = 28.0, 59.0


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def validate_story(path=Path("work/story.json")):
    if not path.exists():
        raise AssertionError(f"story file missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    scenes = data.get("scenes", [])
    if len(scenes) != 25:
        errors.append(f"scene count must be exactly 25, got {len(scenes)}")
    ids = [s.get("id") for s in scenes]
    if ids != list(range(1, 26)):
        errors.append(f"scene ids must be exactly 1..25, got {ids}")
    try:
        total = sum(float(s.get("duration", 0)) for s in scenes)
    except (TypeError, ValueError):
        total = 0.0
        errors.append("one or more scene durations are not numeric")
    if not MIN_LONG <= total <= MAX_LONG:
        errors.append(f"planned duration {total:.1f}s outside 420-900")

    layouts, intents = [], []
    callout_scenes = 0
    for s in scenes:
        sid = s.get("id")
        for key in ("id", "narration", "visual_intent", "layout", "duration"):
            if s.get(key) in (None, "", []):
                errors.append(f"scene {sid} missing {key}")
        try:
            duration = float(s.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
            errors.append(f"scene {sid} duration is not numeric")
        if not MIN_SCENE <= duration <= MAX_SCENE:
            errors.append(f"scene {sid} duration {duration:.1f}s outside 5-60")
        narration = str(s.get("narration", "")).strip()
        intent = str(s.get("visual_intent", "")).strip()
        layout = str(s.get("layout", "")).strip().lower()
        words = _words(narration)
        if words < MIN_WORDS or words > MAX_WORDS:
            errors.append(f"scene {sid} narration must be 25-75 words (got {words})")
        if not re.search(r"[\u0600-\u06ff]", narration):
            errors.append(f"scene {sid} narration must contain Arabic text")
        if _words(intent) < 4:
            errors.append(f"scene {sid} visual intent too short")
        if layout not in ALLOWED_LAYOUTS:
            errors.append(f"scene {sid} unsupported layout '{layout}'")
        callouts = s.get("callouts", [])
        if not isinstance(callouts, list):
            errors.append(f"scene {sid} callouts must be a list")
        else:
            if len(callouts) > 5:
                errors.append(f"scene {sid} has more than 5 callouts")
            if callouts:
                callout_scenes += 1
        layouts.append(layout)
        intents.append(intent.casefold())

    if len(set(layouts)) < 4:
        errors.append(f"visual layout diversity too low: {len(set(layouts))}/4")
    if callout_scenes < 12:
        errors.append(f"technical visual coverage too low: {callout_scenes}/25 scenes have callouts")
    if len(set(intents)) < 20:
        errors.append(f"visual intents too repetitive: {len(set(intents))}/20 unique")

    by_id = {int(s.get("id")): s for s in scenes if str(s.get("id", "")).isdigit()}
    for group_no, group in enumerate(SHORT_GROUPS, 1):
        if all(i in by_id for i in group):
            try:
                d = sum(float(by_id[i]["duration"]) for i in group)
            except (TypeError, ValueError, KeyError):
                errors.append(f"Short {group_no} source scene duration is invalid")
                continue
            if not SHORT_MIN <= d <= SHORT_MAX:
                errors.append(f"Short {group_no} source scenes {group} total {d:.1f}s outside 28-59s")

    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    tags = data.get("tags", [])
    if not title or title.casefold() in {"untitled story", "untitled"}:
        errors.append("weak/missing title")
    if not 20 <= len(title) <= 100:
        errors.append("title must be 20-100 characters")
    if len(description) < 120:
        errors.append("description must be at least 120 characters")
    if not isinstance(tags, list) or len(tags) < 5:
        errors.append("at least 5 tags are required")
    if _words(data.get("narration", "")) < 200:
        errors.append("aggregate narration is too short")
    if errors:
        raise AssertionError("STORY VALIDATION FAILED: " + "; ".join(errors))
    return True


if __name__ == "__main__":
    validate_story()
