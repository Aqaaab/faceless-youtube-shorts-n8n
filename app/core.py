"""Compatibility facade for the Story Engine API.

The implementation is split under app.story; existing imports from app.core remain stable.
"""
import os
import requests
import time

from config.settings import BASE, RUN
from .story.gateway import GATEWAY_TIMEOUT, OdysseusRateLimitError, ask_odysseus
from .story.models import Scene, Story
from .story.normalization import _callout_is_grounded, _ensure_description, _normalize_for_validation
from .story.parser import _extract_json, _story_from_data, _story_shape
from .story.repository import _story_payload, load_story, save_story
from .story.repair import _deterministic_structure_repair, _invalid_scene_ids, _repair_invalid_scenes_incrementally as _repair_invalid_scenes_incrementally_impl, _repair_scene_batch
from .story.service import generate_story

__all__ = [
    "BASE", "RUN", "Scene", "Story", "OdysseusRateLimitError", "ask_odysseus",
    "generate_story", "save_story", "load_story", "GATEWAY_TIMEOUT",
]


def _repair_invalid_scenes_incrementally(data: dict, topic: str) -> dict:
    return _repair_invalid_scenes_incrementally_impl(data, topic, ask_fn=ask_odysseus)
