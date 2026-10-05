from __future__ import annotations
import json
import re
from typing import Any
from .models import Scene, Story

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
        if isinstance(first, dict):
            candidates.extend([first.get("text"), first.get("output_text"), first.get("reasoning_content"), first.get("reasoning")])
    candidates.extend([data.get("output_text"), data.get("text"), data.get("reasoning_content"), data.get("reasoning")])
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




def _story_shape(data: dict) -> dict:
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
        aliases = {"voiceover": "narration", "voice_over": "narration", "visual": "visual_intent", "visual_prompt": "visual_intent", "camera": "visual_intent", "seconds": "duration", "duration_seconds": "duration", "annotations": "callouts"}
        for index, item in enumerate(scenes, 1):
            if not isinstance(item, dict):
                normalized_scenes.append(item)
                continue
            scene = dict(item)
            for source, target in aliases.items():
                if target not in scene and source in scene:
                    scene[target] = scene[source]
            scene.setdefault("id", index)
            if scene.get("callouts") is None:
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
            scenes.append(Scene(int(item["id"]), str(item["narration"]).strip(), str(item["visual_intent"]).strip(), str(item.get("layout", "hero")).strip().lower(), [str(x).strip() for x in item.get("callouts", [])] if isinstance(item.get("callouts", []), list) else [], float(item["duration"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Story response contains malformed scene data: {exc}") from exc
    narration = str(data.get("narration", "")).strip() or " ".join(s.narration for s in scenes)
    tags = data.get("tags", []) if isinstance(data.get("tags", []), list) else []
    short_titles = data.get("short_titles", []) if isinstance(data.get("short_titles", []), list) else []
    return Story(topic=topic, title=str(data.get("title", "")).strip(), description=str(data.get("description", "")).strip(), tags=[str(x).strip() for x in tags], short_titles=[str(x).strip() for x in short_titles], narration=narration, scenes=scenes)


