from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

from .core import RUN, Story
from .story_visuals import _car_hero, _defs, _kind

W,H=1080,1920
TEXT="#F4F6F8";MUTED="#A7AFB8";ACCENT="#E8B44A";PANEL="#0B1015";LINE="#303944"
MODE_LABELS={"performance":"PERFORMANCE","design":"DESIGN","interior":"CABIN","technology":"TECHNOLOGY","efficiency":"EFFICIENCY","safety":"SAFETY","price":"VALUE","hero":"AUTOMOTIVE"}
SHORT_SAFE={"left":72,"right":72,"top":120,"bottom":180}

def _has_arabic(value):return bool(re.search(r"[\u0600-\u06ff]",str(value)))
def _text(text,x,y,size,weight=500,anchor="start",fill=TEXT):
    value=html.escape(str(text)[:110]); arabic=_has_arabic(value); rtl=' direction="rtl" unicode-bidi="plaintext"' if arabic else ''
    if arabic and anchor=="start":
        anchor="end"
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'

def _hero_car(kind:str,scene_id:int):
    # Native 9:16 composition. The full car silhouette is kept inside x=72..1008;
    # no horizontal crop is used and no mirrored transform can throw the subject off-canvas.
    variants=[
        ("vertical_hero",72,315,.64),
        ("vertical_low",48,390,.67),
        ("vertical_tight",38,285,.68),
        ("vertical_offset",92,430,.62),
        ("vertical_wide",58,455,.61),
    ]
    angle,x,y,scale=variants[(scene_id-1)%len(variants)]
    return angle,f'<g transform="translate({x},{y}) scale({scale})">{_car_hero(0,0,.98)}</g>'

def _focus_overlay(kind:str,scene):
    calls=[str(c) for c in scene.callouts[:3]];label=calls[0] if calls else scene.visual_intent
    if kind=="performance":return f'<path d="M80 900 H1000" stroke="{LINE}" stroke-width="8"/><path d="M80 900 L820 750" stroke="{ACCENT}" stroke-width="10"/><circle cx="820" cy="750" r="13" fill="{ACCENT}"/>'+_text("PERFORMANCE",80,970,22,700,"start",MUTED)
    if kind=="design":return f'<path d="M80 900 Q330 760 620 860 T1000 790" fill="none" stroke="{ACCENT}" stroke-width="7"/><circle cx="620" cy="830" r="12" fill="{ACCENT}"/>'+_text("DESIGN / AERODYNAMICS",80,970,22,700,"start",MUTED)
    if kind=="interior":return f'<rect x="90" y="800" width="900" height="155" rx="24" fill="{PANEL}" stroke="#39434E"/><path d="M130 900 L250 840 L390 905 L540 830 L700 900 L920 835" fill="none" stroke="{ACCENT}" stroke-width="6"/>'+_text("CABIN / EXPERIENCE",110,850,22,700,"start",MUTED)
    if kind=="technology":return '<g>'+''.join(f'<circle cx="{150+i*230}" cy="900" r="30" fill="#080B0F" stroke="{ACCENT}" stroke-width="5"/>' for i in range(4))+'</g>'+_text("CONNECTED SYSTEM",80,970,22,700,"start",MUTED)
    if kind=="efficiency":return f'<rect x="90" y="900" width="900" height="25" rx="12" fill="{LINE}"/><rect x="90" y="900" width="610" height="25" rx="12" fill="{ACCENT}"/>'+_text("RANGE / EFFICIENCY",90,970,22,700,"start",MUTED)
    if kind=="safety":return f'<circle cx="540" cy="900" r="135" fill="none" stroke="{ACCENT}" stroke-width="6"/><circle cx="540" cy="900" r="82" fill="none" stroke="{LINE}" stroke-width="5"/>'+_text("SAFETY",540,1090,22,700,"middle",MUTED)
    if kind=="price":return f'<path d="M90 900 H990" stroke="{LINE}" stroke-width="8"/><circle cx="620" cy="900" r="14" fill="{ACCENT}"/>'+_text("VALUE POSITION",90,970,22,700,"start",MUTED)
    return _text(label,540,970,27,700,"middle",TEXT)

def _callout_stack(calls):
    out=[]
    for i,call in enumerate(calls[:3]):
        y=1140+i*118;out.append(f'<rect x="60" y="{y}" width="960" height="86" rx="18" fill="{PANEL}" stroke="#39434E"/>');out.append(_text(call,92,y+55,22,650,"start",TEXT));out.append(f'<circle cx="970" cy="{y+43}" r="6" fill="{ACCENT}"/>')
    return ''.join(out)

def vertical_scene_svg(scene,topic:str,out:Path):
    out.parent.mkdir(parents=True,exist_ok=True);kind=_kind(scene);layout=scene.layout.casefold();calls=[str(c) for c in scene.callouts[:3]];intent=str(scene.visual_intent).strip();angle,car=_hero_car(kind,scene.id);topic_x=1008 if _has_arabic(topic) else 72
    car_signature=hashlib.sha256(re.sub(r'\s+','',_car_hero(0,0,.98)).encode('utf-8')).hexdigest()[:16]
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}" data-camera-angle="{angle}" data-visual-intent="{html.escape(intent[:240])}" data-asset-quality="premium_automotive_editorial_v3_vertical" data-motion="vertical_subject_push" data-car-signature="{car_signature}" data-safe-left="72" data-safe-right="72" data-safe-top="120" data-safe-bottom="180"><defs>{_defs()}</defs><rect width="1080" height="1920" fill="#07090c"/><rect width="1080" height="1500" fill="url(#bg)"/><ellipse cx="540" cy="690" rx="510" ry="430" fill="url(#spot)"/><path d="M55 120 H1025" stroke="{ACCENT}" stroke-width="4"/>{_text(topic,topic_x,85,28,700,"end" if _has_arabic(topic) else "start",TEXT)}{car}{_focus_overlay(kind,scene)}{_callout_stack(calls)}{_text(MODE_LABELS.get(kind,"AUTOMOTIVE"),540,1780,18,700,"middle",MUTED)}</svg>'''
    out.write_text(svg,encoding="utf-8")

def generate_vertical_visuals(story:Story,out_dir:Path=RUN/"vertical_scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    for scene in story.scenes:vertical_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
