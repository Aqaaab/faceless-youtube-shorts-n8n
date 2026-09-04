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
    return {
        "section": SECTION_FALLBACKS[min(len(SECTION_FALLBACKS) - 1, (index - 1) * len(SECTION_FALLBACKS) // 25)][0],
        "section_description": SECTION_FALLBACKS[min(len(SECTION_FALLBACKS) - 1, (index - 1) * len(SECTION_FALLBACKS) // 25)][1],
        "visual_plan": "Pexels automotive footage with a clean technical annotation layer",
        "technical_component": component,
        "technical_flow": flow,
        "technical_motion": motion,
        "failure_mode": "Watch for abnormal heat, noise, vibration or performance loss when relevant.",
        "upgrade_note": "Only recommend changes that match the vehicle's supporting hardware, cooling, fuel and calibration limits.",
        "short_candidate_score": 45,
        "short_role": "technical_explainer",
        "source_claim": "General automotive mechanism; verify exact vehicle-specific specifications before publication.",
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
        scene.update(incoming)
    if isinstance(sources, list):
        clean = []
        for source in sources[:20]:
            if not isinstance(source, dict):
                continue
            url = str(source.get("url", "")).strip()
            claim = str(source.get("claim", "")).strip()
            if url.startswith(("https://", "http://")) and claim:
                clean.append({"claim": claim[:300], "url": url[:500], "authority": str(source.get("authority", "")).strip()[:120], "scene_numbers": source.get("scene_numbers", [])})
        story["sources"] = clean
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
                "failure_mode", "upgrade_note", "short_candidate_score", "short_role", "source_claim"
            ],
            "short_roles": ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"],
            "sources": "Provide authoritative URLs when the scene makes a vehicle-specific claim; prefer manufacturer documentation or established technical/government sources. Do not invent URLs.",
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
        "source_register": "scene-level claims with source URLs when applicable",
    }
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "sources.json").write_text(json.dumps(story.get("sources", []), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"EPISODE_BLUEPRINT=PASS scenes={len(story.get('scenes', []))} technical_layer=ready sources={len(story.get('sources', []))}")
    return story


if __name__ == "__main__":
    main()
