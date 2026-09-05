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


def _has_vehicle_signal(*values: object) -> bool:
    anchors = _vehicle_tokens()
    if not anchors:
        return False
    text = _norm(" ".join(str(v or "") for v in values))
    return any(re.search(rf"\b{re.escape(anchor)}\b", text) for anchor in anchors)


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


def _automotive_visual_templates(vehicle: str) -> list[tuple[str, str]]:
    return [
        (f"{vehicle} exterior front three quarter automotive", f"{vehicle} exterior front three quarter"),
        (f"{vehicle} exterior rear three quarter automotive", f"{vehicle} exterior rear three quarter"),
        (f"{vehicle} front fascia headlights automotive detail", f"{vehicle} front fascia headlights"),
        (f"{vehicle} rear wing taillights automotive detail", f"{vehicle} rear wing taillights"),
        (f"{vehicle} side profile wheel design automotive", f"{vehicle} side profile wheels"),
        (f"{vehicle} engine bay automotive engineering detail", f"{vehicle} engine bay engineering"),
        (f"{vehicle} engine intake exhaust automotive detail", f"{vehicle} intake exhaust"),
        (f"{vehicle} turbocharger cooling automotive detail", f"{vehicle} turbocharger cooling"),
        (f"{vehicle} brake rotor caliper automotive detail", f"{vehicle} brake rotor caliper"),
        (f"{vehicle} front suspension chassis automotive detail", f"{vehicle} front suspension chassis"),
        (f"{vehicle} rear suspension differential automotive detail", f"{vehicle} rear suspension differential"),
        (f"{vehicle} drivetrain transmission automotive detail", f"{vehicle} drivetrain transmission"),
        (f"{vehicle} steering wheel cockpit automotive interior", f"{vehicle} steering wheel cockpit"),
        (f"{vehicle} dashboard controls automotive interior", f"{vehicle} dashboard controls"),
        (f"{vehicle} seats cabin automotive interior", f"{vehicle} seats cabin"),
        (f"{vehicle} cooling radiator airflow automotive detail", f"{vehicle} radiator airflow"),
        (f"{vehicle} tire wheel corner automotive detail", f"{vehicle} tire wheel corner"),
        (f"{vehicle} road driving automotive exterior", f"{vehicle} road driving"),
        (f"{vehicle} performance driving automotive road", f"{vehicle} performance driving"),
        (f"{vehicle} cornering handling automotive driving", f"{vehicle} cornering handling"),
        (f"{vehicle} aerodynamic spoiler airflow automotive", f"{vehicle} spoiler airflow"),
        (f"{vehicle} underbody chassis automotive engineering", f"{vehicle} underbody chassis"),
        (f"{vehicle} brake cooling automotive engineering", f"{vehicle} brake cooling"),
        (f"{vehicle} engine performance automotive engineering", f"{vehicle} engine performance"),
        (f"{vehicle} full car automotive engineering overview", f"{vehicle} automotive overview"),
    ]


def _harden_vehicle_identity(story: dict[str, Any]) -> dict[str, Any]:
    """Keep narration intact while making visual identity deterministic and concrete for the selected vehicle."""
    vehicle = str(os.getenv("CAR_VEHICLE", "")).strip()
    scenes = story.get("scenes")
    if not vehicle or not isinstance(scenes, list):
        return story

    templates = _automotive_visual_templates(vehicle)
    changed = 0
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        visual_text = _scene_vehicle_blob(scene, True)
        # A vehicle-specific visual identity is sufficient; generic automotive wording is optional.
        if _has_vehicle_signal(visual_text):
            continue
        subject, query = templates[index % len(templates)]
        scene["visual_subject"] = subject
        scene["pexels_query"] = query
        changed += 1

    matched = _vehicle_visual_anchor_count(story)
    print(
        f"CAR_IDENTITY_HARDENING=PASS matched_scenes={matched} required={MIN_VEHICLE_ANCHOR_SCENES} "
        f"visuals_replaced={changed} total_scenes={len(scenes)}"
    )
    return story


