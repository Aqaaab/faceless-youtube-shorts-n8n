from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
EXPECTED_SCENES = 25
RETRIES = max(1, int(os.getenv("CAR_GATE_RETRIES", "2")))

CAR_TERMS = {
    "car", "cars", "automotive", "automobile", "vehicle", "vehicles", "engine", "engines",
    "powertrain", "transmission", "gearbox", "clutch", "turbo", "turbocharger", "supercharger",
    "intake", "exhaust", "piston", "cylinder", "valve", "injector", "fuel", "hybrid", "ev",
    "electric", "battery", "motor", "brake", "brakes", "tire", "tires", "tyre", "tyres",
    "wheel", "wheels", "suspension", "differential", "traction", "aerodynamics", "aerodynamic",
    "downforce", "chassis", "steering", "cooling", "radiator", "intercooler", "drivetrain",
    "awd", "rwd", "fwd", "rpm", "torque", "horsepower", "handling", "launch control", "traction control",
    "stability control", "regenerative braking", "regeneration", "spark plug", "oil", "coolant",
}
BAD_NICHE_TERMS = {
    "boston tea party", "tea tax", "parliament", "revolution", "colonial", "history documentary",
    "ancient", "medieval", "warship", "battlefield", "historical event", "politics", "president",
}


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _has_car_signal(*values: object) -> bool:
    text = _norm(" ".join(str(v or "") for v in values))
    for term in CAR_TERMS:
        if len(term) <= 3 and " " not in term:
            if re.search(rf"\b{re.escape(term)}\b", text):
                return True
        elif term in text:
            return True
    return False


def _story_is_automotive(story: dict[str, Any]) -> bool:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        return False
    metadata_text = f"{_norm(story.get('title'))} {_norm(story.get('description'))} " + " ".join(_norm(x) for x in (story.get("tags") or []))
    if not _has_car_signal(metadata_text):
        return False
    for scene in scenes:
        if not isinstance(scene, dict):
            return False
        scene_text = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject"))
        visual_text = " ".join(str(scene.get(k, "")) for k in ("visual_subject", "pexels_query"))
        if not _has_car_signal(scene_text) or not _has_car_signal(visual_text):
            return False
        combined = _norm(f"{scene_text} {scene.get('pexels_query', '')}")
        if any(term in combined for term in BAD_NICHE_TERMS):
            return False
    return True


def _repair_story(story: dict[str, Any], topic: str) -> dict[str, Any]:
    payload = {
        "task": "automotive_content_gate_repair",
        "topic": topic,
        "current_story": story,
        "hard_contract": {
            "niche": "cars and automotive technology only",
            "exact_scene_count": EXPECTED_SCENES,
            "language": "English narration with faithful Modern Standard Arabic translation",
            "every_scene": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "visuals": "Every one of the 25 scenes must be directly depictable with Pexels automotive footage or close-ups of a car, engine, component, wheel, brake, tire, road-driving, workshop, or automotive technology. Every pexels_query must contain a concrete automotive subject.",
            "story": "Explain a real automotive topic with a strong hook, clear technical progression, concrete examples, and a useful verdict.",
            "forbidden": "No politics, war, colonial stories, tea, ships, generic history, unrelated mysteries, or non-automotive topics.",
            "accuracy": "Do not invent specific performance/spec numbers. When exact numbers are not certain, explain the mechanism qualitatively.",
            "scene_length": "40-75 English words per scene, target 45-70.",
        },
        "return": "JSON only with title, description, tags and exactly 25 scenes.",
    }
    result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=180))
    if not isinstance(result, dict):
        raise RuntimeError("CAR_CONTENT_GATE: repair returned invalid JSON")
    return result


def _normalize_metadata(story: dict[str, Any], topic: str) -> None:
    title = str(story.get("title", "")).strip()
    if not _has_car_signal(title):
        clean_topic = re.sub(r"^AUTOMOTIVE NICHE ONLY\.\s*", "", topic, flags=re.I).strip()
        story["title"] = f"Automotive Breakdown: {clean_topic[:80]}".strip()
    description = str(story.get("description", "")).strip()
    story["description"] = description if _has_car_signal(description) else f"Automotive deep dive: {story['title']}. {description}".strip()
    base_tags = [
        "cars", "automotive", "car technology", "car engineering", "automotive engineering",
        "engine", "performance cars", "car facts", "car mechanics", "automotive technology",
        "cars explained", "car shorts", "automotive shorts", "car enthusiasts",
    ]
    tags: list[str] = []
    seen: set[str] = set()
    for tag in base_tags + (story.get("tags") if isinstance(story.get("tags"), list) else []):
        clean = re.sub(r"[^A-Za-z0-9 +&-]", "", str(tag or "")).strip()
        key = clean.casefold()
        if clean and key not in seen and _has_car_signal(clean):
            seen.add(key)
            tags.append(clean)
    story["tags"] = tags[:15]


def main() -> dict[str, Any]:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    topic = os.getenv("VIDEO_TOPIC", "automotive engineering")
    if not _story_is_automotive(story):
        last_error = "story is not automotive-only"
        for _ in range(RETRIES):
            try:
                story = _repair_story(story if isinstance(story, dict) else {}, topic)
            except Exception as exc:
                last_error = str(exc)
                continue
            if _story_is_automotive(story):
                break
            last_error = "repaired story still failed automotive contract"
        else:
            raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: {last_error}")
    _normalize_metadata(story, topic)
    if not _story_is_automotive(story):
        raise RuntimeError("CAR_CONTENT_GATE_FAIL: final story is not automotive-only")
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "metadata.json").write_text(
        json.dumps({"title": story["title"], "description": story["description"], "tags": story["tags"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("CAR_CONTENT_GATE=PASS niche=cars scenes=25 visual_queries=automotive")
    return story


if __name__ == "__main__":
    main()
