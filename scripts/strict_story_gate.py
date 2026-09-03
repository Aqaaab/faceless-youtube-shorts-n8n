from __future__ import annotations

import json
import os
import re
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("STRICT_STORY_RETRIES", "3")))

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _normalize_digits(text: str) -> str:
    return (text or "").translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")


def _digits(text: str) -> list[str]:
    normalized = _normalize_digits(text)
    return re.findall(r"\d+(?:[.,]\d+)?", normalized)


def _local_contract(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("STRICT_STORY_GATE: story must contain exactly 25 scenes")
    for i, scene in enumerate(scenes, 1):
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        visual = str(scene.get("visual_subject", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        if not en or not ar or not visual or not query:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} has missing content")
        if _digits(en) != _digits(ar):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} changed numeric facts between English and Arabic")
        arabic = len(re.findall(r"[\u0600-\u06ff]", ar))
        if arabic < 12:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Arabic is too short")
        if not 3 <= len(query.split()) <= 9:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Pexels query is not concrete enough")
    for index in (1, 7, 13, 19):
        if str(scenes[index - 1].get("beat", "")).lower() != "hook":
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a hook")


def _review(story: dict) -> dict:
    rules = [
        "Compare every scene's final English narration against its Arabic subtitle. Arabic must faithfully preserve the exact meaning, entities, numbers, tense, scope, and causal relationships; rewrite Arabic when needed.",
        "Compare every scene's narration against visual_subject and pexels_query. The query must describe concrete footage that can visibly represent the narration, not merely the broad topic.",
        "Do not invent facts, people, dates, locations, objects, or actions while repairing.",
        "Preserve chronological story order and all factual scope.",
        "Return exactly 25 scenes. Never return 24, 26, or a partial story.",
        "Scenes 1, 7, 13 and 19 must remain independent hooks.",
        "Use fluent Modern Standard Arabic. No ordinary English words embedded in Arabic subtitles.",
        "Preserve all numbers and named entities; never broaden a claim from one person/event to a group.",
        "Return the complete repaired story JSON only. No markdown and no commentary.",
    ]
    current = story
    last: Exception | None = None
    for attempt in range(RETRIES):
        feedback = ""
        if attempt:
            feedback = (
                "The previous repair failed local validation. Do not repeat the failure. "
                f"Previous validation error: {last}. Return a COMPLETE object with exactly 25 scenes."
            )
        payload = {
            "task": "strict_pre_render_story_audit_and_repair",
            "purpose": "Prevent a rendered video whose narration, Arabic subtitles, or visual query describe different facts.",
            "rules": rules,
            "validation_feedback": feedback,
            "story": current,
        }
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=240))
            if not isinstance(result, dict):
                raise RuntimeError("strict audit returned non-object JSON")
            _local_contract(result)
            return result
        except Exception as exc:
            last = exc
            current = result if "result" in locals() and isinstance(result, dict) else current
            if attempt + 1 < RETRIES:
                continue
    raise RuntimeError("STRICT_STORY_GATE failed to obtain a semantically valid 25-scene audit/repair") from last


def main() -> dict:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    _local_contract(story)
    repaired = _review(story)
    if repaired.get("provider") is None:
        repaired["provider"] = story.get("provider", "Odysseus")
    _local_contract(repaired)
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = {"title": repaired.get("title", ""), "description": repaired.get("description", ""), "tags": repaired.get("tags", [])}
    (RUN / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS semantic=audited repaired=normalized visual_queries=concrete arabic=faithful")
    return repaired


if __name__ == "__main__":
    main()
