from __future__ import annotations

import html
import re
from pathlib import Path

from .core import RUN, Story
from .story_visuals import _camera_car, _defs, _kind

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

