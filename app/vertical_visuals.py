from __future__ import annotations

import html
from pathlib import Path

from .core import RUN, Story
from .story_visuals import _defs, _family, _has_arabic, _kind, _special_visual, _text

W, H = 1080, 1920
TEXT = "#F4F6F8"
MUTED = "#A7AFB8"
ACCENT = "#E8B44A"
PANEL = "#0B1015"

# Contracted semantic families. Keep these explicit so the vertical engine cannot silently
# collapse technical/editorial scenes into one generic composition.
SEMANTIC_MODES = {"performance", "design", "interior", "technology", "efficiency", "safety", "price", "battery", "charging", "wheel_detail", "aero"}


def _vertical_car(scene_id: int, family: str):
    variants=[("front_3q",-150,430,.54,1),("rear_3q",700,430,.54,-1),("side_profile",-80,520,.52,1),("low_angle",-190,610,.60,1),("wide_scene",-10,610,.46,1)]
    angle,x,y,scale,mirror=variants[(scene_id-1)%len(variants)]
    if family in {"battery","charging","interior","wheel_detail","aero","technology","efficiency","safety","price"}:
        return angle,""
    from .story_visuals import _car_hero
    return angle,f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero()}</g>'


def _background(family):
    if family in {"battery","charging","technology"}:
        return '<rect width="1080" height="1920" fill="#070A0E"/><path d="M70 260 H1010" stroke="#2D3943" stroke-width="4"/>'
    if family == "interior":
        return '<rect width="1080" height="1920" fill="#05080C"/><rect x="35" y="300" width="1010" height="1100" rx="42" fill="#111922" stroke="#3A4650" stroke-width="4"/>'
    if family in {"performance","efficiency"}:
        return '<rect width="1080" height="1920" fill="#07090C"/><path d="M0 1500 Q300 1260 540 1430 T1080 1320 V1920 H0Z" fill="#10161B"/>'
    if family == "safety":
        return '<rect width="1080" height="1920" fill="#07090C"/><circle cx="540" cy="820" r="410" fill="none" stroke="#394752" stroke-width="8"/><path d="M210 1130 L540 480 L870 1130" fill="none" stroke="#6D7983" stroke-width="5"/>'
    if family == "price":
        return '<rect width="1080" height="1920" fill="#07090C"/><rect x="70" y="360" width="940" height="620" rx="38" fill="#0E151C" stroke="#46535E" stroke-width="5"/>'
    return '<rect width="1080" height="1920" fill="#07090C"/><rect width="1080" height="1320" fill="url(#bg)"/><ellipse cx="540" cy="800" rx="500" ry="520" fill="#F4D58B" opacity=".08"/>'


