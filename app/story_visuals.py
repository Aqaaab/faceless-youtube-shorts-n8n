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
        if any(w in text for w in words): return name
    return "hero"


def _defs():
    return '''<defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#151D26"/><stop offset=".45" stop-color="#080B10"/><stop offset="1" stop-color="#17120B"/></linearGradient>
      <linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FCFDFD"/><stop offset=".18" stop-color="#D7DDE2"/><stop offset=".42" stop-color="#697681"/><stop offset=".72" stop-color="#29333D"/><stop offset="1" stop-color="#0D1217"/></linearGradient>
      <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#435A6A"/><stop offset=".38" stop-color="#101A24"/><stop offset=".72" stop-color="#071017"/><stop offset="1" stop-color="#506B7A"/></linearGradient>
      <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F4F6F7"/><stop offset=".45" stop-color="#89939C"/><stop offset="1" stop-color="#252D35"/></linearGradient>
      <linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1A222A"/><stop offset="1" stop-color="#040507"/></linearGradient>
      <radialGradient id="spot"><stop offset="0" stop-color="#F4D58B" stop-opacity=".34"/><stop offset="1" stop-color="#F4D58B" stop-opacity="0"/></radialGradient>
      <linearGradient id="redlight" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FF5B4D"/><stop offset="1" stop-color="#7E1614"/></linearGradient>
      <filter id="glow"><feGaussianBlur stdDeviation="9"/></filter><filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter>
    </defs>'''


def _car_hero(x=40, y=235, scale=1.0, accent=ACCENT):
    return f'''<g transform="translate({x},{y}) scale({scale})" data-car-style="premium_3q_editorial">
      <ellipse cx="760" cy="615" rx="680" ry="86" fill="#000" opacity=".78" filter="url(#shadow)"/>
      <ellipse cx="760" cy="595" rx="610" ry="34" fill="{accent}" opacity=".10" filter="url(#glow)"/>
      <path d="M75 505 Q125 418 290 375 L485 318 Q620 270 790 275 L950 294 Q1080 310 1195 380 L1390 478 Q1450 508 1460 552 L1415 600 L1130 616 L335 628 L125 592 L72 552 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="6"/>
      <path d="M300 374 L485 222 Q565 162 710 165 L875 182 Q1015 198 1128 319 L1178 385 L930 400 L520 402 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="5"/>
      <path d="M505 226 L532 398 M865 185 L930 397" stroke="#B7C5CE" stroke-width="4" opacity=".72"/>
      <path d="M112 498 Q330 412 590 420 Q920 420 1220 448 L1408 514" fill="none" stroke="#FFFFFF" stroke-opacity=".58" stroke-width="9"/>
      <path d="M150 520 Q390 468 650 478 L1150 484 Q1300 488 1415 528" fill="none" stroke="{accent}" stroke-opacity=".92" stroke-width="5"/>
      <path d="M1180 395 L1378 482 L1450 528 L1395 558 L1265 535 L1140 468 Z" fill="#151C23" opacity=".92"/>
      <path d="M1310 486 L1438 526 L1400 551 L1315 540 Z" fill="url(#redlight)"/>
      <path d="M106 530 L270 510 L300 563 L135 574 Z" fill="#202932"/>
      <path d="M220 575 Q650 610 1270 565" fill="none" stroke="#080A0D" stroke-width="14"/>
      <path d="M530 404 L645 404 L630 522 L505 522 Z" fill="#1A232B" opacity=".72"/><path d="M735 405 L845 405 L915 520 L785 520 Z" fill="#1A232B" opacity=".72"/>
      <path d="M420 355 Q680 325 1035 356" fill="none" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="10"/>
      <path d="M145 565 L420 570 M1040 560 L1280 548" stroke="#DCE3E8" stroke-opacity=".25" stroke-width="4"/>
      <g><circle cx="350" cy="578" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="350" cy="578" r="76" fill="url(#rim)"/><circle cx="350" cy="578" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="350" cy="578" r="19" fill="{accent}"/><path d="M350 532 L350 624 M304 578 L396 578" stroke="#AAB5BD" stroke-width="5"/></g>
      <g><circle cx="1120" cy="560" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="1120" cy="560" r="76" fill="url(#rim)"/><circle cx="1120" cy="560" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="1120" cy="560" r="19" fill="{accent}"/><path d="M1120 514 L1120 606 M1074 560 L1166 560" stroke="#AAB5BD" stroke-width="5"/></g>
      <path d="M1010 428 Q1080 410 1140 430 L1190 460" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="6"/>
      <path d="M90 632 Q730 716 1420 620" fill="none" stroke="{accent}" stroke-opacity=".38" stroke-width="4"/>
    </g>'''


