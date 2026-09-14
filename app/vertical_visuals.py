from __future__ import annotations
import html
from pathlib import Path
from .core import RUN, Story
from .story_visuals import _defs,_family,_has_arabic,_kind,_text,_car_hero
W,H=1080,1920; TEXT="#F4F6F8"; MUTED="#A7AFB8"; ACCENT="#E8B44A"; PANEL="#0B1015"
SEMANTIC_MODES={"performance","design","interior","technology","efficiency","safety","price","battery","charging","wheel_detail","aero"}
TECHNICAL_FAMILIES={name:{"car_layer":"primary","car_composite":True} for name in SEMANTIC_MODES}
def _vertical_car(scene_id:int,family:str):
    variants=[("front_3q",40,850,.54,1),("rear_3q",530,850,.54,-1),("side_profile",35,900,.52,1),("low_angle",-10,930,.60,1),("wide_scene",120,940,.46,1),("front_close",170,820,.70,1),("rear_close",560,820,.70,-1),("three_quarter_high",110,760,.58,1)]
    angle,x,y,scale,mirror=variants[(scene_id-1)%8]
    return angle,f'<g data-car-layer="primary" data-car-style="premium_3q_editorial" opacity=".98" transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero()}</g>'
def _background(family):
    if family in {"battery","charging","technology"}: return '<rect width="1080" height="1920" fill="#070A0E"/><path d="M70 260 H1010" stroke="#2D3943" stroke-width="4"/>'
    if family=="interior": return '<rect width="1080" height="1920" fill="#05080C"/><rect x="35" y="300" width="1010" height="1100" rx="42" fill="#111922" stroke="#3A4650" stroke-width="4"/>'
    if family in {"performance","efficiency"}: return '<rect width="1080" height="1920" fill="#07090C"/><path d="M0 1500 Q300 1260 540 1430 T1080 1320 V1920 H0Z" fill="#10161B"/>'
    if family=="safety": return '<rect width="1080" height="1920" fill="#07090C"/><circle cx="540" cy="820" r="410" fill="none" stroke="#394752" stroke-width="8"/>'
    if family=="price": return '<rect width="1080" height="1920" fill="#07090C"/><rect x="70" y="360" width="940" height="620" rx="38" fill="#0E151C" stroke="#46535E" stroke-width="5"/>'
    return '<rect width="1080" height="1920" fill="#07090C"/><rect width="1080" height="1320" fill="url(#bg)"/><ellipse cx="540" cy="800" rx="500" ry="520" fill="#F4D58B" opacity=".08"/>'
