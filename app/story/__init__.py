"""Decomposed Story Engine implementation; app.core remains the compatibility facade."""

from .gateway import GATEWAY_TIMEOUT, OdysseusRateLimitError, ask_odysseus
from .models import Scene, Story
from .normalization import _callout_is_grounded, _ensure_description, _normalize_for_validation
from .parser import _extract_json, _story_from_data, _story_shape
from .repair import _deterministic_structure_repair, _invalid_scene_ids, _repair_invalid_scenes_incrementally, _repair_scene_batch
from .repository import _story_payload, load_story, save_story
from .service import generate_story
