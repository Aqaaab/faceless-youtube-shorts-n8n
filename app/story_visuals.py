from __future__ import annotations

import html
import re
from pathlib import Path

from .core import RUN, Story

W, H = 1920, 1080
TEXT = "#F4F6F8"
MUTED = "#A7AFB8"
ACCENT = "#E8B44A"
LINE = "#303944"


def _has_arabic(value):
    return bool(re.search(r"[\u0600-\u06ff]", str(value)))


def _text(text, x, y, size, weight=500, anchor="start", fill=TEXT):
    value = html.escape(str(text)[:140])
    rtl = ' direction="rtl" unicode-bidi="plaintext"' if _has_arabic(value) else ""
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'


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
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#151D26"/><stop offset=".5" stop-color="#080B10"/><stop offset="1" stop-color="#17120B"/></linearGradient>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FCFDFD"/><stop offset=".2" stop-color="#D7DDE2"/><stop offset=".48" stop-color="#697681"/><stop offset=".75" stop-color="#29333D"/><stop offset="1" stop-color="#0D1217"/></linearGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#435A6A"/><stop offset=".45" stop-color="#101A24"/><stop offset=".75" stop-color="#071017"/><stop offset="1" stop-color="#506B7A"/></linearGradient>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F4F6F7"/><stop offset=".5" stop-color="#89939C"/><stop offset="1" stop-color="#252D35"/></linearGradient>
    <linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1A222A"/><stop offset="1" stop-color="#040507"/></linearGradient>
    <radialGradient id="spot"><stop offset="0" stop-color="#F4D58B" stop-opacity=".34"/><stop offset="1" stop-color="#F4D58B" stop-opacity="0"/></radialGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="9"/></filter><filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter>
    </defs>'''


def _car_hero(x=0, y=0, scale=1.0, accent=ACCENT):
    return f'''<g transform="translate({x},{y}) scale({scale})" data-car-style="premium_automotive_editorial"><ellipse cx="760" cy="615" rx="680" ry="86" fill="#000" opacity=".78" filter="url(#shadow)"/><path d="M75 505 Q125 418 290 375 L485 318 Q620 270 790 275 L950 294 Q1080 310 1195 380 L1390 478 Q1450 508 1460 552 L1415 600 L1130 616 L335 628 L125 592 L72 552 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="6"/><path d="M300 374 L485 222 Q565 162 710 165 L875 182 Q1015 198 1128 319 L1178 385 L930 400 L520 402 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="5"/><path d="M505 226 L532 398 M865 185 L930 397" stroke="#B7C5CE" stroke-width="4" opacity=".72"/><path d="M112 498 Q330 412 590 420 Q920 420 1220 448 L1408 514" fill="none" stroke="#FFFFFF" stroke-opacity=".58" stroke-width="9"/><path d="M150 520 Q390 468 650 478 L1150 484 Q1300 488 1415 528" fill="none" stroke="{accent}" stroke-opacity=".92" stroke-width="5"/><path d="M1180 395 L1378 482 L1450 528 L1395 558 L1265 535 L1140 468 Z" fill="#151C23"/><path d="M1310 486 L1438 526 L1400 551 L1315 540 Z" fill="#B92B26"/><g><circle cx="350" cy="578" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="350" cy="578" r="76" fill="url(#rim)"/><circle cx="350" cy="578" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="350" cy="578" r="19" fill="{accent}"/></g><g><circle cx="1120" cy="560" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="1120" cy="560" r="76" fill="url(#rim)"/><circle cx="1120" cy="560" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="1120" cy="560" r="19" fill="{accent}"/></g></g>'''


def _background(family: str):
    base = '<rect width="1920" height="1080" fill="url(#bg)"/>'
    if family in {"battery", "charging"}:
        return base + '<path d="M0 820 H1920" stroke="#26333C" stroke-width="6"/><path d="M160 820 V300 M1760 820 V300" stroke="#26333C" stroke-width="3" opacity=".55"/><g opacity=".18">' + ''.join(f'<circle cx="{x}" cy="{y}" r="5" fill="#E8B44A"/>' for x,y in [(300,500),(520,620),(760,420),(1020,560),(1320,380),(1540,620)]) + '</g>'
    if family == "performance":
        return base + '<path d="M0 850 Q500 700 960 800 T1920 730 V1080 H0Z" fill="url(#road)"/><g opacity=".3">' + ''.join(f'<path d="M{x} 1000 L{x+260} 740" stroke="#68737D" stroke-width="5"/>' for x in range(-200,1900,260)) + '</g>'
    if family == "interior":
        return '<rect width="1920" height="1080" fill="#06090D"/><rect x="70" y="90" width="1780" height="900" rx="55" fill="#111922" stroke="#39434E" stroke-width="5"/><path d="M180 760 Q420 420 720 700 T1200 680 T1740 500" fill="none" stroke="#586673" stroke-width="70" opacity=".45"/>'
    if family == "aero":
        return base + '<g opacity=".25">' + ''.join(f'<path d="M80 {y} C500 {y-100} 1350 {y+100} 1840 {y-40}" fill="none" stroke="#71808C" stroke-width="3"/>' for y in range(220,900,110)) + '</g>'
    if family == "safety":
        return base + '<g opacity=".28">' + ''.join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#64717C" stroke-width="3"/>' for x,y,r in [(240,260,130),(960,250,180),(1630,350,150),(420,820,180),(1400,780,220)]) + '</g>'
    return base + '<ellipse cx="960" cy="590" rx="900" ry="430" fill="url(#spot)"/><path d="M0 860 Q500 700 960 800 T1920 760 V1080 H0Z" fill="url(#road)"/>'


def _family(scene):
    text = (scene.narration + " " + scene.visual_intent).casefold()
    if any(x in text for x in ["بطارية", "battery", "خلية"]): return "battery"
    if any(x in text for x in ["800v", "شحن", "charging", "charger"]): return "charging"
    if any(x in text for x in ["مقصورة", "داخلية", "dashboard", "cockpit", "تابلوه"]): return "interior"
    if any(x in text for x in ["عجلة", "عجلات", "wheel", "rim"]): return "wheel_detail"
    if any(x in text for x in ["ديناميكية", "aero", "aerodynamic"]): return "aero"
    if any(x in text for x in ["أداء", "تسارع", "سرعة", "قوة", "حصان", "عزم", "performance"]): return "performance"
    if any(x in text for x in ["أمان", "فرامل", "تصادم", "safety"]): return "safety"
    if any(x in text for x in ["تصميم", "هيكل", "واجهة", "design"]): return "design_detail"
    if any(x in text for x in ["تقنية", "حساس", "كاميرا", "software"]): return "technology"
    return ["front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene"][((int(scene.id)-1) % 5)]


def _special_visual(family: str, scene):
    if family == "battery":
        cells = ''.join(f'<rect x="{780+(i%5)*125}" y="{430+(i//5)*115}" width="90" height="78" rx="12" fill="#18222A" stroke="{ACCENT}" stroke-width="3"/>' for i in range(15))
        return f'<rect x="650" y="300" width="1080" height="520" rx="40" fill="#0B1117" stroke="#45525D" stroke-width="5"/><text x="1180" y="365" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">BATTERY PACK ARCHITECTURE</text>{cells}<path d="M700 865 H1710" stroke="{ACCENT}" stroke-width="8"/>'
    if family == "charging":
        return f'<rect x="650" y="270" width="1080" height="560" rx="40" fill="#0B1117" stroke="#45525D" stroke-width="5"/><path d="M930 720 V440 H1190 L1110 555 H1320 L1050 850 V625 H850Z" fill="{ACCENT}" opacity=".9"/><path d="M1410 430 C1510 520 1510 650 1410 730" fill="none" stroke="#9AA7B2" stroke-width="12"/><circle cx="1410" cy="430" r="18" fill="{ACCENT}"/><text x="1190" y="360" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">800V FAST-CHARGING FLOW</text>'
    if family == "interior":
        return f'<path d="M240 720 Q360 420 650 420 H1260 Q1550 420 1690 720 L1540 820 H380Z" fill="#202A33" stroke="#74818C" stroke-width="5"/><rect x="650" y="475" width="620" height="210" rx="24" fill="#071017" stroke="{ACCENT}" stroke-width="5"/><path d="M700 625 H1220 M790 550 H1120" stroke="#9AA7B2" stroke-width="6"/><circle cx="520" cy="720" r="105" fill="#10171D" stroke="#8996A0" stroke-width="10"/><circle cx="1400" cy="720" r="105" fill="#10171D" stroke="#8996A0" stroke-width="10"/><text x="960" y="330" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">COCKPIT / INTERIOR</text>'
    if family == "wheel_detail":
        return f'<circle cx="960" cy="550" r="310" fill="#070A0D" stroke="#AEB8C0" stroke-width="22"/><circle cx="960" cy="550" r="230" fill="#1A2229" stroke="#56636E" stroke-width="8"/>{"".join(f"<path d=\\"M960 330 L960 770 M740 550 H1180 M805 395 L1115 705 M1115 395 L805 705\\" stroke=\\"{ACCENT}\\" stroke-width=\\"18\\"/>" for _ in [0])}<circle cx="960" cy="550" r="60" fill="{ACCENT}"/><text x="960" y="930" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">WHEEL / BRAKE DETAIL</text>'
    if family == "aero":
        return f'<path d="M560 650 Q850 390 1440 500" fill="none" stroke="#D7DEE3" stroke-width="18"/><path d="M520 700 Q900 440 1510 560" fill="none" stroke="{ACCENT}" stroke-width="8"/>{"".join(f"<path d=\\"M{x} 760 L{x+260} 520\\" stroke=\\"#7D8993\\" stroke-width=\\"4\\"/>" for x in range(500,1500,180))}<text x="960" y="880" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">AERODYNAMIC AIRFLOW</text>'
    if family == "performance":
        return f'<path d="M260 790 C600 650 820 680 1080 520 S1560 390 1760 430" fill="none" stroke="{ACCENT}" stroke-width="10"/><circle cx="1760" cy="430" r="18" fill="{ACCENT}"/><text x="1000" y="340" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">PERFORMANCE / ACCELERATION</text>'
    if family == "safety":
        return f'<circle cx="960" cy="560" r="270" fill="none" stroke="{ACCENT}" stroke-width="9"/><path d="M960 300 L1210 400 V590 C1210 760 1090 850 960 910 C830 850 710 760 710 590 V400Z" fill="#101820" stroke="#8A969F" stroke-width="7"/><path d="M830 585 L925 680 L1100 480" fill="none" stroke="{ACCENT}" stroke-width="20"/>'
    if family == "technology":
        return f'<g>{"".join(f"<circle cx=\\"{650+i*155}\\" cy=\\"540\\" r=\\"42\\" fill=\\"#0B1117\\" stroke=\\"{ACCENT}\\" stroke-width=\\"6\\"/><path d=\\"M{650+i*155} 585 V700\\" stroke=\\"#697783\\" stroke-width=\\"4\\"/>" for i in range(5))}<path d="M650 540 H1270" stroke="#697783" stroke-width="5"/></g><text x="960" y="850" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">SENSOR / SOFTWARE NETWORK</text>'
    return ""


def _car_composition(family: str, scene_id: int):
    presets = {
        "front_3q": (-20, 205, .98, 1, "front_3q"), "rear_3q": (520, 190, .98, -1, "rear_3q"), "side_profile": (50, 235, .92, 1, "side_profile"),
        "low_angle": (-60, 280, 1.04, 1, "low_angle"), "wide_scene": (120, 310, .82, 1, "wide_scene"),
        "design_detail": (520, 170, .92, 1, "design_detail"), "technology": (20, 230, .88, 1, "technology"),
        "performance": (20, 250, .90, 1, "performance"), "safety": (40, 220, .90, 1, "safety"),
    }
    key = family if family in presets else ("side_profile" if scene_id % 2 else "front_3q")
    x,y,s,m,angle = presets[key]
    return angle, f'<g transform="translate({x},{y}) scale({m*s},{s})">{_car_hero()}</g>'


def _chips(calls):
    out=[]
    for i,value in enumerate(calls[:3]):
        x=1370; y=180+i*118
        out.append(f'<rect x="{x}" y="{y}" width="455" height="88" rx="18" fill="#0C1116" fill-opacity=".94" stroke="#39434E"/>')
        out.append(_text(value,x+24,y+55,23,650,"start",TEXT))
        out.append(f'<circle cx="{x+420}" cy="{y+44}" r="6" fill="{ACCENT}"/>')
    return ''.join(out)


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(scene); family = _family(scene); calls=[str(c) for c in scene.callouts[:3]]
    intent = str(scene.visual_intent).strip(); angle, car = _car_composition(family, int(scene.id))
    topic_x = 1810 if _has_arabic(topic) else 70
    special = _special_visual(family, scene)
    car_layer = "" if family in {"battery","charging","interior","wheel_detail","aero"} else car
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-visual-family="{html.escape(family)}" data-layout="{html.escape(str(scene.layout).casefold())}" data-camera-angle="{angle}" data-visual-intent="{html.escape(intent[:240])}" data-visual-focus="{html.escape(family)}" data-asset-quality="premium_automotive_editorial_v3" data-motion="camera_push_pan">{_defs()}{_background(family)}<path d="M70 105 H1850" stroke="{ACCENT}" stroke-width="3" opacity=".65"/>{_text(topic,topic_x,78,27,700,"start",TEXT)}{car_layer}{special}{_chips(calls)}<text x="70" y="1015" font-family="Noto Sans" font-size="18" font-weight="700" fill="{MUTED}" letter-spacing="3">{html.escape(family.upper())}</text></svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
