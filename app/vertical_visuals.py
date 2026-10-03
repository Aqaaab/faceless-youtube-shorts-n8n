from __future__ import annotations

from pathlib import Path

from .core import RUN, Story
from .wangp import generate_vertical_visuals as _generate_vertical
from .story_visuals import _kind


def generate_vertical_visuals(story: Story, out_dir: Path=RUN/"vertical_scenes", scene_ids:list[int] | None=None):
    ids=scene_ids or [s.id for s in story.scenes]
    out_dir.mkdir(parents=True,exist_ok=True)
    _generate_vertical(story,out_dir,ids)


SEMANTIC_MODES={"performance","design","interior","technology","efficiency","safety","price","charging","hero"}
