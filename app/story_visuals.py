from __future__ import annotations
import html,re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .core import RUN,Story
from .raster_automotive import render_scene_raster,png_as_data_svg
W,H=1920,1080
TEXT="#F4F6F8";MUTED="#A7AFB8";ACCENT="#E8B44A";LINE="#303944"
LEGACY_CONTRACT_MARKER="STORY CALLOUT"
def _has_arabic(value): return bool(re.search(r"[\u0600-\u06ff]",str(value)))
def _text(text,x,y,size,weight=500,anchor="start",fill=TEXT):
    value=html.escape(str(text)[:140]);rtl=' direction="rtl" unicode-bidi="plaintext"' if _has_arabic(value) else ''
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}"{rtl}>{value}</text>'
def _kind(scene):
    text=(scene.narration+" "+scene.visual_intent).casefold();groups={"performance":["power","performance","horsepower","torque","acceleration","speed","أداء","قوة","حصان","عزم","تسارع","سرعة"],"design":["design","exterior","body","style","aerodynamic","تصميم","هيكل","شكل","خارجية","ديناميكية"],"interior":["interior","cabin","seat","dashboard","screen","مقصورة","داخلية","مقاعد","شاشة","تابلوه"],"technology":["technology","tech","software","sensor","camera","assist","تقنية","تقنيات","حساس","كاميرا","مساعدة"],"efficiency":["range","efficiency","consumption","battery","electric","مدى","كفاءة","استهلاك","بطارية","كهربائية"],"charging":["charging","charge","شحن","الشحن"],"safety":["safety","brake","airbag","collision","أمان","فرامل","وسادة","تصادم"],"price":["price","cost","value","سعر","تكلفة","قيمة"]}
    for name,words in groups.items():
        if any(w in text for w in words): return name
    return "hero"
def _visual_family(kind,scene_id):
    if kind=="design":
        return "aero" if scene_id in {12,19} else ("wide_scene" if scene_id==23 else "design_detail")
    return {"performance":"performance","interior":"interior","technology":"technology","efficiency":"battery","charging":"charging","safety":"safety","price":"wide_scene","hero":"front_3q"}.get(kind,"front_3q")
def _defs():
    return '''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#151D26"/><stop offset=".45" stop-color="#080B10"/><stop offset="1" stop-color="#17120B"/></linearGradient><linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FCFDFD"/><stop offset=".18" stop-color="#D7DDE2"/><stop offset=".42" stop-color="#697681"/><stop offset=".72" stop-color="#29333D"/><stop offset="1" stop-color="#0D1217"/></linearGradient><linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#435A6A"/><stop offset=".38" stop-color="#101A24"/><stop offset=".72" stop-color="#071017"/><stop offset="1" stop-color="#506B7A"/></linearGradient><linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#F4F6F7"/><stop offset=".45" stop-color="#89939C"/><stop offset="1" stop-color="#252D35"/></linearGradient><linearGradient id="road" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1A222A"/><stop offset="1" stop-color="#040507"/></linearGradient><radialGradient id="spot"><stop offset="0" stop-color="#F4D58B" stop-opacity=".34"/><stop offset="1" stop-color="#F4D58B" stop-opacity="0"/></radialGradient><linearGradient id="redlight" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FF5B4D"/><stop offset="1" stop-color="#7E1614"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="9"/></filter><filter id="shadow"><feGaussianBlur stdDeviation="18"/></filter></defs>'''
