from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .validator import validate_story_data

BASE = Path(os.getenv("ENGINE_ROOT", "."))
RUN = BASE / "work"
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
MAX_GATEWAY_ATTEMPTS = max(1, int(os.getenv("ODYSSEUS_MAX_ATTEMPTS", "5")))
MAX_STORY_REPAIRS = max(0, int(os.getenv("MAX_STORY_REPAIRS", "2")))
GATEWAY_TIMEOUT = max(15.0, float(os.getenv("ODYSSEUS_UPSTREAM_TIMEOUT", "180")))

@dataclass
class Scene:
    id: int
    narration: str
    visual_intent: str
    layout: str
    callouts: list[str]
    duration: float

@dataclass
class Story:
    topic: str
    title: str
    description: str
    tags: list[str]
    short_titles: list[str]
    narration: str
    scenes: list[Scene]


class OdysseusRateLimitError(RuntimeError):
    """Raised only after the configured gateway retries are exhausted on HTTP 429."""


def _balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        start = text.find("{", start + 1)
    return None


def _extract_json(text: str) -> dict:
    raw = str(text or "").strip().lstrip("\ufeff")
    candidates = [raw]
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.I | re.S)
    if match:
        candidates.insert(0, match.group(1).strip())
    balanced = _balanced_json_object(raw)
    if balanced:
        candidates.append(balanced)
    errors: list[str] = []
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(value, dict):
            return value
        errors.append(f"root type is {type(value).__name__}, expected object")
    detail = errors[-1] if errors else "empty response"
    raise RuntimeError(f"Odysseus returned invalid story JSON: {detail}")


