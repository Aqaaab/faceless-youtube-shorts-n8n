from __future__ import annotations
import json, os, re
from dataclasses import dataclass
from pathlib import Path
import requests

BASE = Path(os.getenv("ENGINE_ROOT", "."))
RUN = BASE / "work"

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
    return json.loads(text)


def ask_odysseus(system: str, user: str) -> dict:
    base = os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/")
    key = os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    r = requests.post(
        f"{base}/api/v1/chat",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    content = data.get("content") or data.get("message", {}).get("content") or data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("Odysseus returned no model content")
    return _extract_json(content)


def generate_story(topic: str) -> Story:
    system = '''You are the Story Engine for a premium automotive infographic channel. Return JSON only. Build one coherent Arabic long-form story for the requested car/topic. Exactly 25 scenes. Every scene must have narration, visual_intent, layout, callouts and duration. Narration must be factual and retention-focused. Visuals must directly represent the spoken sentence. Use a consistent automotive editorial infographic identity: hero vehicle, clean technical diagrams, labels, specs, comparison cards, controlled motion, no stock footage. Total duration 420-900 seconds.'''
    data = ask_odysseus(system, f"Create the production story for: {topic}")
    scenes = [Scene(int(s["id"]), s["narration"], s["visual_intent"], s.get("layout", "hero"), s.get("callouts", []), float(s["duration"])) for s in data["scenes"]]
    return Story(topic, data["title"], data["description"], data.get("tags", []), data.get("narration", " ".join(x.narration for x in scenes)), scenes)


def save_story(story: Story, path: Path = RUN / "story.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"topic": story.topic, "title": story.title, "description": story.description, "tags": story.tags, "narration": story.narration, "scenes": [s.__dict__ for s in story.scenes]}, ensure_ascii=False, indent=2), encoding="utf-8")
