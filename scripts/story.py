from __future__ import annotations
import json
from pathlib import Path
from .odysseus import chat, extract_text

SLOT_COUNT = 5

def build_story(topic: str, output: Path) -> dict:
    slots = []
    for i in range(1, SLOT_COUNT + 1):
        prompt = f"Create slot {i}/5 for a faceless YouTube documentary about: {topic}. Return JSON with title, narration, scenes. No markdown."
        data = chat(prompt)
        slots.append({"slot": i, "text": extract_text(data)})
    result = {"topic": topic, "slots": slots}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
