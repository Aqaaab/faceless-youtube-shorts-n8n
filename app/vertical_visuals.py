from __future__ import annotations

import html
from pathlib import Path

from .core import RUN, Story
from .story_visuals import _car_hero, _defs, _kind

W, H = 1080, 1920
TEXT = "#F4F6F8"
MUTED = "#A7AFB8"
ACCENT = "#E8B44A"
PANEL = "#0B1015"
LINE = "#303944"
MODE_LABELS = {"performance": "PERFORMANCE", "design": "DESIGN", "interior": "CABIN", "technology": "TECHNOLOGY", "efficiency": "EFFICIENCY", "safety": "SAFETY", "price": "VALUE", "hero": "AUTOMOTIVE"}


def _text(text, x, y, size, weight=500, anchor="start", fill=TEXT):
    value = html.escape(str(text)[:110])
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{value}</text>'


def _hero_car(kind: str):
    return f'<g transform="translate(-80,470) scale(.72)">{_car_hero(0,0,.82)}</g>'


def _focus_overlay(kind: str, scene):
    calls = [str(c) for c in scene.callouts[:3]]
    label = calls[0] if calls else scene.visual_intent
    if kind == "performance":
        return f'<path d="M80 1160 H1000" stroke="{LINE}" stroke-width="8"/><path d="M80 1160 L820 1010" stroke="{ACCENT}" stroke-width="10"/><circle cx="820" cy="1010" r="13" fill="{ACCENT}"/>' + _text("PERFORMANCE",80,1230,22,700,"start",MUTED)
    if kind == "design":
        return f'<path d="M80 1160 Q330 980 620 1120 T1000 1030" fill="none" stroke="{ACCENT}" stroke-width="7"/><circle cx="620" cy="1080" r="12" fill="{ACCENT}"/>' + _text("DESIGN / AERODYNAMICS",80,1230,22,700,"start",MUTED)
    if kind == "interior":
        return f'<rect x="90" y="1060" width="900" height="155" rx="24" fill="{PANEL}" stroke="#39434E"/><path d="M130 1160 L250 1100 L390 1165 L540 1090 L700 1160 L920 1095" fill="none" stroke="{ACCENT}" stroke-width="6"/>' + _text("CABIN / EXPERIENCE",110,1110,22,700,"start",MUTED)
    if kind == "technology":
        return '<g>' + ''.join(f'<circle cx="{150+i*230}" cy="1190" r="30" fill="#080B0F" stroke="{ACCENT}" stroke-width="5"/>' for i in range(4)) + '</g>' + _text("CONNECTED SYSTEM",80,1260,22,700,"start",MUTED)
    if kind == "efficiency":
        return f'<rect x="90" y="1170" width="900" height="25" rx="12" fill="{LINE}"/><rect x="90" y="1170" width="610" height="25" rx="12" fill="{ACCENT}"/>' + _text("RANGE / EFFICIENCY",90,1240,22,700,"start",MUTED)
    if kind == "safety":
        return f'<circle cx="540" cy="1160" r="135" fill="none" stroke="{ACCENT}" stroke-width="6"/><circle cx="540" cy="1160" r="82" fill="none" stroke="{LINE}" stroke-width="5"/>' + _text("SAFETY",540,1350,22,700,"middle",MUTED)
    if kind == "price":
        return f'<path d="M90 1170 H990" stroke="{LINE}" stroke-width="8"/><circle cx="620" cy="1170" r="14" fill="{ACCENT}"/>' + _text("VALUE POSITION",90,1235,22,700,"start",MUTED)
    return _text(label,540,1235,27,700,"middle",TEXT)


def _callout_stack(calls):
    out = []
    for i, call in enumerate(calls[:3]):
        y = 1370 + i * 112
        out.append(f'<rect x="60" y="{y}" width="960" height="84" rx="18" fill="{PANEL}" stroke="#39434E"/>')
        out.append(_text(call, 92, y + 53, 23, 650, "start", TEXT))
        out.append(f'<circle cx="970" cy="{y+42}" r="6" fill="{ACCENT}"/>')
    return ''.join(out)


def vertical_scene_svg(scene, topic: str, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(scene)
    layout = scene.layout.casefold()
    calls = [str(c) for c in scene.callouts[:3]]
    intent = str(scene.visual_intent).strip()
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}" data-asset-quality="premium_automotive_editorial_v2_vertical" data-motion="vertical_push_pan">
      {_defs()}
      <rect width="1080" height="1920" fill="#07090c"/>
      <rect width="1080" height="1500" fill="url(#bg)"/>
      <ellipse cx="540" cy="840" rx="510" ry="430" fill="url(#spot)"/>
      <path d="M55 120 H1025" stroke="{ACCENT}" stroke-width="4"/>
      {_text(topic,55,85,28,700,"start",TEXT)}
      {_hero_car(kind)}
      {_focus_overlay(kind, scene)}
      {_callout_stack(calls)}
      <rect x="60" y="1720" width="960" height="135" rx="24" fill="#080B0F" stroke="#303944"/>
      {_text(intent,92,1775,23,550,"start",TEXT)}
      {_text(MODE_LABELS.get(kind, "AUTOMOTIVE"),540,1835,18,700,"middle",MUTED)}
    </svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_vertical_visuals(story: Story, out_dir: Path = RUN / "vertical_scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        vertical_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
