from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "assets" / "blueprint" / "automotive_blueprint.svg"

PROFILES = {
    "engine": {"layer": "engine", "mode": "xray_cutaway", "flow": "combustion", "anchor": "engine_bay", "label": "ENGINE ARCHITECTURE"},
    "turbocharger": {"layer": "turbocharger", "mode": "cutaway_flow", "flow": "air", "anchor": "engine_bay", "label": "TURBOCHARGER"},
    "intercooler": {"layer": "intercooler", "mode": "cutaway_flow", "flow": "air_temperature", "anchor": "front", "label": "INTERCOOLER"},
    "cooling system": {"layer": "cooling", "mode": "flow", "flow": "coolant", "anchor": "front", "label": "COOLING LOOP"},
    "fuel delivery": {"layer": "fuel", "mode": "flow", "flow": "fuel", "anchor": "engine_bay", "label": "FUEL DELIVERY"},
    "fuel injector": {"layer": "injector", "mode": "cutaway_flow", "flow": "fuel", "anchor": "engine_bay", "label": "FUEL INJECTOR"},
    "ev battery": {"layer": "battery", "mode": "xray", "flow": "electric", "anchor": "floor", "label": "EV BATTERY"},
    "electric powertrain": {"layer": "electric", "mode": "xray_flow", "flow": "electric", "anchor": "floor", "label": "ELECTRIC POWERTRAIN"},
    "electric motor": {"layer": "motor", "mode": "cutaway_flow", "flow": "torque", "anchor": "axle", "label": "ELECTRIC MOTOR"},
    "hybrid system": {"layer": "hybrid", "mode": "xray_flow", "flow": "electric_torque", "anchor": "powertrain", "label": "HYBRID POWER PATH"},
    "transmission": {"layer": "transmission", "mode": "cutaway_flow", "flow": "torque", "anchor": "center", "label": "TRANSMISSION"},
    "gearbox": {"layer": "transmission", "mode": "cutaway_flow", "flow": "torque", "anchor": "center", "label": "GEARBOX"},
    "differential": {"layer": "differential", "mode": "cutaway_flow", "flow": "torque_split", "anchor": "rear_axle", "label": "DIFFERENTIAL"},
    "braking system": {"layer": "brakes", "mode": "cutaway_flow", "flow": "hydraulic_force", "anchor": "wheel", "label": "BRAKING SYSTEM"},
    "tire contact patch": {"layer": "tire", "mode": "force", "flow": "road_force", "anchor": "wheel", "label": "CONTACT PATCH"},
    "suspension": {"layer": "suspension", "mode": "cutaway_flow", "flow": "road_force", "anchor": "wheel", "label": "SUSPENSION"},
    "aerodynamics": {"layer": "aero", "mode": "airflow", "flow": "air", "anchor": "body", "label": "AERODYNAMICS"},
    "downforce": {"layer": "aero", "mode": "airflow", "flow": "downforce", "anchor": "body", "label": "DOWNFORCE"},
}

ALIASES = {
    "engine architecture": "engine", "engine": "engine", "motor": "electric motor", "electric motor": "electric motor",
    "turbo": "turbocharger", "turbocharger": "turbocharger", "intercooler": "intercooler",
    "cooling": "cooling system", "cooling system": "cooling system", "radiator": "cooling system",
    "fuel": "fuel delivery", "fuel delivery": "fuel delivery", "injector": "fuel injector", "fuel injector": "fuel injector",
    "battery": "ev battery", "ev battery": "ev battery", "electric": "electric powertrain", "electric powertrain": "electric powertrain",
    "hybrid": "hybrid system", "hybrid system": "hybrid system", "transmission": "transmission", "gearbox": "gearbox",
    "differential": "differential", "brake": "braking system", "braking system": "braking system",
    "tire": "tire contact patch", "tire contact patch": "tire contact patch", "suspension": "suspension",
    "aero": "aerodynamics", "aerodynamics": "aerodynamics", "downforce": "downforce",
}


