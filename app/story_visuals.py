from __future__ import annotations

import html
import re
from pathlib import Path

from .core import RUN, Story

W, H = 1920, 1080
TEXT = "#F4F6F8"
MUTED = "#A7AFB8"
ACCENT = "#E8B44A"


def _has_arabic(value):
    return bool(re.search(r"[\u0600-\u06ff]", str(value)))


def _text(text, x, y, size, weight=500, anchor="start", fill=TEXT):
    value = html.escape(str(text)[:140])
    rtl = ' direction="rtl" unicode-bidi="plaintext"' if _has_arabic(value) else ""
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'


def _kind(scene):
    text = (scene.narration + " " + scene.visual_intent).casefold()
    groups = {
        "performance": ["performance", "horsepower", "torque", "acceleration", "speed", "أداء", "قوة", "حصان", "عزم", "تسارع", "سرعة"],
        "design": ["design", "exterior", "body", "style", "aerodynamic", "تصميم", "هيكل", "شكل", "خارجية", "ديناميكية"],
        "interior": ["interior", "cabin", "dashboard", "screen", "مقصورة", "داخلية", "شاشة", "تابلوه"],
        "technology": ["technology", "software", "sensor", "camera", "تقنية", "حساس", "كاميرا"],
        "efficiency": ["range", "efficiency", "battery", "electric", "مدى", "كفاءة", "بطارية", "كهربائية"],
        "safety": ["safety", "brake", "airbag", "collision", "أمان", "فرامل", "تصادم"],
    }
    for name, words in groups.items():
        if any(w in text for w in words):
            return name
    return "hero"


def _defs():
    return '''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#151D26"/><stop offset=".5" stop-color="#080B10"/><stop offset="1" stop-color="#17120B"/></linearGradient><linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FCFDFD"/><stop offset=".25" stop-color="#D7DDE2"/><stop offset=".55" stop-color="#697681"/><stop offset="1" stop-color="#0D1217"/></linearGradient><linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#435A6A"/><stop offset=".5" stop-color="#101A24"/><stop offset="1" stop-color="#071017"/></linearGradient><linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1A222A"/><stop offset="1" stop-color="#040507"/></linearGradient><filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter></defs>'''


def _car_hero(scale=1.0, accent=ACCENT):
    return f'''<g transform="scale({scale})"><ellipse cx="760" cy="615" rx="680" ry="86" fill="#000" opacity=".78" filter="url(#shadow)"/><path d="M75 505 Q125 418 290 375 L485 318 Q620 270 790 275 L950 294 Q1080 310 1195 380 L1390 478 Q1450 508 1460 552 L1415 600 L1130 616 L335 628 L125 592 L72 552Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="6"/><path d="M300 374 L485 222 Q565 162 710 165 L875 182 Q1015 198 1128 319 L1178 385 L930 400 L520 402Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="5"/><path d="M112 498 Q330 412 590 420 Q920 420 1220 448 L1408 514" fill="none" stroke="#FFF" stroke-opacity=".58" stroke-width="9"/><path d="M150 520 Q390 468 650 478 L1150 484 Q1300 488 1415 528" fill="none" stroke="{accent}" stroke-width="5"/><circle cx="350" cy="578" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="350" cy="578" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="350" cy="578" r="19" fill="{accent}"/><circle cx="1120" cy="560" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="1120" cy="560" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="1120" cy="560" r="19" fill="{accent}"/></g>'''


def _background(family):
    base = '<rect width="1920" height="1080" fill="url(#bg)"/>'
    if family == "performance":
        return base + '<path d="M0 850 Q500 700 960 800 T1920 730 V1080 H0Z" fill="url(#road)"/>'
    if family == "interior":
        return '<rect width="1920" height="1080" fill="#06090D"/><rect x="70" y="90" width="1780" height="900" rx="55" fill="#111922" stroke="#39434E" stroke-width="5"/>'
    return base + '<ellipse cx="960" cy="590" rx="900" ry="430" fill="#F4D58B" opacity=".08"/><path d="M0 860 Q500 700 960 800 T1920 760 V1080 H0Z" fill="url(#road)"/>'


def _family(scene):
    text = (scene.narration + " " + scene.visual_intent).casefold()
    checks = [("battery", ["بطارية", "battery", "خلية"]),("charging", ["800v", "شحن", "charging", "charger"]),("interior", ["مقصورة", "داخلية", "dashboard", "cockpit", "تابلوه"]),("wheel_detail", ["عجلة", "عجلات", "wheel", "rim"]),("aero", ["ديناميكية", "aero", "aerodynamic"]),("performance", ["أداء", "تسارع", "سرعة", "قوة", "حصان", "عزم", "performance"]),("safety", ["أمان", "فرامل", "تصادم", "safety"]),("technology", ["تقنية", "حساس", "كاميرا", "software"]),("design_detail", ["تصميم", "هيكل", "واجهة", "design"])]
    for family, words in checks:
        if any(word in text for word in words):
            return family
    return ["front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene"][(int(scene.id)-1)%5]


