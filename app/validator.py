from __future__ import annotations

import json
import re
from pathlib import Path

MIN_LONG, MAX_LONG = 420.0, 900.0
MIN_SCENE, MAX_SCENE = 5.0, 60.0
MIN_WORDS, MAX_WORDS = 25, 75
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_MIN, SHORT_MAX = 28.0, 59.0
ALLOWED_LAYOUTS = {"hero", "technical", "spec", "comparison", "diagram", "timeline"}
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
DIGIT_RE = re.compile(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*")


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(str(text)))


def _numeric_tokens(text: str) -> list[str]:
    return DIGIT_RE.findall(str(text))


def _lexical_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\u0600-\u06ff]+", " ", str(text).casefold())
    return {x for x in cleaned.split() if len(x) >= 3 and not x.isdigit()}


def _validate_callouts(callouts, narration: str, sid: int) -> list[str]:
    errors: list[str] = []
    narration_text = str(narration)
    narration_lower = narration_text.casefold()
    narration_numbers = set(_numeric_tokens(narration_text))
    narration_words = _lexical_tokens(narration_text)
    for callout in callouts:
        if not isinstance(callout, str) or not callout.strip():
            errors.append(f"scene {sid} callouts must contain non-empty strings")
            continue
        value = callout.strip()
        for token in _numeric_tokens(value):
            if token not in narration_numbers:
                errors.append(f"scene {sid} callout introduces unsupported numeric token: {token}")
        callout_words = _lexical_tokens(value)
        if callout_words and narration_words and not (callout_words & narration_words):
            errors.append(f"scene {sid} callout has no lexical support in narration: {value}")
        if value.casefold() not in narration_lower and not _numeric_tokens(value):
            # Non-numeric callouts may be a compact label, but at least one meaningful token must be grounded.
            if callout_words and not (callout_words & narration_words):
                errors.append(f"scene {sid} callout is not grounded in narration: {value}")
    return errors


def _validate_short_titles(data: dict, errors: list[str]) -> None:
    titles = data.get("short_titles")
    if not isinstance(titles, list) or len(titles) != 4:
        errors.append("exactly 4 short_titles are required")
        return
    normalized: list[str] = []
    for index, title in enumerate(titles, 1):
        value = str(title).strip()
        folded = value.casefold()
        normalized.append(folded)
        if not 20 <= len(value) <= 80:
            errors.append(f"short title {index} must be 20-80 characters")
        if not _has_arabic(value):
            errors.append(f"short title {index} must contain Arabic text")
        if folded in {"short 1", "short 2", "short 3", "short 4", "untitled", "untitled story"}:
            errors.append(f"short title {index} is generic")
    if len(set(normalized)) != 4:
        errors.append("Short titles must be unique")


def validate_story_data(data: dict) -> bool:
    if not isinstance(data, dict):
        raise AssertionError("STORY VALIDATION FAILED: root payload must be an object")
    errors: list[str] = []
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise AssertionError("STORY VALIDATION FAILED: scenes must be a list")
    if len(scenes) != 25:
        errors.append(f"scene count must be exactly 25, got {len(scenes)}")
    ids = [s.get("id") if isinstance(s, dict) else None for s in scenes]
    if ids != list(range(1, 26)):
        errors.append(f"scene ids must be exactly 1..25, got {ids}")

    durations: list[float] = []
    layouts: set[str] = set()
    intents: set[str] = set()
    callout_scenes = 0
    aggregate_narration: list[str] = []

    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            errors.append(f"scene {index} must be an object")
            continue
        sid = scene.get("id", index)
        try:
            duration = float(scene.get("duration", 0))
        except (TypeError, ValueError):
            duration = 0.0
            errors.append(f"scene {sid} duration is not numeric")
        durations.append(duration)
        if not MIN_SCENE <= duration <= MAX_SCENE:
            errors.append(f"scene {sid} duration {duration:.2f}s outside {MIN_SCENE:g}-{MAX_SCENE:g}s")

        narration = str(scene.get("narration", "")).strip()
        intent = str(scene.get("visual_intent", "")).strip()
        layout = str(scene.get("layout", "")).strip().lower()
        aggregate_narration.append(narration)
        words = _words(narration)
        if words < MIN_WORDS or words > MAX_WORDS:
            errors.append(f"scene {sid} narration must be {MIN_WORDS}-{MAX_WORDS} words (got {words})")
        if not _has_arabic(narration):
            errors.append(f"scene {sid} narration must contain Arabic")
        if _words(intent) < 4:
            errors.append(f"scene {sid} visual_intent is too short")
        if layout not in ALLOWED_LAYOUTS:
            errors.append(f"scene {sid} unsupported layout '{layout}'")
        layouts.add(layout)
        intents.add(intent.casefold())

        callouts = scene.get("callouts", [])
        if not isinstance(callouts, list):
            errors.append(f"scene {sid} callouts must be a list")
        else:
            if len(callouts) > 5:
                errors.append(f"scene {sid} has more than 5 callouts")
            if callouts:
                callout_scenes += 1
                errors.extend(_validate_callouts(callouts, narration, int(sid) if str(sid).isdigit() else index))

    total = sum(durations)
    if not MIN_LONG <= total <= MAX_LONG:
        errors.append(f"planned duration {total:.2f}s outside {MIN_LONG:g}-{MAX_LONG:g}")
    if len(layouts) < 4:
        errors.append(f"layout diversity too low: {len(layouts)}/4")
    if callout_scenes < 12:
        errors.append(f"callout coverage too low: {callout_scenes}/25")
    if len(intents) < 20:
        errors.append(f"visual intent diversity too low: {len(intents)}/20")

    by_id = {int(s["id"]): s for s in scenes if isinstance(s, dict) and str(s.get("id", "")).isdigit()}
    for number, group in enumerate(SHORT_GROUPS, 1):
        if all(scene_id in by_id for scene_id in group):
            try:
                pair_duration = sum(float(by_id[scene_id]["duration"]) for scene_id in group)
            except (TypeError, ValueError, KeyError):
                errors.append(f"Short {number} source duration is invalid")
            else:
                if not SHORT_MIN <= pair_duration <= SHORT_MAX:
                    errors.append(f"Short {number} source scenes {group} total {pair_duration:.2f}s outside {SHORT_MIN:g}-{SHORT_MAX:g}s")

    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    tags = data.get("tags")
    if not title or title.casefold() in {"untitled", "untitled story"}:
        errors.append("weak or missing title")
    elif not 20 <= len(title) <= 100:
        errors.append("title must be 20-100 characters")
    if len(description) < 120:
        errors.append("description must be at least 120 characters")
    if not isinstance(tags, list) or len([x for x in tags if str(x).strip()]) < 5:
        errors.append("at least 5 non-empty tags are required")
    aggregate = str(data.get("narration", "")).strip() or " ".join(aggregate_narration).strip()
    if _words(aggregate) < 200:
        errors.append("aggregate narration is too short")
    _validate_short_titles(data, errors)

    if errors:
        raise AssertionError("STORY VALIDATION FAILED: " + "; ".join(errors))
    return True


def validate_story(path: Path = Path("work/story.json")) -> bool:
    if not path.exists():
        raise AssertionError(f"story file missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(f"STORY VALIDATION FAILED: invalid story JSON: {exc}") from exc
    return validate_story_data(data)


if __name__ == "__main__":
    validate_story()
