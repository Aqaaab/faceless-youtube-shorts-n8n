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
MAX_STORY_REPAIRS = max(0, int(os.getenv("MAX_STORY_REPAIRS", "2")))
GATEWAY_TIMEOUT = max(15.0, float(os.getenv("ODYSSEUS_UPSTREAM_TIMEOUT", "180")))
REPAIR_TIMEOUT = max(30.0, min(GATEWAY_TIMEOUT, float(os.getenv("ODYSSEUS_REPAIR_TIMEOUT", "120"))))


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
    """Raised after configured gateway retries are exhausted on HTTP 429."""


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


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "")
    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 60.0))
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def ask_odysseus(system: str, user: str, *, timeout: float | None = None, max_attempts: int | None = None) -> dict:
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
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    attempts = max(1, int(max_attempts) if max_attempts is not None else int(os.getenv("ODYSSEUS_MAX_ATTEMPTS", "5")))
    request_timeout = max(15.0, float(timeout if timeout is not None else os.getenv("ODYSSEUS_REQUEST_TIMEOUT", GATEWAY_TIMEOUT)))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(f"Odysseus network failure after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
            continue
        if response.status_code == 429:
            detail = response.text[:1000].replace("\n", " ")
            last_error = OdysseusRateLimitError(f"HTTP 429: {detail}")
            if attempt == attempts:
                raise OdysseusRateLimitError(f"Odysseus rate limit exhausted after {attempts} attempts: {detail}") from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if response.status_code in TRANSIENT_HTTP:
            detail = response.text[:1000].replace("\n", " ")
            last_error = RuntimeError(f"HTTP {response.status_code}: {detail}")
            if attempt == attempts:
                raise RuntimeError(f"Odysseus chat failed after {attempts} attempts: {detail}") from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if not response.ok:
            detail = response.text[:1500].replace("\n", " ")
            raise RuntimeError(f"Odysseus chat failed HTTP {response.status_code}: {detail}")
        try:
            return _extract_json(_content_from_envelope(response.json()))
        except (ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(f"Odysseus response contract failed after {attempts} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Odysseus request failed: {last_error}")


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


def _story_payload(story: Story) -> dict:
    return {"topic": story.topic, "title": story.title, "description": story.description, "tags": story.tags, "short_titles": story.short_titles, "narration": story.narration, "scenes": [s.__dict__ for s in story.scenes]}


def _normalize_for_validation(data: dict) -> dict:
    normalized = _story_shape(data)
    scenes = normalized.get("scenes")
    if isinstance(scenes, list) and not str(normalized.get("narration", "")).strip():
        normalized["narration"] = " ".join(str(s.get("narration", "")).strip() for s in scenes if isinstance(s, dict)).strip()
    return normalized


def _callout_is_grounded(callout: str, narration: str) -> bool:
    numeric = re.findall(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*", callout)
    narration_numbers = set(re.findall(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*", narration))
    if any(token not in narration_numbers for token in numeric):
        return False
    words = {x for x in re.sub(r"[^\w\u0600-\u06ff]+", " ", callout.casefold()).split() if len(x) >= 3 and not x.isdigit()}
    nwords = {x for x in re.sub(r"[^\w\u0600-\u06ff]+", " ", narration.casefold()).split() if len(x) >= 3 and not x.isdigit()}
    return not words or bool(words & nwords)


def _short_title(seed: str, index: int) -> str:
    text = re.sub(r"\s+", " ", seed).strip(" ،.")
    if len(text) > 66:
        text = text[:66].rstrip()
    suffix = f" — المقطع {index}"
    return (text + suffix)[:80].strip()


def _ensure_description(data: dict, topic: str) -> None:
    description = re.sub(r"\s+", " ", str(data.get("description", "")).strip())
    if len(description) < 120:
        base = description or f"تحليل عربي منظم لموضوع {topic} ضمن حلقة سيارات مترابطة."
        description = (base + " يركز على التصميم والتقنية والأداء وتجربة الاستخدام ضمن سرد واضح ومشاهد متتابعة، مع الالتزام بالمعلومات المتاحة وعدم اختلاق مواصفات غير مؤكدة.")
    data["description"] = description[:2000]


def _deterministic_structure_repair(data: dict) -> dict:
    """Repair only mechanical constraints; factual claims remain the model's responsibility."""
    out = _normalize_for_validation(data)
    scenes = out.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        return out
    for scene in scenes:
        if isinstance(scene, dict):
            scene["duration"] = 18.0
            raw = scene.get("callouts", [])
            if isinstance(raw, list):
                scene["callouts"] = [str(c).strip() for c in raw if isinstance(c, str) and str(c).strip() and _callout_is_grounded(str(c), str(scene.get("narration", "")))]
    _ensure_description(out, str(out.get("topic", "")))
    titles = out.get("short_titles")
    valid_titles = isinstance(titles, list) and len(titles) == 4 and len({str(x).strip() for x in titles}) == 4 and all(20 <= len(str(x).strip()) <= 80 for x in titles)
    if not valid_titles:
        groups = ((1, 2), (7, 8), (13, 14), (19, 20))
        by_id = {int(s.get("id")): s for s in scenes if isinstance(s, dict) and str(s.get("id", "")).isdigit()}
        out["short_titles"] = [_short_title(str(by_id.get(first, {}).get("narration", "موضوع السيارة")), index) for index, (first, _) in enumerate(groups, 1)]
    return out


def generate_story(topic: str) -> Story:
    system = '''You are the production Story Engine for a premium Arabic automotive YouTube channel. Output JSON only. EXACTLY 25 scenes, ids 1..25. Each scene must contain id, Arabic narration, visual_intent, layout, callouts, duration. Generate 30-45 Arabic words per scene. Set every provisional duration to 18 seconds. Return exactly four unique Arabic short_titles for source pairs (1,2), (7,8), (13,14), (19,20), each 20-80 characters. Use layouts only hero, technical, spec, comparison, diagram, timeline; at least 4 layouts; at least 12 callout scenes; at least 20 distinct visual intents. Callouts must be directly grounded in the same narration and numeric callouts must copy the exact digit form used there. Do not invent unsupported specifications. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Visual language is full-frame premium automotive editorial with the vehicle as the primary subject; never output dashboard/debug copy or stock-footage references.'''
    repair_system = '''Return JSON only. Repair the supplied Arabic automotive story. The JSON root MUST contain a top-level scenes array. EXACTLY 25 scenes, ids 1..25. Every scene must have 30-45 Arabic narration words, visual_intent >=4 words, valid layout, grounded callouts, and duration 18.0. Return exactly four unique Arabic short_titles of 20-80 characters. Ensure >=4 layouts, >=12 callout scenes, >=20 distinct visual intents, total duration 450 seconds, and source pairs (1,2),(7,8),(13,14),(19,20) each 36 seconds. Preserve factual claims; do not invent facts. Remove unsupported callouts. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Return the complete object only.'''
    data = ask_odysseus(system, f"Create the production story for this topic: {topic}")
    last_error = None
    for repair_index in range(MAX_STORY_REPAIRS + 1):
        candidate = _deterministic_structure_repair(data)
        try:
            validate_story_data(candidate)
            return _story_from_data(candidate, topic)
        except (AssertionError, RuntimeError, TypeError, ValueError) as exc:
            last_error = str(exc)
            if repair_index >= MAX_STORY_REPAIRS:
                raise RuntimeError(f"Story generation failed validation after repairs: {last_error}") from exc
            compact = [{"id": s.get("id"), "narration": str(s.get("narration", "")), "visual_intent": str(s.get("visual_intent", "")), "layout": s.get("layout"), "callouts": s.get("callouts", [])} for s in candidate.get("scenes", []) if isinstance(s, dict)]
            repair_payload = json.dumps({"title": candidate.get("title"), "description": candidate.get("description"), "tags": candidate.get("tags", []), "short_titles": candidate.get("short_titles", []), "scenes": compact}, ensure_ascii=False, separators=(",", ":"))
            data = ask_odysseus(repair_system, f"Validation failures:\n{last_error}\n\nCompact story payload:\n{repair_payload}", timeout=REPAIR_TIMEOUT, max_attempts=2)
    raise RuntimeError(f"Story generation failed validation: {last_error}")


def save_story(story: Story, path: Path = RUN / "story.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_story_payload(story), ensure_ascii=False, indent=2), encoding="utf-8")
