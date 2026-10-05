from __future__ import annotations
import json
from pathlib import Path
from config.settings import RUN
from .models import Story
from .normalization import _normalize_for_validation
from .parser import _story_from_data

def _story_payload(story: Story) -> dict:
    return {"topic": story.topic, "title": story.title, "description": story.description, "tags": story.tags, "short_titles": story.short_titles, "narration": story.narration, "scenes": [s.__dict__ for s in story.scenes]}

def save_story(story: Story, path: Path = RUN / "story.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_story_payload(story), ensure_ascii=False, indent=2), encoding="utf-8")


def load_story(path: Path = RUN / "story.json") -> Story:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Saved story is not a JSON object")
    topic = str(data.get("topic", "")).strip()
    return _story_from_data(_normalize_for_validation(data), topic)

