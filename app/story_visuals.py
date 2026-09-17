from __future__ import annotations

import html
import re
from pathlib import Path

from .core import RUN, Story

W, H = 1920, 1080
TEXT = "#F4F6F8"; MUTED = "#9FA9B4"; ACCENT = "#E8B44A"; PANEL = "#0B1016"; LINE = "#2B3540"


def _has_arabic(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value)))


def _safe(value: str, limit: int = 120) -> str:
    return html.escape(str(value)[:limit])


def _text(value, x, y, size=28, weight=600, anchor="start", fill=TEXT) -> str:
    value = _safe(value, 150)
    rtl = ' direction="rtl" unicode-bidi="plaintext"' if _has_arabic(value) else ""
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'


def _kind(scene) -> str:
    text = (str(scene.narration) + " " + str(scene.visual_intent) + " " + " ".join(map(str, scene.callouts))).casefold()
    groups = {
        "interior": ["interior", "cabin", "seat", "dashboard", "screen", "مقصورة", "داخلية", "مقاعد", "شاشة", "تابلوه"],
        "safety": ["safety", "brake", "airbag", "collision", "أمان", "فرامل", "وسادة", "تصادم"],
        "charging": ["charging", "charge", "شحن", "الشحن"],
        "efficiency": ["range", "efficiency", "consumption", "battery", "electric", "مدى", "كفاءة", "استهلاك", "بطارية", "كهربائية"],
        "technology": ["technology", "tech", "software", "sensor", "camera", "assist", "تقنية", "تقنيات", "حساس", "كاميرا", "مساعدة"],
        "design": ["design", "exterior", "body", "style", "aerodynamic", "تصميم", "هيكل", "شكل", "خارجية", "ديناميكية"],
        "performance": ["performance", "power", "horsepower", "torque", "acceleration", "speed", "أداء", "قوة", "حصان", "عزم", "تسارع", "سرعة"],
        "price": ["price", "cost", "value", "سعر", "تكلفة", "قيمة"],
    }
    for name, words in groups.items():
        if any(w in text for w in words):
            return name
    return "hero"


def _family(scene, kind: str) -> str:
    layout = str(scene.layout).casefold()
    presets = {
        "hero": ["front_3q", "rear_3q", "wide_scene", "three_quarter_high"],
        "technical": ["technology", "low_angle", "aero", "wheel_detail", "battery", "safety"],
        "spec": ["front_close", "rear_close", "wheel_detail", "battery", "design_detail", "technology"],
        "comparison": ["comparison", "wide_scene", "front_3q", "rear_3q"],
        "diagram": ["technology", "performance", "battery", "charging", "safety"],
        "timeline": ["wide_scene", "low_angle", "performance", "rear_3q"],
    }
    options = presets.get(layout, presets["hero"])
    return options[(int(scene.id) - 1) % len(options)]


def _motion(family: str, scene_id: int) -> str:
    motions = ["push_in", "pull_out", "orbit_left", "orbit_right", "rack_focus", "tracking", "rise"]
    return motions[(scene_id + len(family)) % len(motions)]


def _defs() -> str:
    return '''<defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#18212B"/><stop offset=".46" stop-color="#080B10"/><stop offset="1" stop-color="#1B1309"/></linearGradient>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FBFCFD"/><stop offset=".20" stop-color="#D6DDE3"/><stop offset=".43" stop-color="#65727E"/><stop offset=".72" stop-color="#26313A"/><stop offset="1" stop-color="#0B1015"/></linearGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5D7588"/><stop offset=".42" stop-color="#111D27"/><stop offset="1" stop-color="#050A0F"/></linearGradient>
    <radialGradient id="halo"><stop offset="0" stop-color="#F1C86E" stop-opacity=".30"/><stop offset="1" stop-color="#F1C86E" stop-opacity="0"/></radialGradient>
    <linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1D2630"/><stop offset="1" stop-color="#030405"/></linearGradient>
    <filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter>
    <filter id="soft"><feGaussianBlur stdDeviation="8"/></filter>
  </defs>'''


def _environment(scene_id: int, wide: bool = False) -> str:
    van = 160 + (scene_id % 4) * 80
    return f'''<rect width="1920" height="1080" fill="url(#bg)"/>
    <ellipse cx="{960 + (scene_id % 3) * 70}" cy="550" rx="860" ry="430" fill="url(#halo)"/>
    <path d="M0 840 Q420 690 920 790 T1920 730 V1080 H0 Z" fill="url(#road)"/>
    <path d="M0 900 Q480 760 960 850 T1920 790" fill="none" stroke="#2F3944" stroke-width="4"/>
    <g opacity=".20">{''.join(f'<path d="M{x} 155 L{x-140} 830" stroke="#70808C" stroke-width="2"/>' for x in range(120, 1900, van))}</g>'''