def _environment():
    return '<rect width="1920" height="1080" fill="url(#bg)"/><ellipse cx="930" cy="560" rx="900" ry="450" fill="url(#spot)"/><path d="M0 850 Q500 690 960 790 T1920 740 V1080 H0 Z" fill="url(#road)"/><path d="M0 910 Q500 770 960 860 T1920 810" fill="none" stroke="#2B333C" stroke-width="4"/><g opacity=".24">' + ''.join(f'<path d="M{x} 180 L{x-120} 850" stroke="#56616C" stroke-width="2"/>' for x in range(160, 1880, 220)) + '</g>'


def _chips(calls):
    out=[]
    for i,value in enumerate(calls[:4]):
        x=1370; y=240+i*132
        out.append(f'<rect x="{x}" y="{y}" width="455" height="100" rx="20" fill="#0C1116" fill-opacity=".92" stroke="#39434E"/>')
        out.append(_text(value,x+28,y+61,25,650,"start",TEXT)); out.append(f'<circle cx="{x+420}" cy="{y+50}" r="7" fill="{ACCENT}"/>')
    return ''.join(out)


def _semantic_overlay(kind, scene):
    if kind=="performance": return f'<path d="M1390 770 H1810" stroke="{LINE}" stroke-width="10"/><path d="M1390 770 L1690 690" stroke="{ACCENT}" stroke-width="10"/><circle cx="1690" cy="690" r="15" fill="{ACCENT}"/>'+_text("PERFORMANCE / RESPONSE",1390,835,20,700,"start",MUTED)
    if kind=="design": return f'<path d="M1380 760 Q1550 650 1810 735" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1550" cy="700" r="11" fill="{ACCENT}"/>'+_text("FORM / AERODYNAMICS",1380,835,20,700,"start",MUTED)
    if kind=="interior": return f'<rect x="1370" y="700" width="455" height="150" rx="20" fill="#0C1116" stroke="#39434E"/><path d="M1410 805 L1480 755 L1560 790 L1640 735 L1775 790" fill="none" stroke="{ACCENT}" stroke-width="6"/>'+_text("CABIN / EXPERIENCE",1395,735,20,700,"start",MUTED)
    if kind=="technology": return '<path d="M1390 760 H1800" stroke="#39434E" stroke-width="4"/>'+''.join(f'<circle cx="{1420+i*125}" cy="760" r="13" fill="{ACCENT}"/>' for i in range(4))+_text("SYSTEM ARCHITECTURE",1390,835,20,700,"start",MUTED)
    if kind=="efficiency": return f'<rect x="1380" y="730" width="430" height="22" rx="11" fill="#303944"/><rect x="1380" y="730" width="280" height="22" rx="11" fill="{ACCENT}"/>'+_text("RANGE / EFFICIENCY",1380,700,20,700,"start",MUTED)
    if kind=="safety": return f'<circle cx="1600" cy="770" r="75" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1600" cy="770" r="45" fill="none" stroke="#66717C" stroke-width="3"/>'+_text("SAFETY SYSTEMS",1510,870,20,700,"start",MUTED)
    if kind=="price": return f'<path d="M1390 800 H1800" stroke="#39434E" stroke-width="8"/><circle cx="1620" cy="800" r="15" fill="{ACCENT}"/>'+_text("VALUE POSITION",1390,735,20,700,"start",MUTED)
    return _text("AUTOMOTIVE EDITORIAL",1390,815,20,700,"start",MUTED)


def _composition(scene_id: int):
    variants=[("hero_3q",40,235,1.0,1),("low_front",-10,285,1.06,1),("tight_detail",-115,205,1.18,1),("reverse_3q",1540,235,1.0,-1),("wide_hero",140,300,.92,1)]
    return variants[(scene_id-1)%len(variants)]


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True,exist_ok=True); layout=scene.layout.casefold(); kind=_kind(scene); calls=[str(c) for c in scene.callouts[:4]]; intent=str(scene.visual_intent).strip(); safe_topic=html.escape(topic[:90]); camera,x,y,scale,mirror=_composition(scene.id)
    car_transform=f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero(0,0,1.0)}</g>'
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}" data-camera-angle="{camera}" data-asset-quality="premium_automotive_editorial_v2" data-motion="camera_push_pan">
      {_defs()}{_environment()}<path d="M70 105 H1850" stroke="{ACCENT}" stroke-width="3" opacity=".65"/>{_text(safe_topic,70,78,29,700,"start",TEXT)}
      {car_transform}{_semantic_overlay(kind,scene)}{_chips(calls)}
      <rect x="70" y="915" width="1780" height="95" rx="22" fill="#080B0F" fill-opacity=".88" stroke="#303944"/>{_text(intent,105,973,24,550,"start",TEXT)}
    </svg>'''
    out.write_text(svg,encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True,exist_ok=True)
    for scene in story.scenes: render_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
