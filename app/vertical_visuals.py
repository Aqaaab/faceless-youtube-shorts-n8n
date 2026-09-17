from __future__ import annotations

import html
from pathlib import Path

from .core import RUN, Story
from .story_visuals import ACCENT, LINE, MUTED, PANEL, TEXT, _car, _defs, _family, _has_arabic, _kind, _text

W, H = 1080, 1920


def _card(value: str, y: int, width: int = 920, x: int = 80) -> str:
    return f'<rect x="{x}" y="{y}" width="{width}" height="92" rx="22" fill="{PANEL}" fill-opacity=".95" stroke="#44515E" stroke-width="2"/>{_text(value,x+28,y+59,30,650,"start",TEXT)}<circle cx="{x+width-30}" cy="{y+46}" r="7" fill="{ACCENT}"/>'


def _focus_art(family: str, scene, y: int = 1030) -> str:
    calls = [str(c).strip() for c in scene.callouts if str(c).strip()]
    if family == "wheel_detail":
        return f'<g transform="translate(540 {y+120})"><circle cx="0" cy="0" r="190" fill="#050709" stroke="#DDE4E9" stroke-width="11"/>{_car("translate(-410 -205) scale(.55)")}<circle cx="0" cy="0" r="125" fill="#202A34" stroke="{ACCENT}" stroke-width="6"/><path d="M-82 0 H82 M0 -82 V82" stroke="#BFC8CF" stroke-width="5"/><text x="-180" y="270" font-family="Noto Sans" font-size="22" fill="{MUTED}">DETAIL / CONTROL</text></g>'
    if family in {"technology", "battery", "charging", "safety"}:
        label = {"technology":"TECHNOLOGY", "battery":"ENERGY", "charging":"CHARGING", "safety":"SAFETY"}[family]
        dots = ''.join(f'<circle cx="{180+i*230}" cy="{y+115}" r="18" fill="{ACCENT}"/>' for i in range(4))
        return f'<path d="M150 {y+115} H930" stroke="{LINE}" stroke-width="7"/>{dots}{_text(label,150,y+175,22,700,"start",MUTED)}'
    if family == "performance":
        return f'<path d="M120 {y+155} H960" stroke="{LINE}" stroke-width="10"/><path d="M120 {y+155} L300 {y+140} L470 {y+105} L650 {y+45} L820 {y+10} L960 {y-45}" fill="none" stroke="{ACCENT}" stroke-width="10"/>{_text("PERFORMANCE RESPONSE",120,y+220,22,700,"start",MUTED)}'
    if family == "comparison":
        return f'<path d="M120 {y+120} H960 M120 {y+210} H960" stroke="{LINE}" stroke-width="5"/><path d="M140 {y+120} H720 M140 {y+210} H820" stroke="{ACCENT}" stroke-width="18" stroke-linecap="round"/>{_text("POSITION / CLASS",120,y+275,22,700,"start",MUTED)}'
    return f'<path d="M140 {y+150} Q340 {y+25} 520 {y+130} T940 {y+95}" fill="none" stroke="{ACCENT}" stroke-width="8"/><circle cx="520" cy="{y+130}" r="13" fill="{ACCENT}"/>{_text("DESIGN DETAIL",140,y+220,22,700,"start",MUTED)}'


def vertical_scene_svg(scene, topic: str, out: Path) -> None:
    family = _family(scene, _kind(scene)); kind = _kind(scene); motion = ["push_in","pull_out","orbit_left","orbit_right","rack_focus","tracking","rise"][(int(scene.id)+len(family)) % 7]
    intent = str(scene.visual_intent).strip(); calls = [str(c).strip() for c in scene.callouts if str(c).strip()]
    # Native 9:16 composition: subject occupies the middle 46% of the frame, captions get a dedicated lower band.
    if family in {"front_close", "rear_close"}: car = _car("translate(-270 220) scale(.92)")
    elif family == "wide_scene": car = _car("translate(-120 360) scale(.70)")
    elif family == "low_angle": car = _car("translate(-230 400) scale(.78)")
    elif family == "three_quarter_high": car = _car("translate(-180 240) scale(.76)")
    else: car = _car("translate(-170 300) scale(.80)")
    overlay = _focus_art(family, scene, 1080)
    cards = ''.join(_card(c, 1300 + i*108, 920, 80) for i, c in enumerate(calls[:2]))
    topic_x = 1000 if _has_arabic(topic) else 70
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
      data-visual-family="{family}" data-visual-mode="{kind}" data-layout="{html.escape(str(scene.layout))}"
      data-camera-angle="vertical_{family}" data-visual-intent="{html.escape(intent[:240])}" data-motion="{motion}"
      data-car-layer="primary" data-asset-quality="premium_automotive_vertical_v4">
      {_defs()}<rect width="1080" height="1920" fill="#07090C"/><rect width="1080" height="1500" fill="url(#bg)"/>
      <ellipse cx="540" cy="760" rx="510" ry="520" fill="url(#halo)"/>
      <path d="M50 115 H1030" stroke="{ACCENT}" stroke-width="4"/>{_text(topic,topic_x,82,30,700,"start",TEXT)}
      {car}<path d="M70 1030 H1010" stroke="#25303A" stroke-width="3"/>{overlay}{cards}
      {_text(kind.upper(),540,1780,21,700,"middle",MUTED)}
    </svg>'''
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(svg, encoding="utf-8")


def generate_vertical_visuals(story: Story, out_dir: Path = RUN / "vertical_scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        vertical_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
