from __future__ import annotations

import html
import re

PROFILES = {
    "engine": {"layer": "engine", "mode": "xray_cutaway", "flow": "combustion", "anchor": "engine_bay", "label": "ENGINE ARCHITECTURE", "ar": "هندسة المحرك"},
    "turbocharger": {"layer": "turbocharger", "mode": "cutaway_flow", "flow": "air", "anchor": "engine_bay", "label": "TURBOCHARGER", "ar": "التيربو"},
    "intercooler": {"layer": "intercooler", "mode": "cutaway_flow", "flow": "air_temperature", "anchor": "front", "label": "INTERCOOLER", "ar": "المبرّد البيني"},
    "cooling system": {"layer": "cooling", "mode": "flow", "flow": "coolant", "anchor": "front", "label": "COOLING LOOP", "ar": "دورة التبريد"},
    "fuel delivery": {"layer": "fuel", "mode": "flow", "flow": "fuel", "anchor": "engine_bay", "label": "FUEL DELIVERY", "ar": "منظومة الوقود"},
    "fuel injector": {"layer": "injector", "mode": "cutaway_flow", "flow": "fuel", "anchor": "engine_bay", "label": "FUEL INJECTOR", "ar": "بخاخ الوقود"},
    "ev battery": {"layer": "battery", "mode": "xray", "flow": "electric", "anchor": "floor", "label": "EV BATTERY", "ar": "بطارية كهربائية"},
    "electric powertrain": {"layer": "electric", "mode": "xray_flow", "flow": "electric", "anchor": "floor", "label": "ELECTRIC POWERTRAIN", "ar": "منظومة الدفع الكهربائي"},
    "electric motor": {"layer": "motor", "mode": "cutaway_flow", "flow": "torque", "anchor": "axle", "label": "ELECTRIC MOTOR", "ar": "المحرك الكهربائي"},
    "hybrid system": {"layer": "hybrid", "mode": "xray_flow", "flow": "electric_torque", "anchor": "powertrain", "label": "HYBRID POWER PATH", "ar": "مسار الدفع الهجين"},
    "transmission": {"layer": "transmission", "mode": "cutaway_flow", "flow": "torque", "anchor": "center", "label": "TRANSMISSION", "ar": "ناقل الحركة"},
    "gearbox": {"layer": "transmission", "mode": "cutaway_flow", "flow": "torque", "anchor": "center", "label": "GEARBOX", "ar": "علبة التروس"},
    "differential": {"layer": "differential", "mode": "cutaway_flow", "flow": "torque_split", "anchor": "rear_axle", "label": "DIFFERENTIAL", "ar": "الدفرنس"},
    "braking system": {"layer": "brakes", "mode": "cutaway_flow", "flow": "hydraulic_force", "anchor": "wheel", "label": "BRAKING SYSTEM", "ar": "نظام الفرامل"},
    "tire contact patch": {"layer": "tire", "mode": "force", "flow": "road_force", "anchor": "wheel", "label": "CONTACT PATCH", "ar": "نقطة التماس"},
    "suspension": {"layer": "suspension", "mode": "cutaway_flow", "flow": "road_force", "anchor": "wheel", "label": "SUSPENSION", "ar": "نظام التعليق"},
    "aerodynamics": {"layer": "aero", "mode": "airflow", "flow": "air", "anchor": "body", "label": "AERODYNAMICS", "ar": "الديناميكا الهوائية"},
    "downforce": {"layer": "aero", "mode": "airflow", "flow": "downforce", "anchor": "body", "label": "DOWNFORCE", "ar": "القوة السفلية"},
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
    "air": ("M180 470 C390 350 560 370 720 450 C920 530 1110 420 1420 500", "AIR / الهواء"),
    "air_temperature": ("M180 470 C390 350 560 390 700 450 C900 510 1110 420 1420 500", "AIR TEMP / حرارة الهواء"),
    "coolant": ("M430 500 C250 650 420 790 650 760 H980 C1200 740 1300 590 1080 480", "COOLANT / سائل التبريد"),
    "fuel": ("M260 660 C480 610 570 530 710 500 C850 470 930 450 1100 400", "FUEL / الوقود"),
    "electric": ("M260 640 C500 560 690 520 850 500 C1040 480 1180 540 1370 640", "POWER / الطاقة"),
    "electric_torque": ("M330 650 C560 550 700 510 850 500 C1040 500 1170 560 1370 650", "E-POWER / الدفع الكهربائي"),
    "torque": ("M520 500 H900 C1060 500 1170 590 1370 660", "TORQUE / العزم"),
    "torque_split": ("M800 500 C980 500 1110 590 1260 680 M800 500 C620 500 490 590 340 680", "TORQUE SPLIT / توزيع العزم"),
    "hydraulic_force": ("M800 400 C700 510 570 610 400 700 M800 400 C900 510 1030 610 1200 700", "BRAKE FORCE / قوة الفرملة"),
    "road_force": ("M400 590 V840 M1210 590 V840", "ROAD FORCE / قوى الطريق"),
    "downforce": ("M170 330 C500 420 1100 420 1430 330 M800 420 V700", "DOWNFORCE / قوة سفلية"),
    "combustion": ("M500 470 C650 350 740 400 800 460 M800 460 C900 370 1010 410 1130 480", "COMBUSTION / الاحتراق"),
}