def _vertical_special(family):
    if family == "battery":
        cells=''.join(f'<rect x="{170+(i%5)*155}" y="{520+(i//5)*125}" width="120" height="90" rx="12" fill="#17212A" stroke="{ACCENT}" stroke-width="3"/>' for i in range(15))
        return f'<rect x="90" y="390" width="900" height="760" rx="35" fill="#0B1117" stroke="#46535E" stroke-width="5"/><text x="540" y="465" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">BATTERY PACK</text>{cells}'
    if family == "charging":
        return f'<rect x="90" y="380" width="900" height="780" rx="35" fill="#0B1117" stroke="#46535E" stroke-width="5"/><path d="M510 490 V690 H650 L565 820 H760 L500 1080 V850 H360Z" fill="{ACCENT}"/><text x="540" y="450" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">800V CHARGING</text>'
    if family == "interior":
        return f'<path d="M150 1120 Q190 650 420 540 H660 Q890 650 930 1120 L810 1240 H270Z" fill="#202A33" stroke="#76828B" stroke-width="5"/><rect x="330" y="610" width="420" height="190" rx="22" fill="#071017" stroke="{ACCENT}" stroke-width="5"/><path d="M380 750 H700 M440 680 H640" stroke="#98A4AE" stroke-width="6"/><text x="540" y="510" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">COCKPIT / INTERIOR</text>'
    if family == "wheel_detail":
        return f'<circle cx="540" cy="760" r="300" fill="#06090C" stroke="#AEB8C0" stroke-width="20"/><circle cx="540" cy="760" r="220" fill="#1A2229" stroke="#56636E" stroke-width="8"/><path d="M540 540 V980 M320 760 H760 M385 605 L695 915 M695 605 L385 915" stroke="{ACCENT}" stroke-width="17"/><circle cx="540" cy="760" r="55" fill="{ACCENT}"/><text x="540" y="1150" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">WHEEL / BRAKE</text>'
    if family == "aero":
        paths=''.join(f'<path d="M{x} 1110 L{x+190} 850" stroke="#71808A" stroke-width="4"/>' for x in range(120,900,150))
        return f'<path d="M100 950 Q380 600 820 700" fill="none" stroke="#D7DEE3" stroke-width="16"/><path d="M80 1030 Q420 670 950 770" fill="none" stroke="{ACCENT}" stroke-width="8"/>{paths}<text x="540" y="1260" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">AERODYNAMIC AIRFLOW</text>'
    if family == "performance":
        return f'<path d="M80 1120 C300 1000 480 1040 650 900 S900 760 1010 790" fill="none" stroke="{ACCENT}" stroke-width="10"/><circle cx="1010" cy="790" r="16" fill="{ACCENT}"/><text x="540" y="500" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">PERFORMANCE</text>'
    if family == "design":
        return f'<path d="M170 1050 Q250 520 540 470 Q830 520 910 1050" fill="none" stroke="#D7DEE3" stroke-width="14"/><path d="M220 1110 Q540 820 860 1110" fill="none" stroke="{ACCENT}" stroke-width="9"/><circle cx="540" cy="780" r="180" fill="none" stroke="#53616C" stroke-width="5"/><text x="540" y="500" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">DESIGN / PROPORTIONS</text>'
    if family == "technology":
        nodes=''.join(f'<circle cx="{260+i*140}" cy="{650+(i%2)*260}" r="34" fill="{ACCENT}"/>' for i in range(5))
        return f'<rect x="110" y="420" width="860" height="760" rx="34" fill="#0B1117" stroke="#46535E" stroke-width="5"/>{nodes}<path d="M260 650 L400 910 L540 650 L680 910 L820 650" fill="none" stroke="#7E8B95" stroke-width="7"/><text x="540" y="500" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">VEHICLE TECHNOLOGY</text>'
    if family == "efficiency":
        bars=''.join(f'<rect x="{190+i*145}" y="{1000-(i+1)*95}" width="85" height="{(i+1)*95}" rx="10" fill="{ACCENT}" opacity="{0.35+i*0.12}"/>' for i in range(5))
        return f'<path d="M150 1040 H930" stroke="#596671" stroke-width="5"/>{bars}<path d="M190 760 Q420 680 610 780 T900 610" fill="none" stroke="#D7DEE3" stroke-width="7"/><text x="540" y="500" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">EFFICIENCY</text>'
    if family == "safety":
        return f'<path d="M540 470 L830 620 V850 Q790 1110 540 1240 Q290 1110 250 850 V620Z" fill="#0D151C" stroke="{ACCENT}" stroke-width="9"/><path d="M420 850 L505 935 L680 735" fill="none" stroke="#D7DEE3" stroke-width="22"/><text x="540" y="500" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">SAFETY SYSTEMS</text>'
    if family == "price":
        return f'<text x="540" y="610" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">ESTIMATED PRICE</text><text x="540" y="790" text-anchor="middle" font-family="Noto Sans" font-size="92" font-weight="800" fill="{ACCENT}">$—</text><path d="M230 900 H850" stroke="#4A5660" stroke-width="5"/><text x="540" y="990" text-anchor="middle" font-family="Noto Sans" font-size="24" fill="{MUTED}">CONFIGURATION • MARKET • VALUE</text>'
    return ""


def vertical_scene_svg(scene, topic: str, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    kind=_kind(scene)
    family=_family(scene)
    angle,car=_vertical_car(int(scene.id),family)
    calls=[str(c) for c in scene.callouts[:2]]
    topic_x=1025 if _has_arabic(topic) else 55
    chips=''.join(f'<rect x="70" y="{1350+i*105}" width="940" height="76" rx="18" fill="{PANEL}" stroke="#39434E"/><text x="100" y="{1400+i*105}" font-family="Noto Sans Arabic,Noto Sans" font-size="21" fill="{TEXT}">{html.escape(c[:60])}</text>' for i,c in enumerate(calls))
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-visual-family="{html.escape(family)}" data-camera-angle="{angle}_vertical" data-visual-intent="{html.escape(str(scene.visual_intent).strip()[:240])}" data-visual-focus="{html.escape(family)}" data-asset-quality="premium_automotive_editorial_v3_vertical" data-motion="vertical_push_pan">{_defs()}{_background(family)}<path d="M55 115 H1025" stroke="{ACCENT}" stroke-width="4"/>{_text(topic,topic_x,92,25,700,"start",TEXT)}{car}{_vertical_special(family)}{chips}<text x="540" y="1820" text-anchor="middle" font-family="Noto Sans" font-size="17" font-weight="700" fill="{MUTED}" letter-spacing="3">{html.escape(family.upper())}</text></svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_vertical_visuals(story: Story, out_dir: Path = RUN / "vertical_scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        vertical_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