def _car_hero(x=40,y=180,scale=0.94,accent=ACCENT):
    return f'''<g transform="translate({x},{y}) scale({scale})" data-car-style="premium_3q_editorial" data-car-layer="primary"><ellipse cx="760" cy="615" rx="680" ry="86" fill="#000" opacity=".78" filter="url(#shadow)"/><ellipse cx="760" cy="595" rx="610" ry="34" fill="{accent}" opacity=".10" filter="url(#glow)"/><path d="M75 505 Q125 418 290 375 L485 318 Q620 270 790 275 L950 294 Q1080 310 1195 380 L1390 478 Q1450 508 1460 552 L1415 600 L1130 616 L335 628 L125 592 L72 552 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="6"/><path d="M300 374 L485 222 Q565 162 710 165 L875 182 Q1015 198 1128 319 L1178 385 L930 400 L520 402 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="5"/><path d="M505 226 L532 398 M865 185 L930 397" stroke="#B7C5CE" stroke-width="4" opacity=".72"/><path d="M112 498 Q330 412 590 420 Q920 420 1220 448 L1408 514" fill="none" stroke="#FFFFFF" stroke-opacity=".58" stroke-width="9"/><path d="M150 520 Q390 468 650 478 L1150 484 Q1300 488 1415 528" fill="none" stroke="{accent}" stroke-opacity=".92" stroke-width="5"/><path d="M1180 395 L1378 482 L1450 528 L1395 558 L1265 535 L1140 468 Z" fill="#151C23" opacity=".92"/><path d="M1310 486 L1438 526 L1400 551 L1315 540 Z" fill="url(#redlight)"/><path d="M106 530 L270 510 L300 563 L135 574 Z" fill="#202932"/><path d="M220 575 Q650 610 1270 565" fill="none" stroke="#080A0D" stroke-width="14"/><path d="M530 404 L645 404 L630 522 L505 522 Z M735 405 L845 405 L915 520 L785 520 Z" fill="#1A232B" opacity=".72"/><path d="M420 355 Q680 325 1035 356" fill="none" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="10"/><path d="M145 565 L420 570 M1040 560 L1280 548" stroke="#DCE3E8" stroke-opacity=".25" stroke-width="4"/><g><circle cx="350" cy="578" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="350" cy="578" r="76" fill="url(#rim)"/><circle cx="350" cy="578" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="350" cy="578" r="19" fill="{accent}"/><path d="M350 532 L350 624 M304 578 L396 578" stroke="#AAB5BD" stroke-width="5"/></g><g><circle cx="1120" cy="560" r="111" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="1120" cy="560" r="76" fill="url(#rim)"/><circle cx="1120" cy="560" r="55" fill="#10161B" stroke="#68747E" stroke-width="5"/><circle cx="1120" cy="560" r="19" fill="{accent}"/><path d="M1120 514 L1120 606 M1074 560 L1166 560" stroke="#AAB5BD" stroke-width="5"/></g><path d="M1010 428 Q1080 410 1140 430 L1190 460" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="6"/><path d="M90 632 Q730 716 1420 620" fill="none" stroke="{accent}" stroke-opacity=".38" stroke-width="4"/></g>'''
