from __future__ import annotations

import json
import os
import re
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("EPISODE_BLUEPRINT_RETRIES", "2")))

SECTION_FALLBACKS = [
    ("identity", "Vehicle identity, generation and production context"),
    ("exterior", "Exterior design and aerodynamic intent"),
    ("cabin", "Cabin, controls and driver technology"),
    ("engine", "Engine architecture and combustion or motor layout"),
    ("airflow", "Air intake, turbocharging or motor airflow"),
    ("fuel_cooling", "Fuel delivery, lubrication and cooling"),
    ("power", "Power, torque and real-world performance"),
    ("drivetrain", "Transmission, differential and drive system"),
    ("chassis", "Suspension, steering, tires and brakes"),
    ("upgrade", "Modification paths, constraints and ownership verdict"),
]

TECH_KEYWORDS = {
    "turbo": ("Turbocharger", "exhaust gas → turbine → compressor → intake air", "Use a transparent cutaway/flow overlay"),
    "intercool": ("Intercooler", "hot compressed air → heat exchanger → cooler intake air", "Show airflow and temperature direction"),
    "radiator": ("Cooling system", "water pump → engine → radiator → cooled coolant", "Show coolant circulation arrows"),
    "cooling": ("Cooling system", "hot engine coolant → radiator → cooled return", "Show a looping thermal flow"),
    "fuel": ("Fuel delivery", "tank → pump → injector → combustion chamber", "Reveal the fuel path"),
    "inject": ("Fuel injector", "fuel rail → injector → intake/cylinder charge", "Zoom to injector and pulse concept"),
    "brake": ("Braking system", "pedal → hydraulic pressure → caliper → rotor", "Animate force moving to the wheel"),
    "tire": ("Tire contact patch", "wheel load → contact patch → road friction", "Highlight the contact patch"),
    "suspension": ("Suspension", "road input → spring/damper → chassis", "Show compression and rebound"),
    "differential": ("Differential", "driveshaft → differential → left/right axle torque", "Show torque split between wheels"),
    "transmission": ("Transmission", "engine speed/torque → gearset → driveshaft", "Show gear selection and output"),
    "gearbox": ("Gearbox", "input shaft → selected gear → output shaft", "Show the selected gear path"),
    "battery": ("EV battery", "battery cells → inverter → motor → wheels", "Show electrical energy flow"),
    "electric": ("Electric powertrain", "battery → inverter → motor → wheels", "Show instant torque path"),
    "hybrid": ("Hybrid system", "engine + motor → control unit → wheels", "Show the two power sources"),
    "aero": ("Aerodynamics", "airflow → body surface → downforce/drag", "Trace air over the body"),
    "downforce": ("Downforce", "airflow → aero surfaces → vertical load", "Show force arrows at speed"),
    "engine": ("Engine architecture", "air + fuel + spark/compression → combustion → crankshaft", "Use a generic engine cutaway overlay"),
    "motor": ("Electric motor", "inverter current → magnetic field → rotor → wheels", "Show the motor torque path"),
}