SPEC_ALIASES = {
    "engine": ("المحرك", "engine"), "horsepower": ("القوة", "horsepower"), "hp": ("القوة", "hp"), "bhp": ("القوة", "bhp"),
    "power": ("القوة", "power"), "torque": ("العزم", "torque"), "nm": ("العزم", "nm"),
    "acceleration": ("التسارع", "acceleration"), "0-60": ("0-60", "0-60"), "top_speed": ("السرعة القصوى", "top_speed"),
    "transmission": ("ناقل الحركة", "transmission"), "drivetrain": ("نظام الدفع", "drivetrain"),
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
        return {"component_id": "generic", "layer_id": "generic", "mode": "reject", "flow_type": "generic", "anchor": "center", "label": "", "label_ar": "", "allowed": False}
    return {"component_id": component.replace(" ", "_"), "layer_id": profile["layer"], "mode": profile["mode"], "flow_type": profile["flow"], "anchor": profile["anchor"], "label": profile["label"], "label_ar": profile["ar"], "allowed": True}


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _flatten_specs(scene: dict) -> list[tuple[str, str, str]]:
    """Return only explicit, already-researched specs; never invent numeric values."""
    result: list[tuple[str, str, str]] = []
    for container in (scene.get("specs"), scene.get("vehicle_specs"), scene.get("facts")):
        if isinstance(container, dict):
            items = list(container.items())
        elif isinstance(container, list):
            items = []
            for item in container:
                if isinstance(item, dict):
                    key = item.get("name") or item.get("key") or item.get("label")
                    value = item.get("value") or item.get("display") or item.get("text")
                    if key and value:
                        items.append((key, value))
        else:
            continue
        for key, value in items:
            norm = re.sub(r"[^a-z0-9-]+", "_", str(key).casefold()).strip("_")
            label, canonical = SPEC_ALIASES.get(norm, (str(key), norm))
            value_text = str(value).strip()
            if value_text and len(value_text) <= 80 and not any(x[2] == canonical for x in result):
                result.append((label, value_text, canonical))
    return result[:6]


def _panel_specs(scene: dict, x: int = 70, y: int = 610, width: int = 390) -> str:
    specs = _flatten_specs(scene)
    if not specs:
        return f'<g opacity="0.94"><rect x="{x}" y="{y}" width="{width}" height="210" rx="20"/><text x="{x+30}" y="{y+55}" class="panel-title">معلومات السيارة</text><text x="{x+30}" y="{y+105}" class="muted">بيانات موثقة حسب المشهد</text><text x="{x+30}" y="{y+150}" class="muted">لا توجد أرقام غير موثقة</text></g>'
    parts = [f'<g opacity="0.96"><rect x="{x}" y="{y}" width="{width}" height="250" rx="20"/><text x="{x+30}" y="{y+50}" class="panel-title">مواصفات موثقة</text>']
    cursor = y + 95
    for label, value, _ in specs[:4]:
        parts.append(f'<text x="{x+30}" y="{cursor}" class="muted">{_esc(label)}</text><text x="{x+width-40}" y="{cursor}" text-anchor="end" class="value">{_esc(value)}</text>')
        cursor += 36
    parts.append('</g>')
    return ''.join(parts)


def _upgrade_panel(scene: dict, vertical: bool) -> str:
    note = str(scene.get("upgrade_note") or scene.get("upgrade_requirements") or "").strip()
    if not note:
        return ""
    text = re.sub(r"\s+", " ", note)[:150]
    if vertical:
        return f'<g opacity="0.96"><rect x="70" y="1510" width="940" height="230" rx="22"/><text x="105" y="1570" class="panel-title">ترقية / UPGRADES</text><text x="105" y="1625" class="muted">{_esc(text)}</text><path d="M850 1650 h100 l-28 -18 m28 18 l-28 18"/></g>'
    return f'<g opacity="0.96"><rect x="1140" y="640" width="390" height="190" rx="20"/><text x="1170" y="690" class="panel-title">ترقية / UPGRADES</text><text x="1170" y="740" class="muted">{_esc(text)}</text><path d="M1420 780 h90 l-25 -18 m25 18 l-25 18"/></g>'


def _geometry(layer: str) -> str:
    if layer == "engine":
        return '<rect x="540" y="340" width="520" height="270" rx="30"/><path d="M600 400 H1000 M600 475 H1000 M600 550 H1000"/><circle cx="650" cy="400" r="30"/><circle cx="800" cy="475" r="30"/><circle cx="950" cy="550" r="30"/>'
    if layer == "turbocharger":
        return '<circle cx="730" cy="480" r="110"/><circle cx="970" cy="480" r="110"/><path d="M620 480 H470 M1080 480 H1240 M730 370 V590 M970 370 V590"/>'
    if layer == "intercooler":
        return '<rect x="1080" y="330" width="250" height="280" rx="18"/><path d="M470 500 H1080 M1330 500 H1450"/><path d="M1120 370 V570 M1170 370 V570 M1220 370 V570 M1270 370 V570"/>'
    if layer == "cooling":
        return '<rect x="1150" y="300" width="190" height="310" rx="18"/><path d="M480 510 H1150 M1150 610 H480"/><circle cx="540" cy="560" r="48"/>'
    if layer in {"fuel", "injector"}:
        return '<path d="M420 520 H1080"/><rect x="650" y="450" width="70" height="150"/><rect x="870" y="450" width="70" height="150"/><path d="M685 600 L660 690 M905 600 L930 690"/>'
    if layer == "battery":
        cells = ''.join(f'<rect x="{x}" y="585" width="45" height="70" rx="8"/>' for x in range(520, 1130, 70))
        return '<rect x="470" y="565" width="700" height="125" rx="20"/><path d="M500 600 H1140 M500 635 H1140"/>' + cells
    if layer in {"electric", "hybrid"}:
        return '<rect x="450" y="555" width="260" height="130" rx="18"/><circle cx="930" cy="500" r="120"/><path d="M710 620 H820 M1050 500 H1240"/>'
    if layer == "motor":
        return '<circle cx="800" cy="500" r="155"/><circle cx="800" cy="500" r="70"/><path d="M800 345 V655 M645 500 H955"/>'
    if layer in {"transmission", "differential"}:
        return '<circle cx="680" cy="500" r="95"/><circle cx="880" cy="500" r="70"/><circle cx="1040" cy="500" r="48"/><path d="M585 500 H480 M1090 500 H1260"/>'
    if layer == "brakes":
        return '<circle cx="420" cy="650" r="105"/><circle cx="420" cy="650" r="52"/><path d="M375 555 C315 490 285 440 230 405"/>'
    if layer == "suspension":
        return '<path d="M430 390 V550 L500 590 L430 630 L500 670 M1180 390 V550 L1110 590 L1180 630 L1110 670"/>'
    if layer == "aero":
        return '<path d="M230 330 C520 255 1080 255 1370 330 M300 470 C590 395 1010 395 1300 470 M480 600 H1120"/>'
    if layer == "tire":
        return '<circle cx="410" cy="680" r="110"/><path d="M305 805 H515" stroke-width="14"/>'
    raise ValueError(f"unsupported visual layer: {layer}")


def build_scene_svg(scene: dict, vertical: bool = False) -> str:
    profile = visual_profile(scene)
    validate_visual_engineering({**scene, "visual_engineering": profile})
    label = _esc(profile["label"])
    label_ar = _esc(profile["label_ar"])
    flow_path, flow_label = FLOW[profile["flow_type"]]
    geometry = _geometry(profile["layer_id"])
    width, height = (1080, 1920) if vertical else (1920, 1080)
    if vertical:
        geometry_transform = 'transform="translate(-250 510) scale(0.68)"'
        flow_transform = 'transform="translate(-250 510) scale(0.68)"'
        car_box = '<rect x="45" y="250" width="990" height="1040" rx="34"/>'
        title = f'<text x="70" y="105" class="kicker">AUTOMOTIVE / SYSTEM PROFILE</text><text x="70" y="170" class="hero">{label_ar}</text><text x="70" y="215" class="subtitle">{label}</text>'
        flow_text = f'<text x="70" y="1390" class="flow-label">{_esc(flow_label)}</text>'
        specs = _panel_specs(scene, 70, 1100, 940)
    else:
        geometry_transform = 'transform="translate(80 40) scale(1.12)"'
        flow_transform = 'transform="translate(80 40) scale(1.12)"'
        car_box = '<rect x="485" y="205" width="950" height="610" rx="34"/>'
        title = f'<text x="70" y="82" class="kicker">AUTOMOTIVE / SYSTEM PROFILE</text><text x="70" y="140" class="hero">{label_ar}</text><text x="70" y="178" class="subtitle">{label}</text>'
        flow_text = f'<text x="560" y="875" class="flow-label">{_esc(flow_label)}</text>'
        specs = _panel_specs(scene, 70, 610, 390)
    upgrade = _upgrade_panel(scene, vertical)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">
<!-- Non-rendered compatibility metadata: COMPONENT  {html.escape(str(scene.get("technical_component") or profile["label"]), quote=True)} -->
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#020817"/><stop offset="0.55" stop-color="#07172a"/><stop offset="1" stop-color="#02050b"/></linearGradient>
  <radialGradient id="glow"><stop stop-color="#35b9ff" stop-opacity="0.22"/><stop offset="1" stop-color="#35b9ff" stop-opacity="0"/></radialGradient>
  <style>
    .hero{{font:700 42px 'DejaVu Sans','Noto Sans Arabic',sans-serif;fill:#ffffff}} .subtitle{{font:600 22px 'DejaVu Sans',sans-serif;fill:#8fdcff;letter-spacing:3px}}
    .kicker{{font:700 17px 'DejaVu Sans',sans-serif;fill:#62c9ff;letter-spacing:3px}} .panel-title{{font:700 22px 'DejaVu Sans','Noto Sans Arabic',sans-serif;fill:#ffffff}}
    .muted{{font:500 17px 'DejaVu Sans','Noto Sans Arabic',sans-serif;fill:#a9c4d8}} .value{{font:700 20px 'DejaVu Sans','Noto Sans Arabic',sans-serif;fill:#ffffff}}
    .flow-label{{font:700 18px 'DejaVu Sans','Noto Sans Arabic',sans-serif;fill:#7edbff;letter-spacing:1px}}
  </style>
  <filter id="soft"><feGaussianBlur stdDeviation="28"/></filter>
</defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<circle cx="{width*0.52:.0f}" cy="{height*0.48:.0f}" r="420" fill="url(#glow)" filter="url(#soft)"/>
<g opacity="0.22" stroke="#3b8db6" stroke-width="1"><path d="M0 260 H{width} M0 520 H{width} M0 780 H{width}"/><path d="M240 0 V{height} M480 0 V{height} M720 0 V{height} M960 0 V{height} M1200 0 V{height} M1440 0 V{height} M1680 0 V{height}"/></g>
<g stroke="#56c9ff" stroke-width="2" opacity="0.7">{car_box}</g>
{title}
<g {geometry_transform} stroke="#e9f8ff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity="0.86">{geometry}</g>
<g {flow_transform} stroke="#59d4ff" stroke-width="7" stroke-linecap="round" opacity="0.92"><path d="{flow_path}" stroke-dasharray="22 15"><animate attributeName="stroke-dashoffset" from="0" to="-74" dur="1.1s" repeatCount="indefinite"/></path></g>
<g stroke="#59d4ff" opacity="0.7"><path d="M{180 if vertical else 520} {400 if vertical else 260} H{430 if vertical else 760}" stroke-dasharray="6 10"><animate attributeName="stroke-dashoffset" from="0" to="-32" dur="0.8s" repeatCount="indefinite"/></path></g>
{flow_text}
{specs}
{upgrade}
<g opacity="0.8"><text x="{width-70}" y="{height-45}" text-anchor="end" class="kicker">LOCAL INFOGRAPHIC / NO AI TEXT</text></g>
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
    if profile.get("flow_type") not in FLOW:
        raise ValueError(f"unregistered visual flow: {profile.get('flow_type')}")


__all__ = ["PROFILES", "ALIASES", "FLOW", "attach_visual_engineering", "build_scene_svg", "normalize_component", "validate_visual_engineering", "visual_profile"]