def _vertical_special(family):
    if family=="battery":
        cells=''.join(f'<rect x="{150+(i%5)*155}" y="{430+(i//5)*92}" width="115" height="68" rx="10" fill="#17212A" stroke="{ACCENT}" stroke-width="3"/>' for i in range(15)); return f'<g opacity=".90"><rect x="90" y="330" width="900" height="640" rx="35" fill="#0B1117" stroke="#46535E" stroke-width="5"/><text x="540" y="395" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">BATTERY PACK</text>{cells}</g>'
    if family=="charging": return f'<g opacity=".90"><rect x="90" y="340" width="900" height="620" rx="35" fill="#0B1117" stroke="#46535E" stroke-width="5"/><path d="M500 820 V500 H650 L590 610 H760 L520 900 V700 H390Z" fill="{ACCENT}"/><text x="540" y="410" text-anchor="middle" font-family="Noto Sans" font-size="27" fill="{MUTED}">800V CHARGING</text></g>'
    if family=="interior": return '<g opacity=".90"><path d="M120 920 Q180 560 390 500 H690 Q900 560 960 920 L820 1000 H260Z" fill="#202A33" stroke="#76828B" stroke-width="5"/><rect x="330" y="570" width="420" height="170" rx="22" fill="#071017" stroke="#E8B44A" stroke-width="5"/></g>'
    if family=="wheel_detail": return f'<g opacity=".90"><circle cx="540" cy="760" r="250" fill="#06090C" stroke="#AEB8C0" stroke-width="18"/><circle cx="540" cy="760" r="175" fill="#1A2229" stroke="#56636E" stroke-width="8"/><path d="M540 585 V935 M365 760 H715 M415 635 L665 885 M665 635 L415 885" stroke="{ACCENT}" stroke-width="14"/></g>'
    if family=="aero": return f'<g opacity=".90"><path d="M120 900 Q380 520 860 620" fill="none" stroke="#D7DEE3" stroke-width="14"/><path d="M90 970 Q430 590 980 690" fill="none" stroke="{ACCENT}" stroke-width="8"/></g>'
    if family=="performance": return f'<g opacity=".90"><path d="M80 1000 C300 900 450 930 650 790 S900 680 1010 720" fill="none" stroke="{ACCENT}" stroke-width="10"/><circle cx="1010" cy="720" r="16" fill="{ACCENT}"/></g>'
    if family=="design": return '<g opacity=".90"><path d="M170 950 Q250 540 540 500 Q830 540 910 950" fill="none" stroke="#D7DEE3" stroke-width="14"/><path d="M220 1010 Q540 720 860 1010" fill="none" stroke="#E8B44A" stroke-width="9"/></g>'
    if family=="technology": return f'<g opacity=".90"><rect x="100" y="360" width="880" height="650" rx="34" fill="#0B1117" stroke="#46535E" stroke-width="5"/><path d="M220 570 L380 760 L540 570 L700 760 L860 570" fill="none" stroke="#7E8B95" stroke-width="7"/></g>'
    if family=="efficiency": return f'<g opacity=".90"><path d="M130 940 H950" stroke="#596671" stroke-width="5"/><path d="M170 700 Q400 620 600 730 T900 560" fill="none" stroke="#D7DEE3" stroke-width="7"/></g>'
    if family=="safety": return f'<g opacity=".90"><path d="M540 500 L810 640 V850 Q770 1040 540 1150 Q310 1040 270 850 V640Z" fill="#0D151C" stroke="{ACCENT}" stroke-width="9"/><path d="M420 820 L505 905 L680 705" fill="none" stroke="#D7DEE3" stroke-width="22"/></g>'
    if family=="price": return f'<g opacity=".90"><text x="540" y="600" text-anchor="middle" font-family="Noto Sans" font-size="30" fill="{MUTED}">ESTIMATED PRICE</text><text x="540" y="780" text-anchor="middle" font-family="Noto Sans" font-size="92" font-weight="800" fill="{ACCENT}">$—</text></g>'
    return ''
def vertical_scene_svg(scene,topic:str,out:Path):
    out.parent.mkdir(parents=True,exist_ok=True); kind=_kind(scene); family=_family(scene); angle,car=_vertical_car(int(scene.id),family); calls=[str(c) for c in scene.callouts[:2]]; topic_x=1025 if _has_arabic(topic) else 55
    chips=''.join(f'<rect x="70" y="{1370+i*105}" width="940" height="76" rx="18" fill="{PANEL}" stroke="#39434E"/><text x="100" y="{1420+i*105}" font-family="Noto Sans Arabic,Noto Sans" font-size="21" fill="{TEXT}">{html.escape(c[:60])}</text>' for i,c in enumerate(calls))
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-visual-family="{html.escape(family)}" data-camera-angle="{angle}_vertical" data-visual-intent="{html.escape(str(scene.visual_intent).strip()[:240])}" data-visual-focus="{html.escape(family)}" data-asset-quality="premium_automotive_editorial_v3_vertical" data-motion="vertical_push_pan" data-car-layer="primary">{_defs()}{_background(family)}<path d="M55 115 H1025" stroke="{ACCENT}" stroke-width="4"/>{_text(topic,topic_x,92,25,700,"start",TEXT)}{car}{_vertical_special(family)}{chips}<text x="540" y="1820" text-anchor="middle" font-family="Noto Sans" font-size="17" font-weight="700" fill="{MUTED}" letter-spacing="3">{html.escape(family.upper())}</text></svg>'''; out.write_text(svg,encoding='utf-8')
def generate_vertical_visuals(story:Story,out_dir:Path=RUN/"vertical_scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    for scene in story.scenes: vertical_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