def normalize_component(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()
    if text in ALIASES:
        return ALIASES[text]
    for alias, target in sorted(ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return target
    return text


def visual_profile(scene: dict) -> dict:
    component = normalize_component(scene.get("technical_component"))
    profile = PROFILES.get(component)
    if profile is None:
        profile = {"layer": "generic", "mode": "hud_only", "flow": "generic", "anchor": "center", "label": "AUTOMOTIVE SYSTEM"}
        component = "generic"
    return {"component_id": component.replace(" ", "_"), "layer_id": profile["layer"], "mode": profile["mode"], "flow_type": profile["flow"], "anchor": profile["anchor"], "label": profile["label"], "allowed": component != "generic"}


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _flow_geometry(flow: str) -> str:
    return {
        "air": '<path class="flow" d="M250 430 C430 360 520 360 690 430"/><path class="flow" d="M760 430 C950 360 1120 390 1360 500"/>',
        "air_temperature": '<path class="flow" d="M250 430 C430 380 560 390 680 440"/><path class="flow" d="M820 440 C1000 390 1160 420 1360 500"/>',
        "coolant": '<path class="flow" d="M480 470 C350 560 430 690 610 700 H990 C1170 690 1240 560 1080 470"/>',
        "fuel": '<path class="flow" d="M320 650 C500 600 560 520 700 500 C790 490 830 450 930 420"/>',
        "electric": '<path class="flow" d="M350 620 C550 560 680 540 820 500 C980 450 1110 500 1260 600"/>',
        "electric_torque": '<path class="flow" d="M420 620 C620 550 720 510 840 500"/><path class="flow" d="M840 500 C1020 500 1110 550 1260 620"/>',
        "torque": '<path class="flow" d="M650 500 H900 C1030 500 1120 590 1300 650"/>',
        "torque_split": '<path class="flow" d="M820 520 C980 520 1080 590 1200 660"/><path class="flow" d="M820 520 C660 520 560 590 440 660"/>',
        "hydraulic_force": '<path class="flow" d="M800 400 C720 500 590 580 450 670"/><path class="flow" d="M800 400 C880 500 1010 580 1190 670"/>',
        "road_force": '<path class="flow" d="M410 650 V820"/><path class="flow" d="M1200 650 V820"/>',
        "downforce": '<path class="flow" d="M220 300 C500 390 1100 390 1380 300"/><path class="flow" d="M800 390 V600"/>',
        "combustion": '<path class="flow" d="M560 440 C650 390 710 390 760 440"/><path class="flow" d="M800 440 C860 390 930 400 1020 445"/>',
        "generic": '<path class="flow" d="M500 500 H1100"/>',
    }.get(flow, '<path class="flow" d="M500 500 H1100"/>')


def _component_geometry(profile: dict) -> str:
    layer, mode = profile["layer"], profile["mode"]
    if layer == "engine":
        return '<rect x="560" y="340" width="440" height="250" rx="28"/><path d="M620 400 H940 M620 470 H940 M620 540 H940"/><circle cx="670" cy="400" r="28"/><circle cx="790" cy="470" r="28"/><circle cx="910" cy="540" r="28"/>'
    if layer == "turbocharger":
        return '<circle cx="760" cy="480" r="105"/><circle cx="980" cy="480" r="105"/><path d="M655 480 H520 M1085 480 H1230"/><path d="M760 375 V585 M980 375 V585"/>'
    if layer == "cooling":
        return '<rect x="1160" y="300" width="170" height="300" rx="18"/><path d="M520 520 H1160 M1160 600 H520"/><circle cx="560" cy="560" r="45"/>'
    if layer in {"fuel", "injector"}:
        return '<path d="M430 520 H1060"/><rect x="650" y="455" width="60" height="150"/><rect x="850" y="455" width="60" height="150"/><path d="M680 605 L660 680 M880 605 L900 680"/>'
    if layer == "battery":
        return '<rect x="470" y="570" width="700" height="120" rx="20"/><path d="M500 600 H1140 M500 635 H1140"/>' + ''.join(f'<rect x="{x}" y="585" width="45" height="70" rx="8"/>' for x in range(520, 1130, 70))
    if layer in {"electric", "hybrid"}:
        return '<rect x="470" y="560" width="240" height="120" rx="18"/><circle cx="930" cy="500" r="115"/><path d="M710 620 H815 M1045 500 H1230"/>'
    if layer == "motor":
        return '<circle cx="800" cy="500" r="150"/><circle cx="800" cy="500" r="70"/><path d="M800 350 V650 M650 500 H950"/>'
    if layer in {"transmission", "differential"}:
        return '<circle cx="720" cy="500" r="90"/><circle cx="900" cy="500" r="65"/><circle cx="1030" cy="500" r="45"/><path d="M630 500 H520 M1075 500 H1240"/>'
    if layer == "brakes":
        return '<circle cx="420" cy="650" r="95"/><circle cx="420" cy="650" r="48"/><path d="M380 560 C330 500 300 450 240 410"/>'
    if layer == "suspension":
        return '<path d="M430 400 V560 L500 600 L430 640 L500 680"/><path d="M1180 400 V560 L1110 600 L1180 640 L1110 680"/>'
    if layer == "aero":
        return '<path d="M250 330 C520 260 1080 260 1350 330"/><path d="M320 470 C600 400 1000 400 1280 470"/><path d="M500 600 H1100"/>'
    if layer == "tire":
        return '<circle cx="410" cy="680" r="105"/><path d="M310 790 H510" stroke-width="12"/><path d="M1200 680 A105 105 0 0 1 1300 790"/>'
    return '<rect x="560" y="390" width="400" height="210" rx="25"/>'


def build_scene_svg(scene: dict, vertical: bool = False) -> str:
    profile = visual_profile(scene)
    label = _esc(profile["label"])
    component = _esc(scene.get("technical_component") or "Automotive system")
    flow = _flow_geometry(profile["flow_type"])
    opacity = "0.94" if profile["allowed"] else "0.42"
    xray = profile["mode"] in {"xray", "xray_cutaway", "xray_flow"}
    cutaway = profile["mode"] in {"cutaway_flow", "xray_cutaway", "xray_flow"}
    shell = 'opacity="0.16" stroke-dasharray="10 10"' if xray else 'opacity="0.58"'
    cut = '<path d="M1030 320 L1230 700" stroke-dasharray="16 12" opacity="0.55"/><text x="1120" y="350" font-size="18" opacity="0.7">X-RAY SECTION</text>' if xray else ''
    cut_overlay = '<path d="M520 350 L1080 650" stroke-dasharray="8 10" opacity="0.45"/>' if cutaway else ''
    geometry = _component_geometry(profile)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" fill="none">
<g stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" {shell}><path d="M175 610 C230 500 390 440 610 425 L940 425 C1135 430 1300 480 1425 585 L1480 650 L1440 700 L1270 710 L510 700 L350 710 L190 680 Z"/><circle cx="410" cy="680" r="92"/><circle cx="1200" cy="680" r="92"/></g>
<g stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"><g id="component-{profile['layer_id']}">{geometry}{cut}{cut_overlay}{flow}</g></g>
<g fill="white" font-family="DejaVu Sans, Arial, sans-serif" letter-spacing="2"><text x="80" y="90" font-size="30" opacity="0.9">{label}</text><text x="80" y="128" font-size="20" opacity="0.65">COMPONENT  {component}</text><text x="80" y="160" font-size="18" opacity="0.55">MODE  {profile['mode'].upper()}   FLOW  {profile['flow_type'].upper()}</text></g>
<g stroke="white" stroke-width="2" opacity="0.45"><path d="M80 190 H420"/><path d="M1180 190 H1520"/></g></svg>'''


def attach_visual_engineering(scene: dict) -> dict:
    scene["visual_engineering"] = visual_profile(scene)
    return scene


def validate_visual_engineering(scene: dict) -> None:
    profile = scene.get("visual_engineering")
    if not isinstance(profile, dict):
        raise ValueError("missing visual_engineering profile")
    for key in ("component_id", "layer_id", "mode", "flow_type", "anchor", "label", "allowed"):
        if key not in profile:
            raise ValueError(f"visual_engineering missing {key}")
    if profile["allowed"] and profile["layer_id"] == "generic":
        raise ValueError("allowed visual profile cannot use generic layer")


__all__ = ["PROFILES", "ALIASES", "attach_visual_engineering", "build_scene_svg", "normalize_component", "validate_visual_engineering", "visual_profile"]