def _content_from_envelope(data: Any) -> str:
    if not isinstance(data, dict):
        raise RuntimeError("Odysseus returned a non-object response envelope")
    candidates: list[Any] = [data.get("response"), data.get("content")]
    message = data.get("message")
    if isinstance(message, dict):
        candidates.extend([message.get("content"), message.get("text"), message.get("output_text")])
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        choice_message = first.get("message") if isinstance(first, dict) else None
        if isinstance(choice_message, dict):
            candidates.extend([choice_message.get("content"), choice_message.get("text"), choice_message.get("output_text")])
        candidates.extend([first.get("text"), first.get("output_text")] if isinstance(first, dict) else [])
    candidates.extend([data.get("output_text"), data.get("text")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "content", "value"):
                        if isinstance(item.get(key), str):
                            parts.append(item[key])
                            break
            joined = "".join(parts).strip()
            if joined:
                return joined
    raise RuntimeError("Odysseus returned no model content")


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "")
    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 60.0))
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def ask_odysseus(system: str, user: str) -> dict:
    base = os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/")
    key = os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    url = f"{base}/api/v1/chat"
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_GATEWAY_ATTEMPTS + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=GATEWAY_TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise RuntimeError(f"Odysseus network failure after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
            continue
        if response.status_code == 429:
            detail = response.text[:1000].replace("\n", " ")
            last_error = OdysseusRateLimitError(f"HTTP 429: {detail}")
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise OdysseusRateLimitError(
                    f"Odysseus rate limit exhausted after {attempt} attempts: {detail}"
                ) from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if response.status_code in TRANSIENT_HTTP:
            detail = response.text[:1000].replace("\n", " ")
            last_error = RuntimeError(f"HTTP {response.status_code}: {detail}")
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise RuntimeError(f"Odysseus chat failed after {attempt} attempts: {detail}") from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if not response.ok:
            detail = response.text[:1500].replace("\n", " ")
            raise RuntimeError(f"Odysseus chat failed HTTP {response.status_code}: {detail}")
        try:
            envelope = response.json()
            content = _content_from_envelope(envelope)
            return _extract_json(content)
        except (ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise RuntimeError(f"Odysseus response contract failed after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Odysseus request failed: {last_error}")


def _story_shape(data: dict) -> dict:
    """Normalize harmless LLM wrapper/field-shape drift without inventing story data."""
    if not isinstance(data, dict):
        raise RuntimeError("Story response root must be an object")
    current = dict(data)
    for key in ("story", "data", "result", "output"):
        nested = current.get(key)
        if isinstance(nested, dict) and ("scenes" in nested or "scene" in nested or "chapters" in nested):
            merged = dict(nested)
            for field in ("topic", "title", "description", "tags", "short_titles", "narration"):
                if field not in merged and field in current:
                    merged[field] = current[field]
            current = merged
            break
    scenes = current.get("scenes")
    if scenes is None:
        for key in ("scene", "chapters", "segments"):
            if key in current:
                scenes = current[key]
                break
    if isinstance(scenes, dict):
        numeric = []
        for key, value in scenes.items():
            if isinstance(value, dict) and str(key).isdigit() and "id" not in value:
                item = dict(value)
                item["id"] = int(key)
                numeric.append(item)
        if numeric:
            scenes = numeric
    if isinstance(scenes, list):
        normalized_scenes = []
        for index, item in enumerate(scenes, 1):
            if not isinstance(item, dict):
                normalized_scenes.append(item)
                continue
            scene = dict(item)
            aliases = {
                "voiceover": "narration",
                "voice_over": "narration",
                "visual": "visual_intent",
                "visual_prompt": "visual_intent",
                "camera": "visual_intent",
                "seconds": "duration",
                "duration_seconds": "duration",
                "annotations": "callouts",
            }
            for source, target in aliases.items():
                if target not in scene and source in scene:
                    scene[target] = scene[source]
            if "id" not in scene:
                scene["id"] = index
            if "callouts" not in scene or scene["callouts"] is None:
                scene["callouts"] = []
            normalized_scenes.append(scene)
        current["scenes"] = normalized_scenes
    return current


def _story_from_data(data: dict, topic: str) -> Story:
    data = _story_shape(data)
    scenes_data = data.get("scenes")
    if not isinstance(scenes_data, list):
        raise RuntimeError("Story response is missing a scenes list")
    scenes: list[Scene] = []
    try:
        for item in scenes_data:
            if not isinstance(item, dict):
                raise TypeError("scene must be an object")
            scenes.append(Scene(
                int(item["id"]),
                str(item["narration"]).strip(),
                str(item["visual_intent"]).strip(),
                str(item.get("layout", "hero")).strip().lower(),
                [str(x).strip() for x in item.get("callouts", [])] if isinstance(item.get("callouts", []), list) else [],
                float(item["duration"]),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Story response contains malformed scene data: {exc}") from exc
    narration = str(data.get("narration", "")).strip() or " ".join(s.narration for s in scenes)
    tags = data.get("tags", []) if isinstance(data.get("tags", []), list) else []
    short_titles = data.get("short_titles", []) if isinstance(data.get("short_titles", []), list) else []
    return Story(
        topic=topic,
        title=str(data.get("title", "")).strip(),
        description=str(data.get("description", "")).strip(),
        tags=[str(x).strip() for x in tags],
        short_titles=[str(x).strip() for x in short_titles],
        narration=narration,
        scenes=scenes,
    )


def _story_payload(story: Story) -> dict:
    return {
        "topic": story.topic,
        "title": story.title,
        "description": story.description,
        "tags": story.tags,
        "short_titles": story.short_titles,
        "narration": story.narration,
        "scenes": [s.__dict__ for s in story.scenes],
    }


def _normalize_for_validation(data: dict) -> dict:
    normalized = _story_shape(data)
    scenes = normalized.get("scenes")
    if isinstance(scenes, list) and not str(normalized.get("narration", "")).strip():
        normalized["narration"] = " ".join(str(s.get("narration", "")).strip() for s in scenes if isinstance(s, dict)).strip()
    return normalized


def generate_story(topic: str) -> Story:
    system = '''You are the production Story Engine for a premium Arabic automotive YouTube channel. Output JSON only, with no markdown, commentary, or code fences. Build one factual, coherent story for the requested car/topic.
EXACTLY 25 scenes, ids 1..25. Each scene: id, Arabic narration, visual_intent, layout, callouts, duration. Return exactly four unique standalone Arabic short_titles for source pairs (1,2), (7,8), (13,14), (19,20). Keep short titles 20-80 chars, specific, hook-driven, not numbered labels.
Narration per scene: 25-75 Arabic words; target 30-50 for ordinary scenes. Shorts source scenes should be 28-50 narration words and naturally yield a 28-59 second pair without artificial silence. Durations are estimates only; real TTS duration becomes authoritative later.
Use layouts only: hero, technical, spec, comparison, diagram, timeline. Use at least 4 layouts, at least 12 callout scenes, and at least 20 distinct visual intents. Visual intent must state subject/system + composition/camera + graphic element + displayed information. Callouts must be directly grounded in the same narration; never invent facts, numbers, ratings, or specifications. Numeric callouts must use exactly the same digit script/form as the narration.
Do not mention stock-media libraries or create internal/debug presentation copy intended only for the pipeline. The final visual language is full-frame premium automotive editorial, with the vehicle as the primary subject, not a dashboard.
Return title 20-100 chars, description at least 120 chars, and at least 5 useful tags.'''
    repair_system = '''Return JSON only. Repair the supplied production story deterministically. The JSON root MUST contain a top-level "scenes" array; never place it under story/data/result/output and never use singular scene/chapters/segments. Do not invent facts. Preserve useful factual content. EXACTLY 25 scenes, ids 1..25; exactly four specific Arabic short titles for pairs (1,2), (7,8), (13,14), (19,20); 25-75 Arabic words per scene; valid layout; 20+ unique visual intents; 12+ callout scenes; total provisional duration 420-900 seconds; each Short pair 28-59 seconds. Every numeric callout must use the exact same numeric digit form found in its scene narration. Remove unsupported callouts rather than fabricating facts. Title 20-100 chars, description >=120, >=5 tags. Output the complete object only.'''
    data = ask_odysseus(system, f"Create the production story for: {topic}")
    last_error = None
    for repair_index in range(MAX_STORY_REPAIRS + 1):
        try:
            candidate = _normalize_for_validation(data)
            validate_story_data(candidate)
            return _story_from_data(candidate, topic)
        except (AssertionError, RuntimeError, TypeError, ValueError) as exc:
            last_error = str(exc)
            if repair_index >= MAX_STORY_REPAIRS:
                raise RuntimeError(f"Story generation failed validation after repairs: {last_error}") from exc
            repair_payload = json.dumps(_normalize_for_validation(data), ensure_ascii=False, indent=2)
            data = ask_odysseus(repair_system, f"Validation errors:\n{last_error}\n\nStory to repair:\n{repair_payload}")
    raise RuntimeError(f"Story generation failed validation: {last_error}")


def save_story(story: Story, path: Path = RUN / "story.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_story_payload(story), ensure_ascii=False, indent=2), encoding="utf-8")
