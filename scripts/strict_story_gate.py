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
_HOOK_WORDS = {"shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange", "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never"}


def _normalize_digits(text: str) -> str:
    return (text or "").translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")


def _digits(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", _normalize_digits(text))


def _is_hook(scene: dict) -> bool:
    text = str(scene.get("text_en", "")).strip().lower()
    beat = str(scene.get("beat", "")).strip().lower()
    words = re.findall(r"[a-z][a-z'-]*", text)
    has_hook_signal = any(word in _HOOK_WORDS for word in words) or "?" in text or "!" in text
    has_open_loop = any(token in text for token in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    return beat == "hook" and len(words) >= 18 and (has_hook_signal or has_open_loop)


def _local_contract(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("STRICT_STORY_GATE: story must contain exactly 25 scenes")
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} is not an object")
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        visual = str(scene.get("visual_subject", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        if not en or not ar or not visual or not query or not str(scene.get("beat", "")).strip():
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} has missing content")
        if _digits(en) != _digits(ar):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} changed numeric facts between English and Arabic")
        if len(re.findall(r"[\u0600-\u06ff]", ar)) < 12:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Arabic is too short")
        if not 3 <= len(query.split()) <= 9:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Pexels query is not concrete enough")
    for index in (1, 7, 13, 19):
        if not _is_hook(scenes[index - 1]):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a genuine hook")


def _review(story: dict) -> dict:
    rules = [
        "Return exactly 25 scenes with complete metadata.",
        "Scenes 1, 7, 13 and 19 must be genuine hooks: introduce a specific mystery, contradiction, danger, surprising fact, unanswered question, or open loop; never a generic introduction.",
        "Each hook must be at least 18 English words and contain a hook signal or open-loop construction.",
        "Preserve every number, named entity, chronology, causal relationship, and factual scope.",
        "Arabic must faithfully preserve the English meaning in fluent Modern Standard Arabic.",
        "Every visual_subject and pexels_query must describe concrete visible footage.",
        "Return complete JSON only, without markdown or commentary.",
    ]
    current = story
    last: Exception | None = None
    for attempt in range(RETRIES):
        feedback = f"Previous failure: {last}" if last else ""
        payload = {"task": "strict_pre_render_story_audit_and_repair", "rules": rules, "validation_feedback": feedback, "story": current}
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=240))
            if not isinstance(result, dict):
                raise RuntimeError("strict audit returned non-object JSON")
            _local_contract(result)
            return result
        except Exception as exc:
            last = exc
            if isinstance(locals().get("result"), dict):
                current = result
    raise RuntimeError("STRICT_STORY_GATE failed after deterministic and semantic validation") from last


def main() -> dict:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    _local_contract(story)
    repaired = _review(story)
    repaired.setdefault("provider", story.get("provider", "Odysseus"))
    _local_contract(repaired)
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "metadata.json").write_text(json.dumps({"title": repaired.get("title", ""), "description": repaired.get("description", ""), "tags": repaired.get("tags", [])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS semantic=audited hooks=validated visuals=concrete arabic=faithful")
    return repaired


if __name__ == "__main__":
    main()
