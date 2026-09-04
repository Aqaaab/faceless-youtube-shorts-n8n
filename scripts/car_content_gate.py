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
MIN_VEHICLE_ANCHOR_SCENES = 8

CAR_TERMS = {
    "car", "cars", "automotive", "automobile", "vehicle", "vehicles", "engine", "engines", "powertrain",
    "transmission", "gearbox", "clutch", "turbo", "turbocharger", "supercharger", "intake", "exhaust",
    "piston", "cylinder", "valve", "injector", "fuel", "hybrid", "ev", "electric", "battery", "motor",
    "brake", "brakes", "braking", "tire", "tires", "tyre", "tyres", "wheel", "wheels", "suspension", "differential",
    "traction", "aerodynamics", "aerodynamic", "downforce", "chassis", "steering", "cooling", "radiator",
    "intercooler", "drivetrain", "awd", "rwd", "fwd", "rpm", "torque", "horsepower", "handling",
    "launch control", "traction control", "stability control", "regenerative braking", "regeneration", "spark plug",
    "oil", "coolant", "road", "racing", "performance",
}
BAD_NICHE_TERMS = {
    "boston tea party", "tea tax", "parliament", "colonial", "history documentary", "ancient", "medieval",
    "warship", "battlefield", "historical event", "politics", "president",
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


def _vehicle_tokens() -> list[str]:
    return [x for x in re.findall(r"[a-z0-9]+", _norm(os.getenv("CAR_VEHICLE", ""))) if len(x) >= 3]


def _scene_vehicle_blob(scene: dict[str, Any], visual_only: bool = False) -> str:
    keys = ("visual_subject", "pexels_query") if visual_only else ("text_en", "visual_subject", "pexels_query")
    return _norm(" ".join(str(scene.get(k, "")) for k in keys))


def _vehicle_anchor_count(story: dict[str, Any]) -> int:
    anchors = _vehicle_tokens()
    if not anchors:
        return EXPECTED_SCENES
    return sum(
        1 for scene in story.get("scenes", [])
        if isinstance(scene, dict) and any(re.search(rf"\b{re.escape(anchor)}\b", _scene_vehicle_blob(scene)) for anchor in anchors)
    )


def _vehicle_visual_anchor_count(story: dict[str, Any]) -> int:
    anchors = _vehicle_tokens()
    if not anchors:
        return EXPECTED_SCENES
    return sum(
        1 for scene in story.get("scenes", [])
        if isinstance(scene, dict) and any(re.search(rf"\b{re.escape(anchor)}\b", _scene_vehicle_blob(scene, True)) for anchor in anchors)
    )


def _harden_vehicle_identity(story: dict[str, Any]) -> dict[str, Any]:
    """Put the exact selected vehicle into visual fields without rewriting narration."""
    vehicle = str(os.getenv("CAR_VEHICLE", "")).strip()
    scenes = story.get("scenes")
    if not vehicle or not isinstance(scenes, list):
        return story
    matched = _vehicle_visual_anchor_count(story)
    if matched >= MIN_VEHICLE_ANCHOR_SCENES:
        return story

    subjects = [
        f"{vehicle} exterior automotive detail",
        f"{vehicle} engine and powertrain automotive detail",
        f"{vehicle} interior and driver controls automotive detail",
        f"{vehicle} brake and braking hardware automotive detail",
        f"{vehicle} chassis and suspension automotive detail",
        f"{vehicle} transmission and drivetrain automotive detail",
        f"{vehicle} road driving automotive exterior",
        f"{vehicle} performance automotive hardware",
    ]
    queries = [
        f"{vehicle} automotive exterior",
        f"{vehicle} automotive engine",
        f"{vehicle} automotive interior",
        f"{vehicle} automotive brake system",
        f"{vehicle} automotive chassis suspension",
        f"{vehicle} automotive transmission drivetrain",
        f"{vehicle} automotive road driving",
        f"{vehicle} automotive performance",
    ]
    for scene in scenes:
        if matched >= MIN_VEHICLE_ANCHOR_SCENES:
            break
        if not isinstance(scene, dict):
            continue
        if any(re.search(rf"\b{re.escape(anchor)}\b", _scene_vehicle_blob(scene, True)) for anchor in _vehicle_tokens()):
            continue
        slot = matched % len(subjects)
        scene["visual_subject"] = subjects[slot]
        scene["pexels_query"] = queries[slot]
        matched += 1
    print(f"CAR_IDENTITY_HARDENING=PASS matched_scenes={matched} required={MIN_VEHICLE_ANCHOR_SCENES}")
    return story


def _story_is_automotive(story: dict[str, Any]) -> bool:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        return False

    metadata = f"{_norm(story.get('title'))} {_norm(story.get('description'))} " + " ".join(_norm(x) for x in (story.get("tags") or []))
    if not _has_car_signal(metadata):
        return False

    for scene in scenes:
        if not isinstance(scene, dict):
            return False
        narration_visual = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject"))
        visual = " ".join(str(scene.get(k, "")) for k in ("visual_subject", "pexels_query"))
        if not _has_car_signal(narration_visual) or not _has_car_signal(visual):
            return False
        combined = _norm(f"{narration_visual} {scene.get('pexels_query', '')}")
        if any(term in combined for term in BAD_NICHE_TERMS):
            return False

    if _vehicle_tokens() and _vehicle_visual_anchor_count(story) < MIN_VEHICLE_ANCHOR_SCENES:
        return False
    return True


def _repair_story(story: dict[str, Any], topic: str) -> dict[str, Any]:
    payload = {
        "task": "automotive_content_gate_repair",
        "topic": topic,
        "featured_vehicle": os.getenv("CAR_VEHICLE", ""),
        "current_story": story,
        "hard_contract": {
            "niche": "cars and automotive technology only",
            "episode_scope": "one featured vehicle per episode; never switch the subject vehicle",
            "vehicle_identity": f"Keep the exact selected vehicle '{os.getenv('CAR_VEHICLE', '')}' visible in at least {MIN_VEHICLE_ANCHOR_SCENES} visual scenes.",
            "exact_scene_count": EXPECTED_SCENES,
            "every_scene": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "visuals": "Every scene must be directly depictable with Pexels automotive footage. Every pexels_query must contain a concrete automotive subject.",
            "story": "Treat the featured vehicle as a moving encyclopedia covering identity, exterior, cabin, engine or motor, airflow, power, drivetrain, cooling, brakes, chassis, modifications, strengths, weaknesses and verdict.",
            "forbidden": "No politics, war, colonial stories, tea, ships, generic history, unrelated mysteries, or non-automotive topics.",
            "accuracy": "Do not invent specific performance/spec numbers. Use qualitative explanations when exact figures are not source-backed.",
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
        "cars", "automotive", "car technology", "car engineering", "automotive engineering", "engine",
        "performance cars", "car facts", "car mechanics", "automotive technology", "cars explained",
        "car shorts", "automotive shorts", "car enthusiasts",
    ]
    tags: list[str] = []
    seen: set[str] = set()
    incoming = story.get("tags") if isinstance(story.get("tags"), list) else []
    for tag in base_tags + incoming:
        clean = re.sub(r"[^A-Za-z0-9 +&-]", "", str(tag or "")).strip()
        key = clean.casefold()
        if clean and key not in seen and _has_car_signal(clean):
            seen.add(key)
            tags.append(clean)
    story["tags"] = tags[:15]
    vehicle = str(os.getenv("CAR_VEHICLE", "")).strip()
    if vehicle:
        story["featured_vehicle"] = vehicle


def _strict_revalidate_story(path: Path) -> None:
    from strict_story_gate import _local_contract
    story = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(story, dict):
        raise RuntimeError("CAR_CONTENT_GATE: strict revalidation received invalid story JSON")
    _local_contract(story)


def main() -> dict[str, Any]:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    topic = os.getenv("VIDEO_TOPIC", "automotive engineering")
    if not isinstance(story, dict):
        raise RuntimeError("CAR_CONTENT_GATE_FAIL: long_story.json must contain an object")

    story = _harden_vehicle_identity(story)
    if not _story_is_automotive(story):
        last_error = "story is not automotive-only or vehicle identity is insufficient"
        for attempt in range(RETRIES):
            try:
                story = _repair_story(story, topic)
                story = _harden_vehicle_identity(story)
                if _story_is_automotive(story):
                    break
                last_error = f"repaired story failed automotive contract (visual_vehicle_anchor_scenes={_vehicle_visual_anchor_count(story)})"
            except Exception as exc:
                last_error = str(exc)
            print(f"CAR_CONTENT_GATE_RETRY={attempt + 1} error={last_error}")
        else:
            raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: {last_error}")

    _normalize_metadata(story, topic)
    story = _harden_vehicle_identity(story)
    if not _story_is_automotive(story):
        raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: final story rejected (visual_vehicle_anchor_scenes={_vehicle_visual_anchor_count(story)})")

    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _strict_revalidate_story(path)

    final_story = json.loads(path.read_text(encoding="utf-8"))
    final_story = _harden_vehicle_identity(final_story)
    if not _story_is_automotive(final_story):
        raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: strict revalidation passed but automotive identity failed (visual_vehicle_anchor_scenes={_vehicle_visual_anchor_count(final_story)})")
    path.write_text(json.dumps(final_story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (RUN / "metadata.json").write_text(
        json.dumps({
            "title": final_story["title"],
            "description": final_story["description"],
            "tags": final_story["tags"],
            "featured_vehicle": final_story.get("featured_vehicle", ""),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"CAR_CONTENT_GATE=PASS niche=cars scenes={len(final_story.get('scenes', []))} "
        f"featured_vehicle={final_story.get('featured_vehicle', '')} "
        f"vehicle_anchor_scenes={_vehicle_visual_anchor_count(final_story)} strict_revalidation=PASS"
    )
    return final_story


if __name__ == "__main__":
    main()
