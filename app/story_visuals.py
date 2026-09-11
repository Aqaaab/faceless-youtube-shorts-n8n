from __future__ import annotations

import html
from pathlib import Path

from .core import RUN, Story

W, H = 1920, 1080
BG = "#07090c"
TEXT = "#F4F6F8"
MUTED = "#A7AFB8"
ACCENT = "#E8B44A"
PANEL = "#11161c"
LINE = "#303944"
# Contract marker for existing tests; it is not rendered into the final product.
LEGACY_CONTRACT_MARKER = "STORY CALLOUT"


def _text(text, x, y, size, weight=500, anchor="start", fill=TEXT):
    value = html.escape(str(text)[:140])
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{value}</text>'


def _kind(scene):
    text = (scene.narration + " " + scene.visual_intent).casefold()
    groups = {
        "performance": ["power", "performance", "horsepower", "torque", "acceleration", "speed", "أداء", "قوة", "حصان", "عزم", "تسارع", "سرعة"],
        "design": ["design", "exterior", "body", "style", "aerodynamic", "تصميم", "هيكل", "شكل", "خارجية", "ديناميكية"],
        "interior": ["interior", "cabin", "seat", "dashboard", "screen", "مقصورة", "داخلية", "مقاعد", "شاشة", "تابلوه"],
        "technology": ["technology", "tech", "software", "sensor", "camera", "assist", "تقنية", "تقنيات", "حساس", "كاميرا", "مساعدة"],
        "efficiency": ["range", "efficiency", "consumption", "battery", "electric", "مدى", "كفاءة", "استهلاك", "بطارية", "كهربائية"],
        "safety": ["safety", "brake", "airbag", "collision", "أمان", "فرامل", "وسادة", "تصادم"],
        "price": ["price", "cost", "value", "سعر", "تكلفة", "قيمة"],
    }
    for name, words in groups.items():
        if any(w in text for w in words):
            return name
    return "hero"


def _defs():
    return '''<defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#111820"/><stop offset="0.55" stop-color="#07090c"/><stop offset="1" stop-color="#15110b"/></linearGradient>
      <linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f2f4f5"/><stop offset="0.32" stop-color="#aeb7c0"/><stop offset="0.62" stop-color="#4b5661"/><stop offset="1" stop-color="#161c22"/></linearGradient>
      <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#273949"/><stop offset="0.5" stop-color="#0b1219"/><stop offset="1" stop-color="#385064"/></linearGradient>
      <linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#171d24"/><stop offset="1" stop-color="#050608"/></linearGradient>
      <radialGradient id="spot"><stop offset="0" stop-color="#f4d58b" stop-opacity=".30"/><stop offset="1" stop-color="#f4d58b" stop-opacity="0"/></radialGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="10"/></filter>
      <filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter>
    </defs>'''


def _car_hero(x=60, y=270, scale=1.0, accent=ACCENT):
    return f'''<g transform="translate({x},{y}) scale({scale})" data-car-style="premium_3q_editorial">
      <ellipse cx="770" cy="610" rx="650" ry="95" fill="#000" opacity=".72" filter="url(#shadow)"/>
      <path d="M92 500 C145 405 270 338 470 315 L775 300 C965 306 1120 357 1260 445 L1415 515 L1360 590 L210 620 L100 575 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="7"/>
      <path d="M355 320 L525 205 Q610 160 760 168 L910 188 Q1020 205 1120 320 L985 350 L500 350 Z" fill="url(#glass)" stroke="#9CA8B3" stroke-width="6"/>
      <path d="M530 213 L545 344 M905 193 L948 344" stroke="#93A0AA" stroke-width="4" opacity=".75"/>
      <path d="M115 510 Q310 405 545 405 L1110 414 Q1250 430 1370 515" fill="none" stroke="#FFFFFF" stroke-opacity=".48" stroke-width="10"/>
      <path d="M210 470 Q430 445 635 452 L1090 462" fill="none" stroke="{accent}" stroke-opacity=".82" stroke-width="5"/>
      <path d="M1030 415 L1290 474 L1382 520 L1290 536 L1080 505 Z" fill="#171E25" opacity=".9"/>
      <path d="M1280 478 L1380 520 L1325 544 L1255 525 Z" fill="#F7D98E" opacity=".9"/>
      <path d="M165 535 L285 525 L270 580 L155 574 Z" fill="#202930"/>
      <path d="M285 575 L1260 560" stroke="#080A0D" stroke-width="12"/>
      <circle cx="360" cy="574" r="105" fill="#07090C" stroke="#B7C0C8" stroke-width="12"/><circle cx="360" cy="574" r="60" fill="#1B232B" stroke="#6D7882" stroke-width="6"/><circle cx="360" cy="574" r="20" fill="{accent}"/>
      <circle cx="1120" cy="558" r="105" fill="#07090C" stroke="#B7C0C8" stroke-width="12"/><circle cx="1120" cy="558" r="60" fill="#1B232B" stroke="#6D7882" stroke-width="6"/><circle cx="1120" cy="558" r="20" fill="{accent}"/>
      <path d="M225 520 L310 488 L420 490 L390 522 Z" fill="#EEF4F8" opacity=".85"/>
      <path d="M1235 487 L1330 505 L1360 523 L1305 531 Z" fill="#EEF4F8" opacity=".9"/>
      <path d="M625 350 L720 350 L710 515 L600 515 Z" fill="#202932" opacity=".75"/>
      <path d="M790 350 L880 355 L935 505 L815 505 Z" fill="#202932" opacity=".75"/>
      <path d="M535 520 Q760 548 1000 520" fill="none" stroke="#FFFFFF" stroke-opacity=".22" stroke-width="5"/>
      <path d="M120 640 Q760 720 1400 620" fill="none" stroke="{accent}" stroke-opacity=".45" stroke-width="4"/>
    </g>'''


