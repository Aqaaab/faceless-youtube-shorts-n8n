from __future__ import annotations

import html
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .core import RUN, Story
from .story_visuals import _kind, _camera_car
from .raster_automotive import png_as_data_svg
from .blender_automotive import render_scene_blender

W,H=1080,1920
TEXT="#F4F6F8";MUTED="#A7AFB8";ACCENT="#E8B44A";PANEL="#0B1015";LINE="#303944"
MODE_LABELS={"performance":"الأداء","design":"التصميم","interior":"المقصورة","technology":"التقنية","efficiency":"الكفاءة","charging":"الشحن","safety":"السلامة","price":"القيمة","hero":"السيارة"}

def _has_arabic(value):return bool(re.search(r"[\u0600-\u06ff]",str(value)))
def _text(text,x,y,size,weight=500,anchor="start",fill=TEXT):
    value=html.escape(str(text)[:110]);rtl=' direction="rtl" unicode-bidi="plaintext"' if _has_arabic(value) else ''
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'

def _hero_car(kind:str,scene_id:int):
    variants=[("front_3q",-80,420,.68,1),("low_angle",-120,460,.72,1),("front_close",-185,360,.78,1),("rear_3q",1160,420,.68,-1),("wide_scene",-25,500,.62,1),("three_quarter_high",-10,350,.60,1),("side_profile",-80,430,.68,1),("rear_close",1120,390,.76,-1)]
    camera,x,y,scale,mirror=variants[(scene_id-1)%len(variants)]
    if kind=="interior": camera="interior"; x=-170; y=300; scale=.78; mirror=1
    return camera,_camera_car(camera,x,y,scale,mirror)

def _focus_overlay(kind:str,scene):
    calls=[str(c) for c in scene.callouts[:3]];label=calls[0] if calls else scene.visual_intent
    if kind=="performance":return f'<path d="M80 1160 H1000" stroke="{LINE}" stroke-width="8"/><path d="M80 1160 L820 1010" stroke="{ACCENT}" stroke-width="10"/><circle cx="820" cy="1010" r="13" fill="{ACCENT}"/>'+_text("الأداء",80,1230,22,700,"start",MUTED)
    if kind=="design":return f'<path d="M80 1160 Q330 980 620 1120 T1000 1030" fill="none" stroke="{ACCENT}" stroke-width="7"/><circle cx="620" cy="1080" r="12" fill="{ACCENT}"/>'+_text("التصميم / الديناميكية الهوائية",80,1230,22,700,"start",MUTED)
    if kind=="interior":return f'<rect x="90" y="1060" width="900" height="155" rx="24" fill="{PANEL}" stroke="#39434E"/><path d="M130 1160 L250 1100 L390 1165 L540 1090 L700 1160 L920 1095" fill="none" stroke="{ACCENT}" stroke-width="6"/>'+_text("المقصورة / التجربة",110,1110,22,700,"start",MUTED)
    if kind=="technology":return '<g>'+''.join(f'<circle cx="{150+i*230}" cy="1190" r="30" fill="#080B0F" stroke="{ACCENT}" stroke-width="5"/>' for i in range(4))+'</g>'+_text("الأنظمة المتصلة",80,1260,22,700,"start",MUTED)
    if kind=="efficiency":return f'<rect x="90" y="1170" width="900" height="25" rx="12" fill="{LINE}"/><rect x="90" y="1170" width="610" height="25" rx="12" fill="{ACCENT}"/>'+_text("المدى / الكفاءة",90,1240,22,700,"start",MUTED)
    if kind=="safety":return f'<circle cx="540" cy="1160" r="135" fill="none" stroke="{ACCENT}" stroke-width="6"/><circle cx="540" cy="1160" r="82" fill="none" stroke="{LINE}" stroke-width="5"/>'+_text("أنظمة الأمان",540,1350,22,700,"middle",MUTED)
    if kind=="price":return f'<path d="M90 1170 H990" stroke="{LINE}" stroke-width="8"/><circle cx="620" cy="1170" r="14" fill="{ACCENT}"/>'+_text("القيمة",90,1235,22,700,"start",MUTED)
    return _text(label,540,1235,27,700,"middle",TEXT)

def _callout_stack(calls):
    out=[]
    for i,call in enumerate(calls[:3]):
        y=1370+i*112;out.append(f'<rect x="60" y="{y}" width="960" height="84" rx="18" fill="{PANEL}" stroke="#39434E"/>');out.append(_text(call,92,y+53,23,650,"start",TEXT));out.append(f'<circle cx="970" cy="{y+42}" r="6" fill="{ACCENT}"/>')
    return ''.join(out)

def vertical_scene_svg(scene,topic:str,out:Path):
    out.parent.mkdir(parents=True,exist_ok=True)
    kind=_kind(scene)
    layout=scene.layout.casefold()
    intent=str(scene.visual_intent).strip()
    camera=["front_3q","low_angle","front_close","rear_3q","wide_scene","three_quarter_high","side_profile","rear_close"][(scene.id-1)%8]
    if kind=="interior": camera="interior"
    png=out.with_suffix(".png")
    render_scene_blender(scene,topic,png,(W,H),camera)
    svg=png_as_data_svg(png,W,H,{
        "visual-mode":kind,
        "layout":layout,
        "camera-angle":camera,
        "visual-intent":intent[:240],
        "asset-quality":"blender_eevee_automotive_v1_vertical",
        "motion":"vertical_push_pan",
        "car-layer":"primary",
    })
    out.write_text(svg,encoding="utf-8")

def generate_vertical_visuals(story:Story,out_dir:Path=RUN/"vertical_scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    def render_one(scene): vertical_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(render_one,story.scenes))
