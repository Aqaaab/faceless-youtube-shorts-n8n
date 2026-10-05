from __future__ import annotations
from dataclasses import dataclass

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