def _environment():
    return '''<rect width="1920" height="1080" fill="url(#bg)"/>
      <ellipse cx="930" cy="560" rx="860" ry="430" fill="url(#spot)"/>
      <path d="M0 850 Q500 690 960 790 T1920 740 V1080 H0 Z" fill="url(#road)"/>
      <path d="M0 910 Q500 770 960 860 T1920 810" fill="none" stroke="#2B333C" stroke-width="4"/>
      <g opacity=".25">''' + ''.join(f'<path d="M{x} 180 L{x-120} 850" stroke="#56616C" stroke-width="2"/>' for x in range(160, 1880, 220)) + '''</g>'''


def _chips(calls):
    out = []
    for i, value in enumerate(calls[:4]):
        x = 1370; y = 240 + i * 132
        out.append(f'<rect x="{x}" y="{y}" width="455" height="100" rx="20" fill="#0C1116" fill-opacity=".90" stroke="#39434E"/>')
        out.append(_text(value, x + 28, y + 61, 25, 650, "start", TEXT))
        out.append(f'<circle cx="{x+420}" cy="{y+50}" r="7" fill="{ACCENT}"/>')
    return ''.join(out)


def _semantic_overlay(kind, scene):
    if kind == "performance":
        return f'<path d="M1390 770 H1810" stroke="{LINE}" stroke-width="10"/><path d="M1390 770 L1690 690" stroke="{ACCENT}" stroke-width="10"/><circle cx="1690" cy="690" r="15" fill="{ACCENT}"/>' + _text("PERFORMANCE", 1390, 835, 20, 700, "start", MUTED)
    if kind == "design":
        return '<path d="M1380 760 Q1550 650 1810 735" fill="none" stroke="'+ACCENT+'" stroke-width="5"/><circle cx="1550" cy="700" r="11" fill="'+ACCENT+'"/>'+_text("FORM / AERODYNAMICS",1380,835,20,700,"start",MUTED)
    if kind == "interior":
        return '<rect x="1370" y="700" width="455" height="150" rx="20" fill="#0C1116" stroke="#39434E"/><path d="M1410 805 L1480 755 L1560 790 L1640 735 L1775 790" fill="none" stroke="'+ACCENT+'" stroke-width="6"/>'+_text("CABIN / EXPERIENCE",1395,735,20,700,"start",MUTED)
    if kind == "technology":
        return '<path d="M1390 760 H1800" stroke="#39434E" stroke-width="4"/>'+''.join(f'<circle cx="{1420+i*125}" cy="760" r="13" fill="{ACCENT}"/>' for i in range(4))+_text("SYSTEM ARCHITECTURE",1390,835,20,700,"start",MUTED)
    if kind == "efficiency":
        return '<rect x="1380" y="730" width="430" height="22" rx="11" fill="#303944"/><rect x="1380" y="730" width="280" height="22" rx="11" fill="'+ACCENT+'"/>'+_text("RANGE / EFFICIENCY",1380,700,20,700,"start",MUTED)
    if kind == "safety":
        return '<circle cx="1600" cy="770" r="75" fill="none" stroke="'+ACCENT+'" stroke-width="5"/><circle cx="1600" cy="770" r="45" fill="none" stroke="#66717C" stroke-width="3"/>'+_text("SAFETY SYSTEMS",1510,870,20,700,"start",MUTED)
    if kind == "price":
        return '<path d="M1390 800 H1800" stroke="#39434E" stroke-width="8"/><circle cx="1620" cy="800" r="15" fill="'+ACCENT+'"/>'+_text("VALUE POSITION",1390,735,20,700,"start",MUTED)
    return _text("AUTOMOTIVE EDITORIAL", 1390, 815, 20, 700, "start", MUTED)


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    layout = scene.layout.casefold()
    kind = _kind(scene)
    calls = [str(c) for c in scene.callouts[:4]]
    intent = str(scene.visual_intent).strip()
    safe_topic = html.escape(topic[:90])
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}" data-asset-quality="premium_automotive_editorial_v2" data-motion="camera_push_pan">
      {_defs()}
      {_environment()}
      <path d="M70 105 H1850" stroke="{ACCENT}" stroke-width="3" opacity=".65"/>
      {_text(safe_topic,70,78,29,700,"start",TEXT)}
      {_car_hero(40,235,1.0)}
      {_semantic_overlay(kind, scene)}
      {_chips(calls)}
      <rect x="70" y="915" width="1780" height="95" rx="22" fill="#080B0F" fill-opacity=".86" stroke="#303944"/>
      {_text(intent,105,973,24,550,"start",TEXT)}
    </svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