def _automotive_failure_reason(story: dict[str, Any]) -> str | None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        return f"scene_count={len(scenes) if isinstance(scenes, list) else 'invalid'} required={EXPECTED_SCENES}"

    metadata = f"{_norm(story.get('title'))} {_norm(story.get('description'))} " + " ".join(_norm(x) for x in (story.get("tags") or []))
    if not _has_car_signal(metadata) and not _has_vehicle_signal(metadata):
        return "metadata has no automotive or featured-vehicle signal"

    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            return f"scene {index} is not an object"
        narration_visual = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject"))
        visual = " ".join(str(scene.get(k, "")) for k in ("visual_subject", "pexels_query"))
        if not (_has_car_signal(narration_visual) or _has_vehicle_signal(narration_visual)):
            return f"scene {index} has no automotive or featured-vehicle signal in narration/subject"
        if not (_has_car_signal(visual) or _has_vehicle_signal(visual)):
            return f"scene {index} has no automotive or featured-vehicle signal in visuals"
        combined = _norm(f"{narration_visual} {scene.get('pexels_query', '')}")
        if any(term in combined for term in BAD_NICHE_TERMS):
            return f"scene {index} contains forbidden non-automotive niche term"

    visual_anchors = _vehicle_visual_anchor_count(story)
    if _vehicle_tokens() and visual_anchors < MIN_VEHICLE_ANCHOR_SCENES:
        return f"visual_vehicle_anchor_scenes={visual_anchors} required={MIN_VEHICLE_ANCHOR_SCENES}"
    return None


def _story_is_automotive(story: dict[str, Any]) -> bool:
    return _automotive_failure_reason(story) is None


def _repair_story(story: dict[str, Any], topic: str) -> dict[str, Any]:
    payload = {
        "task": "automotive_content_gate_repair",
        "topic": topic,
        "featured_vehicle": os.getenv("CAR_VEHICLE", ""),
        "current_story": story,
        "hard_contract": {
            "niche": "cars and automotive technology only",
            "episode_scope": "one featured vehicle per episode; never switch the subject vehicle",
            "vehicle_identity": f"Keep the exact selected vehicle '{os.getenv('CAR_VEHICLE', '')}' available across the episode visuals. At least {MIN_VEHICLE_ANCHOR_SCENES} visual scenes must explicitly identify it, and all visual fields should stay about that vehicle.",
            "exact_scene_count": EXPECTED_SCENES,
            "every_scene": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
            "visuals": "Every scene must be directly depictable with Pexels automotive footage. Every pexels_query must contain a concrete automotive subject and must not be abstract.",
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
    if not _has_car_signal(title) and not _has_vehicle_signal(title):
        clean_topic = re.sub(r"^AUTOMOTIVE NICHE ONLY\.\s*", "", topic, flags=re.I).strip()
        story["title"] = f"Automotive Breakdown: {clean_topic[:80]}".strip()
    description = str(story.get("description", "")).strip()
    if not (_has_car_signal(description) or _has_vehicle_signal(description)):
        story["description"] = f"Automotive deep dive: {story['title']}. {description}".strip()
    else:
        story["description"] = description

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
        if clean and key not in seen and (_has_car_signal(clean) or _has_vehicle_signal(clean)):
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
    reason = _automotive_failure_reason(story)
    if reason is not None:
        last_error = reason
        for attempt in range(RETRIES):
            try:
                story = _repair_story(story, topic)
                story = _harden_vehicle_identity(story)
                reason = _automotive_failure_reason(story)
                if reason is None:
                    break
                last_error = reason
            except Exception as exc:
                last_error = str(exc)
            print(f"CAR_CONTENT_GATE_RETRY={attempt + 1} error={last_error}")
        else:
            raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: {last_error}")

    _normalize_metadata(story, topic)
    story = _harden_vehicle_identity(story)
    reason = _automotive_failure_reason(story)
    if reason is not None:
        raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: final story rejected ({reason})")

    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _strict_revalidate_story(path)

    final_story = json.loads(path.read_text(encoding="utf-8"))
    final_story = _harden_vehicle_identity(final_story)
    reason = _automotive_failure_reason(final_story)
    if reason is not None:
        raise RuntimeError(f"CAR_CONTENT_GATE_FAIL: strict revalidation passed but automotive contract failed ({reason})")
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
