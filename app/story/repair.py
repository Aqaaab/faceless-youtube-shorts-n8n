from __future__ import annotations
import json
import os
from .gateway import ask_odysseus
from .normalization import _callout_is_grounded, _normalize_for_validation, _ensure_description
from .parser import _story_shape

def _deterministic_structure_repair(data: dict) -> dict:
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
        # Titles are only provisional story metadata. The real four Shorts are
        # selected later from the candidate pool; never encode source scene pairs here.
        anchors = [scenes[min(len(scenes) - 1, round((len(scenes) - 1) * i / 3))] for i in range(4)]
        out["short_titles"] = [_short_title(str(item.get("narration", "موضوع السيارة")), index) for index, item in enumerate(anchors, 1)]
    return out


def _invalid_scene_ids(data: dict) -> list[int]:
    scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(scenes, list):
        return []
    invalid: list[int] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("id")
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            continue
        narration = str(scene.get("narration", "")).strip()
        words = len(narration.split())
        visual = str(scene.get("visual_intent", "")).strip()
        if not (25 <= words <= 75 and len(visual.split()) >= 4):
            invalid.append(sid)
    return invalid


def _repair_scene_batch(data: dict, scene_ids: list[int], topic: str) -> dict:
    scenes = data.get("scenes", [])
    by_id = {int(s.get("id")): s for s in scenes if isinstance(s, dict) and str(s.get("id", "")).isdigit()}
    payload = [{"id": sid, "narration": str(by_id[sid].get("narration", "")), "visual_intent": str(by_id[sid].get("visual_intent", "")), "layout": by_id[sid].get("layout", "hero"), "callouts": by_id[sid].get("callouts", [])} for sid in scene_ids if sid in by_id]
    system = """Return JSON only with a top-level scenes array. Repair ONLY the supplied scene IDs for an Arabic automotive YouTube story. Each returned scene must keep its id and factual claims, and must contain 30-45 natural Arabic words of narration, at least 4 visual-intent words, a valid layout, and only callouts grounded in that same narration. Do not invent specifications or numbers. Do not return any other scene."""
    serialized_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    repair_timeout = min(60.0, max(30.0, float(os.getenv("ODYSSEUS_SCENE_REPAIR_TIMEOUT", "60"))))
    repaired = ask_odysseus(system, f"Topic: {topic}\nScenes to repair:\n{serialized_payload}", timeout=repair_timeout, max_attempts=3)
    repaired_scenes = _story_shape(repaired).get("scenes", [])
    if not isinstance(repaired_scenes, list):
        raise RuntimeError("Scene repair returned no scenes array")
    for item in repaired_scenes:
        if not isinstance(item, dict):
            continue
        try:
            sid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if sid in by_id:
            original = by_id[sid]
            original.update({k: item[k] for k in ("narration", "visual_intent", "layout", "callouts") if k in item})
            original["duration"] = 18.0
    return data


def _repair_invalid_scenes_incrementally(data: dict, topic: str) -> dict:
    invalid = _invalid_scene_ids(data)
    for start in range(0, len(invalid), 5):
        _repair_scene_batch(data, invalid[start:start + 5], topic)
    return data