def _wheel(cx, cy, r=110) -> str:
    return f'''<g><circle cx="{cx}" cy="{cy}" r="{r}" fill="#050709" stroke="#D6DEE4" stroke-width="10"/>
    <circle cx="{cx}" cy="{cy}" r="{r-26}" fill="#8C98A3"/><circle cx="{cx}" cy="{cy}" r="{r-45}" fill="#11171D" stroke="#53606B" stroke-width="5"/>
    <circle cx="{cx}" cy="{cy}" r="17" fill="{ACCENT}"/>{''.join(f'<path d="M{cx} {cy-r+34} L{cx} {cy+r-34}" stroke="#B7C1C8" stroke-width="4" transform="rotate({a} {cx} {cy})"/>' for a in (0, 60, 120))}</g>'''


def _car(transform: str = "", wheel_scale: float = 1.0) -> str:
    return f'''<g transform="{transform}" data-car-style="premium_automotive_vector_v4" data-car-layer="primary">
      <ellipse cx="760" cy="640" rx="670" ry="68" fill="#000" opacity=".75" filter="url(#shadow)"/>
      <path d="M80 525 Q118 430 295 386 L488 315 Q620 258 796 274 L966 296 Q1088 312 1204 382 L1395 482 Q1450 514 1460 555 L1415 607 L1130 620 L340 632 L122 598 L72 557 Z" fill="url(#body)" stroke="#F7F8FA" stroke-width="6"/>
      <path d="M302 385 L490 220 Q575 155 717 160 L882 180 Q1014 196 1136 322 L1182 388 L930 402 L520 404 Z" fill="url(#glass)" stroke="#B8C6D0" stroke-width="5"/>
      <path d="M505 225 L535 400 M865 184 L930 400" stroke="#C0CBD3" stroke-width="4" opacity=".75"/>
      <path d="M116 500 Q365 405 610 420 Q916 421 1210 448 L1405 518" fill="none" stroke="#FFFFFF" stroke-opacity=".52" stroke-width="9"/>
      <path d="M145 532 Q395 474 645 480 L1145 485 Q1305 490 1418 529" fill="none" stroke="{ACCENT}" stroke-opacity=".90" stroke-width="5"/>
      <path d="M1185 400 L1378 488 L1450 532 L1398 560 L1268 536 L1140 470 Z" fill="#141B22"/>
      <path d="M1310 490 L1440 528 L1402 554 L1317 542 Z" fill="#C9342E"/>
      <path d="M110 536 L276 512 L305 568 L136 578 Z" fill="#202A34"/>
      <path d="M220 585 Q660 621 1272 568" fill="none" stroke="#070A0D" stroke-width="14"/>
      <path d="M435 356 Q692 326 1038 358" fill="none" stroke="#FFFFFF" stroke-opacity=".16" stroke-width="11"/>
      <path d="M1025 427 Q1085 408 1145 430 L1195 459" fill="none" stroke="#FFFFFF" stroke-opacity=".5" stroke-width="6"/>
      {_wheel(350, 584, int(110*wheel_scale))}{_wheel(1120, 566, int(110*wheel_scale))}
    </g>'''


def _callout_cards(calls, x=1380, y=220, width=460):
    out=[]
    for i, call in enumerate(calls[:3]):
        yy=y+i*126; out.append(f'<rect x="{x}" y="{yy}" width="{width}" height="92" rx="18" fill="{PANEL}" fill-opacity=".94" stroke="#3A4652"/>')
        out.append(_text(call, x+26, yy+57, 24, 650, "start", TEXT)); out.append(f'<circle cx="{x+width-32}" cy="{yy+46}" r="7" fill="{ACCENT}"/>')
    return ''.join(out)


