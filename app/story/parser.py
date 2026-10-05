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