def _camera_car(camera,x,y,scale,mirror,accent=ACCENT):
    """Render materially different vehicle geometry per camera preset."""
    if camera=="front_3q":
        return f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero(0,0,1.0,accent)}</g>'
    if camera=="rear_3q":
        return f'''<g transform="translate({x},{y}) scale({mirror*scale},{scale})">
        <ellipse cx="760" cy="610" rx="650" ry="78" fill="#000" opacity=".78" filter="url(#shadow)"/>
        <path d="M105 540 Q150 430 330 380 L520 330 Q760 285 1000 330 L1190 380 Q1370 430 1415 540 L1380 600 Q1100 650 760 650 Q420 650 140 600 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="7"/>
        <path d="M350 385 Q430 230 620 205 L900 205 Q1090 230 1170 385 L1080 420 L440 420 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="6"/>
        <path d="M145 505 Q400 470 760 475 Q1120 470 1375 505" fill="none" stroke="#DCE3E8" stroke-opacity=".35" stroke-width="10"/>
        <path d="M170 535 Q420 500 760 510 Q1100 500 1350 535" fill="none" stroke="{accent}" stroke-width="8"/>
        <path d="M260 535 L500 540 M1020 540 L1260 535" stroke="#FF5B4D" stroke-width="28" stroke-linecap="round"/>
        <rect x="575" y="535" width="370" height="42" rx="20" fill="#151C23" stroke="#66717C" stroke-width="4"/>
        <circle cx="330" cy="585" r="95" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/>
        <circle cx="1190" cy="585" r="95" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/>
        </g>'''
    if camera=="front_close":
        return f'''<g transform="translate({x},{y}) scale({mirror*scale},{scale})">
        <ellipse cx="760" cy="700" rx="610" ry="55" fill="#000" opacity=".7" filter="url(#shadow)"/>
        <path d="M120 620 Q180 390 380 270 Q760 105 1140 270 Q1340 390 1400 620 L1320 720 Q760 790 200 720 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="8"/>
        <path d="M300 430 Q410 235 760 205 Q1110 235 1220 430 L1080 470 L440 470 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="6"/>
        <path d="M270 560 Q760 500 1250 560" fill="none" stroke="#FFFFFF" stroke-opacity=".45" stroke-width="10"/>
        <path d="M250 620 Q760 570 1270 620" fill="none" stroke="{accent}" stroke-width="9"/>
        <path d="M340 610 L560 590 M960 590 L1180 610" stroke="#F4F6F8" stroke-width="18" stroke-linecap="round"/>
        <path d="M690 610 L760 570 L830 610 L805 690 L715 690 Z" fill="#10161B" stroke="#66717C" stroke-width="5"/>
        </g>'''
    if camera=="interior":
        return f'''<g transform="translate({x},{y}) scale({scale})">
        <rect x="90" y="180" width="1340" height="700" rx="70" fill="#080D12" stroke="#6B7680" stroke-width="8"/>
        <path d="M150 700 Q300 430 520 360 L700 390 L760 470 L820 390 L1000 360 Q1220 430 1370 700" fill="#151D26" stroke="#AAB7C1" stroke-width="6"/>
        <path d="M180 300 Q760 180 1340 300 L1280 430 Q760 350 220 430 Z" fill="url(#glass)" opacity=".9"/>
        <rect x="560" y="475" width="400" height="170" rx="24" fill="#05080B" stroke="{accent}" stroke-width="6"/>
        <path d="M600 610 H920 M640 570 H880" stroke="{accent}" stroke-width="8"/>
        <circle cx="410" cy="600" r="115" fill="#111820" stroke="#AAB7C1" stroke-width="9"/>
        <circle cx="1110" cy="600" r="115" fill="#111820" stroke="#AAB7C1" stroke-width="9"/>
        </g>'''
    if camera=="low_angle":
        return f'<g transform="translate({x},{y}) skewY(7) scale({mirror*scale},{scale})">{_car_hero(0,0,1.0,accent)}</g>'
    if camera=="three_quarter_high":
        return f'<g transform="translate({x},{y}) rotate(-5 760 540) scale({mirror*scale*.94},{scale*.82})">{_car_hero(0,40,1.0,accent)}</g>'
    if camera=="side_profile":
        return f'''<g transform="translate({x},{y}) scale({mirror*scale},{scale})">
        <ellipse cx="760" cy="620" rx="690" ry="72" fill="#000" opacity=".78" filter="url(#shadow)"/>
        <path d="M70 545 Q115 470 235 445 L410 405 L555 335 Q690 270 835 300 L1040 345 Q1170 375 1280 445 L1420 505 Q1470 530 1455 575 L1390 610 L1190 625 L350 635 L120 600 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="7"/>
        <path d="M390 405 L555 300 Q660 230 810 250 L1010 300 L1130 405 L980 425 L520 425 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="6"/>
        <path d="M570 305 L585 425 M820 260 L865 425" stroke="#B7C5CE" stroke-width="4" opacity=".72"/>
        <path d="M115 505 Q430 450 760 470 Q1080 450 1400 515" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="9"/>
        <path d="M145 550 Q500 510 820 525 L1390 545" fill="none" stroke="{accent}" stroke-width="6"/>
        <path d="M1230 450 L1405 515 L1445 545 L1390 565 L1260 535 Z" fill="#151C23"/>
        <path d="M1290 480 L1415 520 L1395 542 L1300 530 Z" fill="url(#redlight)"/>
        <path d="M210 575 Q650 610 1280 570" fill="none" stroke="#080A0D" stroke-width="14"/>
        <circle cx="350" cy="580" r="112" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="350" cy="580" r="76" fill="url(#rim)"/><circle cx="350" cy="580" r="19" fill="{accent}"/>
        <circle cx="1120" cy="565" r="112" fill="#06080B" stroke="#BFC8CF" stroke-width="12"/><circle cx="1120" cy="565" r="76" fill="url(#rim)"/><circle cx="1120" cy="565" r="19" fill="{accent}"/>
        </g>'''
    if camera=="rear_close":
        return f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})"><path d="M170 650 Q230 390 470 270 Q760 145 1050 270 Q1290 390 1350 650 L1260 760 Q760 820 260 760 Z" fill="url(#body)" stroke="#F7F8F9" stroke-width="9"/><path d="M360 430 Q480 255 760 225 Q1040 255 1160 430 L1060 485 L460 485 Z" fill="url(#glass)" stroke="#AAB7C1" stroke-width="7"/><path d="M250 575 Q760 510 1270 575" fill="none" stroke="{accent}" stroke-width="10"/><path d="M280 625 H520 M1000 625 H1240" stroke="#FF5B4D" stroke-width="34" stroke-linecap="round"/><rect x="610" y="610" width="300" height="70" rx="28" fill="#111820" stroke="#66717C" stroke-width="5"/><path d="M520 705 Q760 760 1000 705" fill="none" stroke="#080A0D" stroke-width="18"/><circle cx="390" cy="700" r="72" fill="#06080B" stroke="#BFC8CF" stroke-width="11"/><circle cx="1130" cy="700" r="72" fill="#06080B" stroke="#BFC8CF" stroke-width="11"/><circle cx="760" cy="610" r="13" fill="{accent}"/></g>'
    return f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_camera_car("rear_3q",0,0,1.0,1,accent)}</g>'
    return f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero(0,0,1.0,accent)}</g>'