def _special_visual(family, scene):
    if family == "battery":
        cells=''.join(f'<rect x="{500+(i%5)*145}" y="{360+(i//5)*120}" width="110" height="80" rx="12" fill="#18222A" stroke="{ACCENT}" stroke-width="3"/>' for i in range(15))
        return f'<rect x="390" y="250" width="1160" height="560" rx="40" fill="#0B1117" stroke="#45525D" stroke-width="5"/>{cells}'
    if family == "charging":
        return f'<rect x="430" y="240" width="1060" height="580" rx="40" fill="#0B1117" stroke="#45525D" stroke-width="5"/><path d="M850 690 V420 H1090 L1010 540 H1210 L940 830 V610 H740Z" fill="{ACCENT}"/>'
    if family == "interior":
        return f'<path d="M240 720 Q360 420 650 420 H1260 Q1550 420 1690 720 L1540 820 H380Z" fill="#202A33" stroke="#74818C" stroke-width="5"/><rect x="650" y="475" width="620" height="210" rx="24" fill="#071017" stroke="{ACCENT}" stroke-width="5"/>'
    if family == "wheel_detail":
        return f'<circle cx="960" cy="550" r="310" fill="#070A0D" stroke="#AEB8C0" stroke-width="22"/><circle cx="960" cy="550" r="230" fill="#1A2229" stroke="#56636E" stroke-width="8"/><path d="M960 330 V770 M740 550 H1180 M805 395 L1115 705 M1115 395 L805 705" stroke="{ACCENT}" stroke-width="18"/><circle cx="960" cy="550" r="60" fill="{ACCENT}"/>'
    if family == "aero":
        paths=''.join(f'<path d="M{x} 760 L{x+260} 520" stroke="#7D8993" stroke-width="4"/>' for x in range(500,1500,180))
        return f'<path d="M560 650 Q850 390 1440 500" fill="none" stroke="#D7DEE3" stroke-width="18"/><path d="M520 700 Q900 440 1510 560" fill="none" stroke="{ACCENT}" stroke-width="8"/>{paths}'
    if family == "performance":
        return f'<path d="M260 790 C600 650 820 680 1080 520 S1560 390 1760 430" fill="none" stroke="{ACCENT}" stroke-width="10"/><circle cx="1760" cy="430" r="18" fill="{ACCENT}"/>'
    if family == "safety":
        return f'<circle cx="960" cy="560" r="270" fill="none" stroke="{ACCENT}" stroke-width="9"/><path d="M960 300 L1210 400 V590 C1210 760 1090 850 960 910 C830 850 710 760 710 590 V400Z" fill="#101820" stroke="#8A969F" stroke-width="7"/><path d="M830 585 L925 680 L1100 480" fill="none" stroke="{ACCENT}" stroke-width="20"/>'
    return ""


def _car_composition(family, scene_id):
    presets={"front_3q":(-20,205,.98,1),"rear_3q":(520,190,.98,-1),"side_profile":(50,235,.92,1),"low_angle":(-60,280,1.04,1),"wide_scene":(120,310,.82,1)}
    key=family if family in presets else ["front_3q","rear_3q","side_profile","low_angle","wide_scene"][(scene_id-1)%5]
    x,y,scale,mirror=presets[key]
    return key,f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero()}</g>'


def _chips(calls):
    out=[]
    for i,value in enumerate(calls[:3]):
        x,y=1370,180+i*118
        out.append(f'<rect x="{x}" y="{y}" width="455" height="88" rx="18" fill="#0C1116" fill-opacity=".94" stroke="#39434E"/>')
        out.append(_text(value,x+24,y+55,23,650,"start",TEXT))
    return ''.join(out)


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    kind=_kind(scene); family=_family(scene); angle,car=_car_composition(family,int(scene.id))
    calls=[str(c) for c in scene.callouts[:3]]
    intent=html.escape(str(scene.visual_intent).strip()[:240])
    topic_x=1810 if _has_arabic(topic) else 70
    car_layer='' if family in {"battery","charging","interior","wheel_detail","aero"} else car
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-visual-family="{html.escape(family)}" data-camera-angle="{angle}" data-visual-intent="{intent}" data-visual-focus="{html.escape(family)}" data-asset-quality="premium_automotive_editorial_v3" data-motion="camera_push_pan">{_defs()}{_background(family)}{_text(topic,topic_x,78,27,700,"start",TEXT)}{car_layer}{_special_visual(family,scene)}{_chips(calls)}<text x="70" y="1015" font-family="Noto Sans" font-size="18" font-weight="700" fill="{MUTED}" letter-spacing="3">{html.escape(family.upper())}</text></svg>'''
    out.write_text(svg,encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
