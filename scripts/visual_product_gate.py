from __future__ import annotations

import json
import os
import re
from pathlib import Path

from visual_engineering import visual_profile, validate_visual_engineering

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
VEHICLE = str(os.getenv("CAR_VEHICLE", "")).strip().casefold()
INTERNAL = re.compile(r"FLOW\s+MODE|FACT_SOURCE_REQUIRED|GENERAL_EXPLANATION|MODIFIED_ESTIMATE|HUD_ONLY|COMPONENT_ID|LAYER_ID|VISUAL\s+(?:xray|cutaway|flow|hud)|X-RAY SECTION", re.I)
GENERIC_QUERY = re.compile(r"\b(?:generic|stock car|car footage|automotive footage|car video|automobile footage)\b", re.I)
COMPONENT_WORDS = {
    "engine": {"engine", "motor", "powertrain"}, "turbocharger": {"turbo", "turbocharger"}, "intercooler": {"intercooler"},
    "cooling system": {"cooling", "radiator", "coolant"}, "fuel delivery": {"fuel", "injector"}, "fuel injector": {"injector", "fuel"},
    "ev battery": {"battery", "ev"}, "electric powertrain": {"electric", "powertrain", "inverter"}, "electric motor": {"electric", "motor"},
    "hybrid system": {"hybrid", "powertrain"}, "transmission": {"transmission", "gearbox"}, "gearbox": {"gearbox", "transmission"},
    "differential": {"differential", "axle"}, "braking system": {"brake", "braking", "caliper", "rotor"},
    "tire contact patch": {"tire", "wheel", "contact"}, "suspension": {"suspension", "damper", "spring"},
    "aerodynamics": {"aerodynamic", "aero", "airflow"}, "downforce": {"downforce", "aero", "airflow"},
}


def _load(name: str):
    path = RUN / name
    if not path.is_file():
        raise RuntimeError(f"VISUAL_PRODUCT_GATE: missing {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _vehicle_tokens() -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", VEHICLE) if len(x) >= 3}


def _validate_scene(index: int, scene: dict) -> None:
    profile = visual_profile(scene)
    validate_visual_engineering({**scene, "visual_engineering": profile})
    if not str(scene.get("visual_subject", "")).strip() or not str(scene.get("pexels_query", "")).strip():
        raise RuntimeError(f"scene {index}: missing visual subject/query")
    query = str(scene["pexels_query"]).casefold()
    if GENERIC_QUERY.search(query):
        raise RuntimeError(f"scene {index}: generic Pexels query forbidden")
    component = str(scene.get("technical_component", "")).casefold()
    required = COMPONENT_WORDS.get(component, set())
    if required and not any(token in query for token in required):
        raise RuntimeError(f"scene {index}: Pexels query does not describe technical component '{component}'")
    tokens = _vehicle_tokens()
    if tokens and not any(re.search(rf"\b{re.escape(token)}\b", query) for token in tokens):
        raise RuntimeError(f"scene {index}: Pexels query lacks featured vehicle identity")


def _validate_sources(story: dict) -> None:
    sources = story.get("sources")
    if not isinstance(sources, list) or len(sources) < 3:
        raise RuntimeError("source register must contain at least 3 distinct trusted sources")
    ids = {str(s.get("id", "")).strip() for s in sources if isinstance(s, dict)}
    if "" in ids or len(ids) != len(sources):
        raise RuntimeError("source register contains missing/duplicate IDs")
    by_id = {str(s["id"]): s for s in sources}
    for index, scene in enumerate(story.get("scenes", []), 1):
        source_id = str(scene.get("source_id", "")).strip()
        claim = str(scene.get("source_claim", "")).strip()
        if source_id not in by_id or not claim:
            raise RuntimeError(f"scene {index}: claim-level provenance is incomplete")
        source = by_id[source_id]
        if index not in source.get("scene_numbers", []):
            raise RuntimeError(f"scene {index}: source_id is not mapped to the scene")
        if str(source.get("claim", "")).strip() == "General automotive mechanism; exact vehicle-specific specifications require a mapped trusted source.":
            raise RuntimeError(f"scene {index}: generic fallback evidence is not publishable")
        claim_tokens = {x for x in re.findall(r"[a-z0-9]{4,}", claim.casefold())}
        scene_tokens = {x for x in re.findall(r"[a-z0-9]{4,}", str(scene.get("text_en", "")).casefold())}
        if claim_tokens and scene_tokens and not (claim_tokens & scene_tokens):
            raise RuntimeError(f"scene {index}: evidence claim has no lexical overlap with narration")


