from __future__ import annotations
import os
from .gateway import GATEWAY_TIMEOUT, ask_odysseus
from .normalization import _deterministic_structure_repair
from .parser import _story_from_data
from .repair import _invalid_scene_ids, _repair_invalid_scenes_incrementally
from .models import Story
from app.validator import validate_story_data

def generate_story(topic: str) -> Story:
    system = '''You are the production Story Engine for a premium Arabic automotive YouTube channel. Output JSON only. EXACTLY 25 scenes, ids 1..25. Each scene must contain id, Arabic narration, visual_intent, layout, callouts, duration. Generate 30-45 Arabic words per scene. Set every provisional duration to 18 seconds. Return exactly four unique Arabic short_titles, 20-80 characters each; they are provisional titles and must not assume fixed scene pairs because a later selector chooses Shorts from a candidate pool. Use layouts only hero, technical, spec, comparison, diagram, timeline; at least 4 layouts; at least 12 callout scenes; at least 20 distinct visual intents. Callouts must be directly grounded in the same narration and numeric callouts must copy the exact digit form used there. Do not invent unsupported specifications. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Visual language is full-frame premium automotive editorial with the vehicle as the primary subject; never output dashboard/debug copy or stock-footage references.'''
    data = ask_odysseus(system, f"Create the production story for this topic: {topic}")
    max_repairs = max(0, int(os.getenv("MAX_STORY_REPAIRS", "2")))
    last_error = None
    for repair_index in range(max_repairs + 1):
        candidate = _deterministic_structure_repair(data)
        try:
            validate_story_data(candidate)
            return _story_from_data(candidate, topic)
        except (AssertionError, RuntimeError, TypeError, ValueError) as exc:
            last_error = str(exc)
            if repair_index >= max_repairs:
                raise RuntimeError(f"Story generation failed validation after repairs: {last_error}") from exc
            invalid = _invalid_scene_ids(candidate)
            if invalid:
                data = _repair_invalid_scenes_incrementally(candidate, topic)
            else:
                repair_system = '''Return JSON only. Repair the supplied Arabic automotive story. The JSON root MUST contain a top-level scenes array. EXACTLY 25 scenes, ids 1..25. Every scene must have 30-45 Arabic narration words, visual_intent >=4 words, valid layout, grounded callouts, and duration 18.0. Return exactly four unique Arabic short_titles of 20-80 characters. Ensure >=4 layouts, >=12 callout scenes, >=20 distinct visual intents, total duration 450 seconds, and candidate Shorts are selected later from a larger candidate pool. Preserve factual claims; do not invent facts. Remove unsupported callouts. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Return the complete object only.'''
                compact = [{"id": s.get("id"), "narration": str(s.get("narration", "")), "visual_intent": str(s.get("visual_intent", "")), "layout": s.get("layout"), "callouts": s.get("callouts", [])} for s in candidate.get("scenes", []) if isinstance(s, dict)]
                payload = json.dumps({"title": candidate.get("title"), "description": candidate.get("description"), "tags": candidate.get("tags", []), "short_titles": candidate.get("short_titles", []), "scenes": compact}, ensure_ascii=False, separators=(",", ":"))
                data = ask_odysseus(repair_system, f"Validation failures:\n{last_error}\n\nCompact story payload:\n{payload}", timeout=min(60.0, GATEWAY_TIMEOUT), max_attempts=3)
    raise RuntimeError(f"Story generation failed validation: {last_error}")


