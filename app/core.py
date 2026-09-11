from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .validator import validate_story_data

BASE = Path(os.getenv("ENGINE_ROOT", "."))
RUN = BASE / "work"

TRANSIENT_HTTP = {429, 502, 503, 504}
MAX_GATEWAY_ATTEMPTS = 4
MAX_STORY_REPAIRS = 2


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
    narration: str
    scenes: list[Scene]


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Odysseus returned invalid story JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Odysseus story response must be a JSON object")
    return value


def ask_odysseus(system: str, user: str) -> dict:
    base = os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/")
    key = os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    }
    last_error = None
    for attempt in range(1, MAX_GATEWAY_ATTEMPTS + 1):
        try:
            r = requests.post(
                f"{base}/api/v1/chat",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise RuntimeError(f"Odysseus network failure after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
            continue

        if r.status_code in TRANSIENT_HTTP:
            detail = r.text[:2000].replace("\n", " ")
            last_error = RuntimeError(f"HTTP {r.status_code}: {detail}")
            if attempt == MAX_GATEWAY_ATTEMPTS:
                raise RuntimeError(f"Odysseus chat failed after {attempt} attempts: {detail}") from last_error
            retry_after = r.headers.get("Retry-After", "")
            try:
                delay = max(1, min(float(retry_after), 30)) if retry_after else min(2 ** (attempt - 1), 8)
            except ValueError:
                delay = min(2 ** (attempt - 1), 8)
            time.sleep(delay)
            continue

        if not r.ok:
            detail = r.text[:2000].replace("\n", " ")
            raise RuntimeError(f"Odysseus chat failed HTTP {r.status_code}: {detail}")

        try:
            data = r.json()
        except ValueError as exc:
            raise RuntimeError("Odysseus returned invalid JSON envelope") from exc
        message = data.get("message") if isinstance(data, dict) else None
        choices = data.get("choices") if isinstance(data, dict) else None
        content = data.get("response") or data.get("content")
        if not content and isinstance(message, dict):
            content = message.get("content")
        if not content and isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice_message = choices[0].get("message")
            if isinstance(choice_message, dict):
                content = choice_message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Odysseus returned no model content")
        return _extract_json(content)

    raise RuntimeError(f"Odysseus request failed: {last_error}")


def _story_from_data(data: dict, topic: str) -> Story:
    scenes_data = data.get("scenes")
    if not isinstance(scenes_data, list):
        raise RuntimeError("Story response is missing a scenes list")
    scenes = []
    try:
        for s in scenes_data:
            scenes.append(
                Scene(
                    int(s["id"]),
                    str(s["narration"]).strip(),
                    str(s["visual_intent"]).strip(),
                    str(s.get("layout", "hero")).strip().lower(),
                    [str(x).strip() for x in list(s.get("callouts", []))],
                    float(s["duration"]),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Story response contains malformed scene data: {exc}") from exc
    narration = str(data.get("narration", "")).strip()
    if not narration:
        narration = " ".join(x.narration for x in scenes)
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return Story(
        topic=topic,
        title=str(data.get("title", "")).strip(),
        description=str(data.get("description", "")).strip(),
        tags=[str(x).strip() for x in tags],
        narration=narration,
        scenes=scenes,
    )


def _story_payload(story: Story) -> dict:
    return {
        "topic": story.topic,
        "title": story.title,
        "description": story.description,
        "tags": story.tags,
        "narration": story.narration,
        "scenes": [s.__dict__ for s in story.scenes],
    }


def _normalize_for_validation(data: dict) -> dict:
    normalized = dict(data)
    scenes = normalized.get("scenes")
    if isinstance(scenes, list) and not str(normalized.get("narration", "")).strip():
        normalized["narration"] = " ".join(
            str(s.get("narration", "")).strip() for s in scenes if isinstance(s, dict)
        ).strip()
    return normalized


def generate_story(topic: str) -> Story:
    system = '''You are the production Story Engine for a premium Arabic automotive infographic channel. Return JSON only. Create one coherent factual story for the requested car/topic with EXACTLY 25 scenes and no filler. Every scene has id, Arabic narration, visual_intent, layout, callouts and duration. Narration is 25-75 Arabic words and directly drives the visual. Keep scene duration normally 10-35 seconds; target spoken pacing around 1.8-3.0 Arabic words per second so TTS fits the planned duration with only small padding. Never use an ultra-short scene with dense narration. For the eight scenes used by Shorts (1,2,7,8,13,14,19,20), use 14-24 seconds and target roughly 28-60 narration words per scene so each pair naturally stays inside 28-59 seconds. Use only these layouts: hero, technical, spec, comparison, diagram, timeline. Use at least 4 layouts, at least 12 scenes with useful callouts, and at least 20 distinct visual intents. Total duration must be 420-900 seconds. Make visual_intent concrete: identify the vehicle system, camera/composition, infographic element, and on-screen information that should appear. Callouts must be directly supported by the scene narration and must not introduce facts, numbers, ratings, or specifications absent from that narration. For numeric callouts, copy the exact numeric form used in the narration, including Arabic-Indic versus Latin digits. Do not invent quantitative claims. Do not mention external media libraries or stock sources. The final visual language is a full-frame premium automotive editorial infographic, not an overlay placed on unrelated footage. Return strong title (20-100 chars), description (120+ chars), and 5+ useful tags.'''

    repair_system = '''You are a strict production JSON repair engine. Return JSON only. Repair the supplied automotive story so it passes every production contract without weakening factual integrity. Preserve the requested topic and useful content. EXACTLY 25 scenes with ids 1..25. Every scene must have 25-75 Arabic narration words, 5-60 seconds duration, a concrete visual_intent of at least 4 words, one allowed layout (hero, technical, spec, comparison, diagram, timeline), and no more than 5 callouts. At least 12 scenes must have callouts and at least 20 visual intents must be unique. Total duration 420-900 seconds. Shorts source pairs (1,2), (7,8), (13,14), (19,20) must each total 28-59 seconds. Every numeric token in a callout MUST appear in that same scene narration in the exact numeric form. Do not invent facts to satisfy validation; remove or rewrite unsupported callout claims instead. Title 20-100 characters, description at least 120 characters, at least 5 tags, aggregate narration at least 200 words. Return the complete corrected object, not a patch.'''

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
            data = ask_odysseus(
                repair_system,
                "Validation errors:\n" + last_error + "\n\nStory to repair:\n" + repair_payload,
            )
    raise RuntimeError(f"Story generation failed validation: {last_error}")


def save_story(story: Story, path: Path = RUN / "story.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_story_payload(story), ensure_ascii=False, indent=2), encoding="utf-8")
