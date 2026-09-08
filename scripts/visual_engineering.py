from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "assets" / "blueprint" / "automotive_blueprint.svg"

# Deterministic visual registry. The language model chooses the technical concept;
# this registry decides which geometry is allowed to appear on screen.
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
    "engine architecture": "engine",
    "engine": "engine",
    "turbo": "turbocharger",
    "turbocharger": "turbocharger",
    "intercooler": "intercooler",
    "cooling": "cooling system",
    "cooling system": "cooling system",
    "fuel": "fuel delivery",
    "fuel delivery": "fuel delivery",
    "fuel injector": "fuel injector",
    "battery": "ev battery",
    "ev battery": "ev battery",
    "electric": "electric powertrain",
    "electric powertrain": "electric powertrain",
    "electric motor": "electric motor",
    "motor": "electric motor",
    "hybrid": "hybrid system",
    "hybrid system": "hybrid system",
    "transmission": "transmission",
    "gearbox": "gearbox",
    "differential": "differential",
    "brake": "braking system",
    "braking system": "braking system",
    "tire": "tire contact patch",
    "tire contact patch": "tire contact patch",
    "suspension": "suspension",
    "aero": "aerodynamics",
    "aerodynamics": "aerodynamics",
    "downforce": "downforce",
}


def normalize_component(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return ALIASES.get(text, text)


def visual_profile(scene: dict) -> dict:
    component = normalize_component(scene.get("technical_component"))
    profile = PROFILES.get(component)
    if profile is None:
        profile = {"layer": "generic", "mode": "hud_only", "flow": "generic", "anchor": "center", "label": "AUTOMOTIVE SYSTEM"}
        component = "generic"
    return {
        "component_id": component.replace(" ", "_"),
        "layer_id": profile["layer"],
        "mode": profile["mode"],
        "flow_type": profile["flow"],
        "anchor": profile["anchor"],
        "label": profile["label"],
        "allowed": component != "generic",
    }


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _flow_geometry(flow: str) -> str:
    paths = {
        "air": '<path class="flow" d="M250 430 C430 360 520 360 690 430"/><path class="flow" d="M760 430 C950 360 1120 390 1360 500"/>',
        "air_temperature": '<path class="flow" d="M260 450 C430 380 540 390 680 440"/><path class="flow" d="M820 440 C1000 390 1160 420 1350 500"/>',
        "coolant": '<path class="flow" d="M520 500 C430 540 430 650 560 665 C760 690 900 690 1060 650 C1180 620 1180 500 1050 470"/>',
        "fuel": '<path class="flow" d="M360 650 C500 600 560 520 700 500 C780 490 820 470 900 440"/>',
        "electric": '<path class="flow" d="M430 610 C620 560 720 560 850 500 C980 440 1080 470 1220 560"/>',
        "electric_torque": '<path class="flow" d="M470 610 C650 550 720 520 850 500"/><path class="flow" d="M850 500 C1000 500 1080 540 1230 600"/>',
        "torque": '<path class="flow" d="M690 500 C820 500 930 500 1060 570 C1150 615 1210 630 1300 650"/>',
        "torque_split": '<path class="flow" d="M850 520 C960 520 1050 570 1160 650"/><path class="flow" d="M850 520 C760 520 650 570 540 650"/>',
        "hydraulic_force": '<path class="flow" d="M720 420 C690 500 600 560 470 650"/><path class="flow" d="M720 420 C760 500 850 560 1160 650"/>',
        "road_force": '<path class="flow" d="M410 650 V790"/><path class="flow" d="M1200 650 V790"/>',
        "downforce": '<path class="flow" d="M220 300 C500 390 1100 390 1380 300"/><path class="flow" d="M800 390 V570"/>',
        "combustion": '<path class="flow" d="M560 430 C650 390 700 390 760 430"/><path class="flow" d="M790 430 C850 390 920 400 1010 440"/>',
        "generic": '<path class="flow" d="M500 500 H1100"/>',
    }
    return paths.get(flow, paths["generic"])


def build_scene_svg(scene: dict, vertical: bool = False) -> str:
    profile = visual_profile(scene)
    label = _esc(profile["label"])
    component = _esc(scene.get("technical_component") or "Automotive system")
    flow = _flow_geometry(profile["flow_type"])
    view = "0 0 1600 900"
    # The same lightweight vector vocabulary is used for every component. No
    # external image provider or heavy graphics dependency is introduced.
    opacity = "0.92" if profile["allowed"] else "0.42"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="{view}" fill="none">
  <g stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.58">
    <path d="M175 610 C230 500 390 440 610 425 L940 425 C1135 430 1300 480 1425 585 L1480 650 L1440 700 L1270 710 L1130 700 L510 700 L350 710 L190 680 Z"/>
    <path d="M505 470 L575 565 L1010 565 L1090 470"/>
    <circle cx="410" cy="680" r="92"/><circle cx="1200" cy="680" r="92"/>
    <path d="M610 425 L675 355 L940 355 L1010 425"/>
  </g>
  <g stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}">
    <g fill="none">
      <rect x="610" y="395" width="330" height="135" rx="22"/>
      <circle cx="675" cy="460" r="35"/><circle cx="875" cy="460" r="35"/>
      <path d="M600 535 H955" opacity="0.55"/>
    </g>
    <g id="component-{profile['layer_id']}">
      <path d="M500 560 C600 500 650 430 760 430 C870 430 950 500 1080 560" opacity="0.28"/>
      {flow}
      <path d="M500 560 C620 500 700 480 820 500 C940 520 1040 560 1120 620" stroke-dasharray="12 12" opacity="0.75"/>
    </g>
  </g>
  <g fill="white" font-family="DejaVu Sans, Arial, sans-serif" letter-spacing="2">
    <text x="80" y="90" font-size="30" opacity="0.82">{label}</text>
    <text x="80" y="128" font-size="20" opacity="0.58">COMPONENT  {component}</text>
    <text x="80" y="160" font-size="18" opacity="0.48">MODE  {profile['mode'].upper()}   FLOW  {profile['flow_type'].upper()}</text>
  </g>
  <g stroke="white" stroke-width="2" opacity="0.45">
    <path d="M80 190 H420"/><path d="M1180 190 H1520"/>
  </g>
</svg>'''


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


__all__ = ["PROFILES", "attach_visual_engineering", "build_scene_svg", "normalize_component", "validate_visual_engineering", "visual_profile"]