def _environment(): return '<rect width="1920" height="1080" fill="url(#bg)"/><ellipse cx="930" cy="560" rx="900" ry="450" fill="url(#spot)"/><path d="M0 850 Q500 690 960 790 T1920 740 V1080 H0 Z" fill="url(#road)"/><path d="M0 910 Q500 770 960 860 T1920 810" fill="none" stroke="#2B333C" stroke-width="4"/><g opacity=".24">'+''.join(f'<path d="M{x} 180 L{x-120} 850" stroke="#56616C" stroke-width="2"/>' for x in range(160,1880,220))+'</g>'
def _chips(calls):
    out=[]
    for i,value in enumerate(calls[:4]):
        x=1370;y=240+i*132;out.append(f'<rect x="{x}" y="{y}" width="455" height="100" rx="20" fill="#0C1116" fill-opacity=".92" stroke="#39434E"/>');out.append(_text(value,x+28,y+61,25,650,"start",TEXT));out.append(f'<circle cx="{x+420}" cy="{y+50}" r="7" fill="{ACCENT}"/>')
    return ''.join(out)
def _semantic_overlay(kind,scene):
    if kind=="performance": return f'<path d="M1390 770 H1810" stroke="{LINE}" stroke-width="10"/><path d="M1390 770 L1690 690" stroke="{ACCENT}" stroke-width="10"/><circle cx="1690" cy="690" r="15" fill="{ACCENT}"/>'+_text("الأداء / الاستجابة",1390,835,20,700,"start",MUTED)
    if kind=="design": return f'<path d="M1380 760 Q1550 650 1810 735" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1550" cy="700" r="11" fill="{ACCENT}"/>'+_text("الشكل / الديناميكية الهوائية",1380,835,20,700,"start",MUTED)
    if kind=="interior": return f'<rect x="1370" y="700" width="455" height="150" rx="20" fill="#0C1116" stroke="#39434E"/><path d="M1410 805 L1480 755 L1560 790 L1640 735 L1775 790" fill="none" stroke="{ACCENT}" stroke-width="6"/>'+_text("المقصورة / التجربة",1395,735,20,700,"start",MUTED)
    if kind=="technology": return '<path d="M1390 760 H1800" stroke="#39434E" stroke-width="4"/>'+''.join(f'<circle cx="{1420+i*125}" cy="760" r="13" fill="{ACCENT}"/>' for i in range(4))+_text("بنية الأنظمة",1390,835,20,700,"start",MUTED)
    if kind=="efficiency": return f'<rect x="1380" y="730" width="430" height="22" rx="11" fill="#303944"/><rect x="1380" y="730" width="280" height="22" rx="11" fill="{ACCENT}"/>'+_text("المدى / الكفاءة",1380,700,20,700,"start",MUTED)
    if kind=="charging": return f'<path d="M1390 760 H1800" stroke="#39434E" stroke-width="8"/><path d="M1390 760 L1550 700 L1700 735 L1800 675" fill="none" stroke="{ACCENT}" stroke-width="7"/>'+_text("منحنى الشحن",1390,835,20,700,"start",MUTED)
    if kind=="safety": return f'<circle cx="1600" cy="770" r="75" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1600" cy="770" r="45" fill="none" stroke="#66717C" stroke-width="3"/>'+_text("أنظمة الأمان",1510,870,20,700,"start",MUTED)
    if kind=="price": return f'<path d="M1390 800 H1800" stroke="#39434E" stroke-width="8"/><circle cx="1620" cy="800" r="15" fill="{ACCENT}"/>'+_text("القيمة",1390,735,20,700,"start",MUTED)
    return _text("تحرير السيارات",1390,815,20,700,"start",MUTED)
def _composition(scene_id:int):
    return [("front_3q",40,180,.94,1),("low_angle",-10,225,1.0,1),("front_close",-115,145,1.10,1),("rear_3q",1540,180,.94,-1),("wide_scene",140,245,.88,1),("three_quarter_high",90,110,.82,1),("side_profile",-80,300,.86,1),("rear_close",1470,240,1.02,-1)][(scene_id-1)%8]
def render_scene_svg(scene,topic:str,out:Path)->None:
    out.parent.mkdir(parents=True,exist_ok=True)
    layout=scene.layout.casefold()
    kind=_kind(scene)
    intent=str(scene.visual_intent).strip()
    camera,x,y,scale,mirror=_composition(scene.id)
    if kind=="interior": camera="interior"
    png=out.with_suffix(".png")
    render_scene_raster(scene,topic,png,(W,H),camera=camera)
    svg=png_as_data_svg(png,W,H,{
        "visual-family":_visual_family(kind,scene.id),
        "visual-mode":kind,
        "layout":layout,
        "camera-angle":camera,
        "visual-intent":intent[:240],
        "asset-quality":"raster_automotive_render_v1",
        "motion":"camera_push_pan",
        "car-layer":"primary",
    })
    out.write_text(svg,encoding="utf-8")

def generate_visuals(story:Story,out_dir:Path=RUN/"scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    def render_one(scene): render_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(render_one,story.scenes))
