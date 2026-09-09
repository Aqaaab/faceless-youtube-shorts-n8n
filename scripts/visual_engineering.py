from __future__ import annotations

import html
import re

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

FLOW = {
    "air": "M220 430 C430 350 560 370 720 440 C920 520 1100 420 1380 500",
    "air_temperature": "M220 430 C430 350 560 390 690 440 C900 500 1110 420 1380 500",
    "coolant": "M470 460 C300 600 430 730 650 720 H960 C1190 710 1260 570 1080 460",
    "fuel": "M300 650 C500 600 560 520 700 500 C820 480 900 450 1040 410",
    "electric": "M300 620 C520 560 690 520 830 500 C1010 470 1150 520 1300 620",
    "electric_torque": "M360 620 C570 540 700 500 840 500 C1030 500 1140 550 1300 620",
    "torque": "M560 500 H900 C1060 500 1160 590 1320 650",
    "torque_split": "M800 500 C980 500 1090 580 1220 660 M800 500 C620 500 510 580 380 660",
    "hydraulic_force": "M800 400 C720 500 590 590 430 680 M800 400 C880 500 1010 590 1190 680",
    "road_force": "M410 600 V820 M1200 600 V820",
    "downforce": "M200 300 C520 390 1080 390 1400 300 M800 390 V620",
    "combustion": "M520 440 C650 360 730 390 800 450 M800 450 C900 370 970 400 1080 460",
}


def normalize_component(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    if text in ALIASES:
        return ALIASES[text]
    for alias, target in sorted(ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return target
    return text


def visual_profile(scene: dict) -> dict:
    component = normalize_component(scene.get("technical_component"))
    profile = PROFILES.get(component)
    if profile is None:
        return {"component_id": "generic", "layer_id": "generic", "mode": "reject", "flow_type": "generic", "anchor": "center", "label": "", "allowed": False}
    return {"component_id": component.replace(" ", "_"), "layer_id": profile["layer"], "mode": profile["mode"], "flow_type": profile["flow"], "anchor": profile["anchor"], "label": profile["label"], "allowed": True}


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _geometry(layer: str) -> str:
    if layer == "engine":
        return '<rect x="560" y="340" width="440" height="250" rx="28"/><path d="M620 400 H940 M620 470 H940 M620 540 H940"/><circle cx="670" cy="400" r="28"/><circle cx="790" cy="470" r="28"/><circle cx="910" cy="540" r="28"/>'
    if layer == "turbocharger":
        return '<circle cx="760" cy="480" r="105"/><circle cx="980" cy="480" r="105"/><path d="M655 480 H520 M1085 480 H1230 M760 375 V585 M980 375 V585"/>'
    if layer == "cooling":
        return '<rect x="1160" y="300" width="170" height="300" rx="18"/><path d="M520 520 H1160 M1160 600 H520"/><circle cx="560" cy="560" r="45"/>'
    if layer in {"fuel", "injector"}:
        return '<path d="M430 520 H1060"/><rect x="650" y="455" width="60" height="150"/><rect x="850" y="455" width="60" height="150"/><path d="M680 605 L660 680 M880 605 L900 680"/>'
    if layer == "battery":
        cells = ''.join(f'<rect x="{x}" y="585" width="45" height="70" rx="8"/>' for x in range(520, 1130, 70))
        return '<rect x="470" y="570" width="700" height="120" rx="20"/><path d="M500 600 H1140 M500 635 H1140"/>' + cells
    if layer in {"electric", "hybrid"}:
        return '<rect x="470" y="560" width="240" height="120" rx="18"/><circle cx="930" cy="500" r="115"/><path d="M710 620 H815 M1045 500 H1230"/>'
    if layer == "motor":
        return '<circle cx="800" cy="500" r="150"/><circle cx="800" cy="500" r="70"/><path d="M800 350 V650 M650 500 H950"/>'
    if layer in {"transmission", "differential"}:
        return '<circle cx="720" cy="500" r="90"/><circle cx="900" cy="500" r="65"/><circle cx="1030" cy="500" r="45"/><path d="M630 500 H520 M1075 500 H1240"/>'
    if layer == "brakes":
        return '<circle cx="420" cy="650" r="95"/><circle cx="420" cy="650" r="48"/><path d="M380 560 C330 500 300 450 240 410"/>'
    if layer == "suspension":
        return '<path d="M430 400 V560 L500 600 L430 640 L500 680 M1180 400 V560 L1110 600 L1180 640 L1110 680"/>'
    if layer == "aero":
        return '<path d="M250 330 C520 260 1080 260 1350 330 M320 470 C600 400 1000 400 1280 470 M500 600 H1100"/>'
    if layer == "tire":
        return '<circle cx="410" cy="680" r="105"/><path d="M310 790 H510" stroke-width="12"/>'
    raise ValueError(f"unsupported visual layer: {layer}")


def build_scene_svg(scene: dict, vertical: bool = False) -> str:
    profile = visual_profile(scene)
    validate_visual_engineering({**scene, "visual_engineering": profile})
    label = _esc(profile["label"])
    flow = FLOW[profile["flow_type"]]
    geometry = _geometry(profile["layer_id"])
    width, height = (1080, 1920) if vertical else (1600, 900)
    scale = ' transform="translate(0 450) scale(0.675)"' if vertical else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
<g{scale} stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
<path opacity="0.16" d="M175 610 C230 500 390 440 610 425 L940 425 C1135 430 1300 480 1425 585 L1480 650 L1440 700 L1270 710 L510 700 L350 710 L190 680 Z"/>
<g opacity="0.95">{geometry}</g>
<path class="flow" opacity="0.85" d="{flow}" stroke-dasharray="18 14"><animate attributeName="stroke-dashoffset" from="0" to="-64" dur="1.1s" repeatCount="indefinite"/></path>
</g>
<g fill="white" font-family="DejaVu Sans, Arial, sans-serif"><text x="60" y="100" font-size="30" letter-spacing="2">{label}</text><path d="M60 125 H430" stroke="white" opacity="0.45"/></g>
</svg>'''


def attach_visual_engineering(scene: dict) -> dict:
    scene["visual_engineering"] = visual_profile(scene)
    return scene


def validate_visual_engineering(scene: dict) -> None:
    profile = scene.get("visual_engineering")
    if not isinstance(profile, dict):
        raise ValueError("missing visual_engineering profile")
    required = ("component_id", "layer_id", "mode", "flow_type", "anchor", "label", "allowed")
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError("visual_engineering missing " + ",".join(missing))
    if not profile.get("allowed") or profile.get("component_id") == "generic" or profile.get("mode") == "reject":
        raise ValueError("generic/hud-only visual profiles are forbidden in production")
    if profile.get("layer_id") not in {p["layer"] for p in PROFILES.values()}:
        raise ValueError(f"unregistered visual layer: {profile.get('layer_id')}")


__all__ = ["PROFILES", "ALIASES", "attach_visual_engineering", "build_scene_svg", "normalize_component", "validate_visual_engineering", "visual_profile"]