def _validate_render_manifest() -> None:
    manifest = _load("render_manifest.json")
    engineering = manifest.get("technical_overlay", {})
    required = {
        "internal_metadata_rendered": False,
        "generic_profiles_allowed": False,
        "full_frame": True,
        "cutaway_geometry": True,
        "animated_flow_paths": True,
        "arabic_ui": True,
        "verified_spec_cards": True,
        "upgrade_panel": True,
    }
    for key, expected in required.items():
        if engineering.get(key) is not expected:
            raise RuntimeError(f"render manifest technical overlay contract failed: {key}={engineering.get(key)!r}")
    if engineering.get("type") != "full_frame_automotive_infographic":
        raise RuntimeError("render manifest does not identify the full-frame infographic renderer")
    profiles = engineering.get("scene_profiles", [])
    if len(profiles) != 25:
        raise RuntimeError("render manifest must contain 25 visual profiles")
    for index, profile in enumerate(profiles, 1):
        if not profile.get("allowed") or profile.get("component_id") == "generic":
            raise RuntimeError(f"render manifest contains forbidden visual profile at scene {index}")


def _validate_visual_manifest() -> None:
    manifest = _load("visual_manifest.json")
    if manifest.get("provider_order") != ["generated", "pexels"]:
        raise RuntimeError("visual manifest does not use generated-first media order")
    if manifest.get("motion") != "Ken Burns/parallax for stills; native motion for video fallback":
        raise RuntimeError("visual manifest does not declare motion treatment")
    scenes = manifest.get("scenes", [])
    if len(scenes) != 25:
        raise RuntimeError("visual manifest must contain 25 scene records")
    allowed = {"generated", "pexels"}
    motions = {"ken_burns", "live_clip"}
    for index, record in enumerate(scenes, 1):
        if record.get("scene") != index or record.get("provider") not in allowed or record.get("motion") not in motions:
            raise RuntimeError(f"scene {index}: invalid visual provider/motion record")
        if record["provider"] == "generated" and record["motion"] != "ken_burns":
            raise RuntimeError(f"scene {index}: generated still lacks camera motion")


def _validate_svgs(story: dict) -> None:
    root = RUN / "technical_overlay" / "master"
    svgs = sorted(root.glob("scene-*.svg"))
    if len(svgs) != 25:
        raise RuntimeError("technical overlay must contain 25 master SVG scenes")
    scenes = story.get("scenes", [])
    for index, svg in enumerate(svgs, 1):
        text = svg.read_text(encoding="utf-8")
        if INTERNAL.search(text):
            raise RuntimeError(f"internal metadata leaked into rendered SVG: {svg.name}")
        if '<svg' not in text or 'width="1920"' not in text or 'height="1080"' not in text:
            raise RuntimeError(f"{svg.name}: master infographic is not 1920x1080 full-frame")
        if 'class="flow-label"' not in text:
            raise RuntimeError(f"{svg.name}: infographic lacks required flow UI")
        if "معلومات السيارة" not in text and "مواصفات موثقة" not in text:
            raise RuntimeError(f"{svg.name}: infographic lacks Arabic specification UI")
        scene = scenes[index - 1] if index - 1 < len(scenes) else {}
        upgrade_note = str(scene.get("upgrade_note") or scene.get("upgrade_requirements") or "").strip()
        if upgrade_note and "UPGRADES" not in text:
            raise RuntimeError(f"{svg.name}: scene declares upgrade data but upgrade UI is missing")
        if not upgrade_note and "UPGRADES" in text:
            raise RuntimeError(f"{svg.name}: upgrade UI rendered without scene upgrade data")


def main() -> None:
    story = _load("long_story.json")
    scenes = story.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("visual product gate requires exactly 25 scenes")
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"scene {index} is not an object")
        _validate_scene(index, scene)
    _validate_sources(story)
    _validate_render_manifest()
    _validate_visual_manifest()
    _validate_svgs(story)
    print("VISUAL_PRODUCT_GATE=PASS")
    print("FULL_FRAME_INFOGRAPHIC=PASS")
    print("CUTAWAY_GEOMETRY=PASS")
    print("ANIMATED_FLOW_PATHS=PASS")
    print("ARABIC_UI=PASS")
    print("VERIFIED_SPEC_CARDS=PASS")
    print("UPGRADE_PANEL=PASS")
    print("GENERATED_STILL_FIRST=PASS")
    print("PEXELS_FALLBACK=ENABLED")
    print("KEN_BURNS_MOTION=PASS")
    print("GENERIC_PROFILES=BLOCKED")
    print("INTERNAL_HUD_METADATA=BLOCKED")
    print("TECHNICAL_COMPONENT_QUERIES=PASS")
    print("FEATURED_VEHICLE_QUERY_ANCHOR=PASS")
    print("CLAIM_LEVEL_PROVENANCE=PASS")
    print("ENGINEERING_SVG_SANITIZATION=PASS")


if __name__ == "__main__":
    main()