SPEC_RE = re.compile(r"\b(?:horsepower|hp|bhp|ps|nm|lb-ft|0-60|0\s*(?:to|-|–)\s*60|quarter mile|top speed|displacement|liter engine|litre engine|cubic)\b", re.I)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _technical_defaults(scene: dict, index: int) -> dict:
    blob = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject", "pexels_query"))
    tokens = _tokens(blob)
    component, flow, motion = "Automotive system", "input → mechanism → output", "Reveal the mechanism and its flow"
    for key, value in TECH_KEYWORDS.items():
        if key in tokens or key in blob.casefold():
            component, flow, motion = value
            break
    spec_status = "FACT_SOURCE_REQUIRED" if SPEC_RE.search(blob) else "GENERAL_EXPLANATION"
    return {
        "section": SECTION_FALLBACKS[min(len(SECTION_FALLBACKS) - 1, (index - 1) * len(SECTION_FALLBACKS) // 25)][0],
        "section_description": SECTION_FALLBACKS[min(len(SECTION_FALLBACKS) - 1, (index - 1) * len(SECTION_FALLBACKS) // 25)][1],
        "visual_plan": "Pexels automotive footage with a clean technical annotation layer",
        "technical_component": component,
        "technical_flow": flow,
        "technical_motion": motion,
        "failure_mode": "Watch for abnormal heat, noise, vibration or performance loss when relevant.",
        "upgrade_note": "Only recommend changes that match the vehicle's supporting hardware, cooling, fuel and calibration limits.",
        "upgrade_requirements": "Check cooling, fuel delivery, braking, drivetrain and calibration limits before modifying output.",
        "spec_status": spec_status,
        "modified_estimate": "NO_NUMERIC_ESTIMATE",
        "short_candidate_score": 45,
        "short_role": "technical_explainer",
        "source_claim": "General automotive mechanism; exact vehicle-specific specifications require a mapped trusted source.",
    }


def _merge_annotations(story: dict, payload: dict) -> dict:
    annotations = payload.get("scene_annotations") if isinstance(payload, dict) else None
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(annotations, list):
        annotations = []
    for index, scene in enumerate(story.get("scenes", [])):
        fallback = _technical_defaults(scene, index + 1)
        incoming = annotations[index] if index < len(annotations) and isinstance(annotations[index], dict) else {}
        for key, value in fallback.items():
            if key not in incoming or not str(incoming.get(key, "")).strip():
                incoming[key] = value
        try:
            incoming["short_candidate_score"] = max(0, min(100, float(incoming.get("short_candidate_score", 45))))
        except (TypeError, ValueError):
            incoming["short_candidate_score"] = 45
        if str(incoming.get("spec_status", "")).upper() not in {"FACT_SOURCE_REQUIRED", "GENERAL_EXPLANATION", "MODIFIED_ESTIMATE"}:
            incoming["spec_status"] = fallback["spec_status"]
        scene.update(incoming)
    clean = []
    if isinstance(sources, list):
        for source in sources[:30]:
            if not isinstance(source, dict):
                continue
            url = str(source.get("url", "")).strip()
            claim = str(source.get("claim", "")).strip()
            scene_numbers = source.get("scene_numbers", [])
            if url.startswith("https://") and claim and isinstance(scene_numbers, list):
                clean.append({
                    "claim": claim[:300], "url": url[:500],
                    "authority": str(source.get("authority", "")).strip()[:120],
                    "scene_numbers": scene_numbers,
                })
    story["sources"] = clean
    story["source_system"] = {
        "policy": "Vehicle-specific specifications require a mapped trusted source; general mechanisms may use the built-in technical explanation.",
        "source_count": len(clean),
        "external_media": "Pexels only",
    }
    return story


def main() -> dict:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    topic = os.getenv("VIDEO_TOPIC", "automotive engineering")
    prompt = {
        "task": "episode_blueprint_enrichment",
        "topic": topic,
        "story": story,
        "contract": {
            "niche": "cars and automotive technology only",
            "purpose": "Turn the long-form story into a coherent automotive encyclopedia episode.",
            "do_not_rewrite": "Do not rewrite narration. Return only scene annotations and a compact source register.",
            "scene_annotations": [
                "section", "section_description", "visual_plan", "technical_component", "technical_flow", "technical_motion",
                "failure_mode", "upgrade_note", "upgrade_requirements", "spec_status", "modified_estimate",
                "short_candidate_score", "short_role", "source_claim"
            ],
            "short_roles": ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"],
            "spec_policy": "Mark vehicle-specific numeric specifications FACT_SOURCE_REQUIRED and map them to source URLs. Mark modification numbers MODIFIED_ESTIMATE and state that they are estimates, not guarantees.",
            "sources": "Provide authoritative HTTPS URLs for vehicle-specific claims; prefer manufacturer documentation, government/standards sources, or established automotive publications. Do not invent URLs. Include scene_numbers.",
            "visual_rule": "Pexels remains the only external footage source. Technical overlays are generated locally from the annotations.",
        },
        "return": "JSON only with scene_annotations for all 25 scenes and sources.",
    }
    result: dict = {}
    for attempt in range(RETRIES):
        try:
            candidate = extract_json(call(json.dumps(prompt, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=180))
            if isinstance(candidate, dict):
                result = candidate
                break
        except Exception as exc:
            print(f"EPISODE_BLUEPRINT_RETRY={attempt + 1} error={exc}")
    story = _merge_annotations(story, result)
    story["episode_format"] = {
        "master": "25-scene automotive encyclopedia",
        "shorts": "4 unique Shorts selected from the master scenes",
        "media": "Pexels footage only",
        "technical_layer": "generated locally from scene annotations",
        "source_register": "scene-level claims with mapped source URLs",
        "visual_fallback": "technical HUD/diagram layer when Pexels cannot show the mechanism directly",
    }
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "episode_blueprint.json").write_text(json.dumps({
        "episode_format": story["episode_format"],
        "scenes": story.get("scenes", []),
        "sources": story.get("sources", []),
        "source_system": story.get("source_system", {}),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "sources.json").write_text(json.dumps(story.get("sources", []), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"EPISODE_BLUEPRINT=PASS scenes={len(story.get('scenes', []))} technical_layer=ready sources={len(story.get('sources', []))}")
    return story


if __name__ == "__main__":
    main()