def _focus(family: str, scene) -> str:
    calls=[str(c) for c in scene.callouts if str(c).strip()]
    if family == "wheel_detail":
        return f'''<g transform="translate(1040 165)"><circle cx="430" cy="405" r="250" fill="#050709" stroke="#E0E6EA" stroke-width="12"/>{_wheel(430,405,190)}<path d="M160 730 Q420 560 700 720" fill="none" stroke="{ACCENT}" stroke-width="7"/><text x="160" y="790" font-family="Noto Sans" font-size="20" fill="{MUTED}">WHEEL / BRAKE DETAIL</text></g>'''
    if family in {"technology", "battery", "charging", "safety"}:
        labels = {"technology":"SYSTEM ARCHITECTURE", "battery":"BATTERY / ENERGY", "charging":"CHARGING FLOW", "safety":"SAFETY COVERAGE"}
        dots=''.join(f'<circle cx="{1450+i*120}" cy="720" r="18" fill="{ACCENT}"/>' for i in range(4))
        return f'''<g><path d="M1375 720 H1815" stroke="{LINE}" stroke-width="6"/>{dots}{_text(labels[family],1375,790,20,700,"start",MUTED)}
        <path d="M1435 665 L1530 610 L1640 650 L1740 570 L1810 595" fill="none" stroke="{ACCENT}" stroke-width="7"/>{_callout_cards(calls,1380,205,450)}</g>'''
    if family == "performance":
        return f'''<g><path d="M1380 760 H1810" stroke="{LINE}" stroke-width="10"/><path d="M1380 760 L1510 735 L1615 680 L1715 615 L1810 590" fill="none" stroke="{ACCENT}" stroke-width="9"/>{_text("PERFORMANCE CURVE",1380,820,20,700,"start",MUTED)}{_callout_cards(calls,1370,210,455)}</g>'''
    if family == "comparison":
        return f'''<g><rect x="1365" y="220" width="470" height="535" rx="24" fill="{PANEL}" fill-opacity=".92" stroke="#3A4652"/>{_text("POSITION IN CLASS",1400,270,19,700,"start",MUTED)}
        <path d="M1420 350 H1780 M1420 480 H1780 M1420 610 H1780" stroke="#3A4652" stroke-width="3"/>
        <path d="M1420 350 H1660 M1420 480 H1710 M1420 610 H1600" stroke="{ACCENT}" stroke-width="14" stroke-linecap="round"/></g>'''
    if family in {"front_close", "rear_close", "design_detail", "aero"}:
        return f'''<g><path d="M1380 790 Q1540 650 1810 720" fill="none" stroke="{ACCENT}" stroke-width="7"/><circle cx="1590" cy="700" r="13" fill="{ACCENT}"/>{_text("DESIGN DETAIL",1380,845,20,700,"start",MUTED)}{_callout_cards(calls,1370,200,455)}</g>'''
    return _callout_cards(calls)


def render_scene_svg(scene, topic: str, out: Path) -> None:
    family = _family(scene, _kind(scene)); kind = _kind(scene); camera = family
    motion = _motion(family, int(scene.id)); intent = str(scene.visual_intent).strip(); calls=[str(c).strip() for c in scene.callouts if str(c).strip()]
    if family == "front_close": car = _car('translate(-100 75) scale(1.18)'); env = _environment(scene.id)
    elif family == "rear_close": car = _car('translate(1030 90) scale(1.18)') ; env = _environment(scene.id)
    elif family == "low_angle": car = _car('translate(-40 260) scale(1.02)'); env = _environment(scene.id)
    elif family == "wide_scene": car = _car('translate(180 330) scale(.74)'); env = _environment(scene.id, True)
    elif family == "three_quarter_high": car = _car('translate(120 85) scale(.85)'); env = _environment(scene.id)
    elif family in {"interior"}: car = _car('translate(50 250) scale(.62)'); env = _environment(scene.id)
    else: car = _car('translate(40 205) scale(.94)'); env = _environment(scene.id)
    if family == "interior":
        focus = '''<g transform="translate(1090 210)"><rect x="0" y="0" width="650" height="490" rx="28" fill="#10171E" stroke="#46515B" stroke-width="4"/><path d="M80 390 L150 240 L330 260 L420 135 L600 210 L570 385 Z" fill="#202A34" stroke="#B9C4CC" stroke-width="5"/><rect x="185" y="120" width="260" height="100" rx="18" fill="#060A0F" stroke="{ACCENT}" stroke-width="5"/><circle cx="500" cy="330" r="95" fill="#0A0D11" stroke="#87939C" stroke-width="10"/><circle cx="500" cy="330" r="64" fill="#1D252D" stroke="{ACCENT}" stroke-width="5"/><text x="75" y="450" font-family="Noto Sans" font-size="20" fill="{MUTED}">CABIN / DRIVER INTERFACE</text></g>{_callout_cards(calls,1370,730,455)}'''
    else: focus = _focus(family, scene)
    topic_x = 1810 if _has_arabic(topic) else 70
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
      data-visual-family="{family}" data-visual-mode="{kind}" data-layout="{_safe(scene.layout,40)}" data-camera-angle="{camera}"
      data-visual-intent="{_safe(intent,240)}" data-motion="{motion}" data-car-layer="primary" data-asset-quality="premium_automotive_editorial_v4">
      {_defs()}{env}<path d="M70 105 H1850" stroke="{ACCENT}" stroke-width="3" opacity=".75"/>
      {_text(topic,topic_x,75,28,700,"start",TEXT)}{car}{focus}
      {_text(kind.upper(),70,985,18,700,"start",MUTED)}
    </svg>'''
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
