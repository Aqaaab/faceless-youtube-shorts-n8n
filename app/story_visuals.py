from __future__ import annotations
import html,re
from pathlib import Path
from .core import RUN,Story
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
def _car_hero(x=40,y=180,scale=0.94,accent=ACCENT,variant=0,focus="full"):
    """Layered metallic vehicle render: consistent identity with varied reflections and focal details."""
    v=int(variant)%6
    body_hi=["#FFFFFF","#EEF2F5","#D9E0E5","#F8FAFB","#D5DCE1","#EEF1F3"][v]
    body_mid=["#AEB8C0","#9FAAB4","#87939D","#B8C2C9","#8F9BA5","#A6B1B9"][v]
    body_dark=["#10161C","#0B1117","#151B21","#0E141A","#121920","#0A1015"][v]
    glass_hi=["#8FA9B8","#7893A4","#6F8999","#9CB1BE","#718B9B","#829EAE"][v]
    focus_marker = ""
    if focus=="wheel": focus_marker='<circle cx="350" cy="579" r="132" fill="none" stroke="#FFFFFF" stroke-opacity=".22" stroke-width="7"/>'
    elif focus=="front": focus_marker='<path d="M1110 395 Q1260 380 1400 500" fill="none" stroke="#FFFFFF" stroke-opacity=".34" stroke-width="12"/>'
    elif focus=="glass": focus_marker='<path d="M320 350 Q650 120 1120 340" fill="none" stroke="#FFFFFF" stroke-opacity=".28" stroke-width="18"/>'
    return f"""<g transform="translate({x},{y}) scale({scale})" data-car-layer="primary" data-car-style="premium_automotive_editorial_v4" data-car-material="layered-metallic-reflection">
      <ellipse cx="760" cy="630" rx="690" ry="92" fill="#000" opacity=".82" filter="url(#shadow)"/>
      <ellipse cx="760" cy="607" rx="600" ry="42" fill="{accent}" opacity=".10" filter="url(#glow)"/>
      <path d="M68 505 Q118 414 286 365 L475 308 Q625 250 790 266 L956 286 Q1085 300 1208 374 L1395 470 Q1456 503 1465 548 L1410 603 L1125 622 L332 635 L116 596 L64 550 Z" fill="url(#body)" stroke="#F8FAFC" stroke-width="7"/>
      <path d="M92 503 Q240 414 486 385 Q760 352 1118 408 Q1280 428 1418 505" fill="none" stroke="{body_hi}" stroke-opacity=".64" stroke-width="18"/>
      <path d="M102 545 Q360 485 640 493 Q990 496 1378 535" fill="none" stroke="{body_mid}" stroke-opacity=".72" stroke-width="26"/>
      <path d="M118 571 Q440 610 770 602 Q1090 594 1398 548" fill="none" stroke="{body_dark}" stroke-opacity=".78" stroke-width="30"/>
      <path d="M280 365 L472 214 Q566 146 716 151 L886 168 Q1028 188 1146 310 L1190 382 L930 404 L515 402 Z" fill="url(#glass)" stroke="#B9C6CF" stroke-width="6"/>
      <path d="M472 220 Q560 170 704 174 Q835 180 930 210 L1080 322" fill="none" stroke="{glass_hi}" stroke-opacity=".78" stroke-width="16"/>
      <path d="M492 232 L532 397 M858 182 L930 398" stroke="#DDE8EF" stroke-opacity=".58" stroke-width="5"/>
      <path d="M525 249 Q660 198 828 218 Q934 232 1038 300" fill="none" stroke="#FFFFFF" stroke-opacity=".30" stroke-width="9"/>
      <path d="M140 452 Q380 350 660 370 T1180 414 Q1320 440 1410 492" fill="none" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="30"/>
      <path d="M170 474 Q430 405 700 420 T1240 468" fill="none" stroke="{accent}" stroke-opacity=".22" stroke-width="12"/>
      <path d="M110 515 Q360 470 610 480 L1180 486 Q1320 489 1425 525" fill="none" stroke="{accent}" stroke-opacity=".95" stroke-width="7"/>
      <path d="M1160 391 L1380 475 L1452 524 L1394 560 L1260 538 L1134 467 Z" fill="{body_dark}" opacity=".96"/>
      <path d="M1298 482 L1439 525 L1400 552 L1304 540 Z" fill="url(#redlight)"/>
      <path d="M108 529 L272 506 L305 563 L134 577 Z" fill="{body_dark}"/>
      <path d="M1220 508 Q1325 492 1402 526 L1348 566 L1230 556 Z" fill="#05070A" stroke="#596671" stroke-width="4"/>
      <path d="M1252 520 L1364 536 M1250 532 L1354 547 M1244 544 L1342 556" stroke="#AAB7C0" stroke-opacity=".55" stroke-width="4"/>
      <g><circle cx="350" cy="579" r="116" fill="#07090C" stroke="#CBD3D9" stroke-width="13"/><circle cx="350" cy="579" r="84" fill="#343D45" stroke="#9EA8AF" stroke-width="5"/><circle cx="350" cy="579" r="64" fill="#0C1116" stroke="#6F7A83" stroke-width="4"/><circle cx="350" cy="579" r="27" fill="none" stroke="{accent}" stroke-width="6"/><circle cx="350" cy="579" r="12" fill="{accent}"/><path d="M350 522 L350 636 M293 579 L407 579 M309 538 L391 620 M391 538 L309 620" stroke="#C9D0D5" stroke-opacity=".65" stroke-width="4"/><path d="M430 542 Q450 580 428 615" fill="none" stroke="#C94A42" stroke-width="10"/></g>
      <g><circle cx="1120" cy="562" r="116" fill="#07090C" stroke="#CBD3D9" stroke-width="13"/><circle cx="1120" cy="562" r="84" fill="#343D45" stroke="#9EA8AF" stroke-width="5"/><circle cx="1120" cy="562" r="64" fill="#0C1116" stroke="#6F7A83" stroke-width="4"/><circle cx="1120" cy="562" r="27" fill="none" stroke="{accent}" stroke-width="6"/><circle cx="1120" cy="562" r="12" fill="{accent}"/><path d="M1120 505 L1120 619 M1063 562 L1177 562 M1079 521 L1161 603 M1161 521 L1079 603" stroke="#C9D0D5" stroke-opacity=".65" stroke-width="4"/><path d="M1200 525 Q1220 560 1198 598" fill="none" stroke="#C94A42" stroke-width="10"/></g>
      <path d="M1015 414 Q1082 396 1152 426 L1202 456 Q1130 458 1050 443 Z" fill="#EAF8FF" opacity=".92"/>
      <path d="M1018 420 Q1088 414 1164 438" fill="none" stroke="#FFFFFF" stroke-width="8" opacity=".9"/>
      <path d="M96 634 Q730 722 1425 624" fill="none" stroke="{accent}" stroke-opacity=".34" stroke-width="5"/>
      {focus_marker}
    </g>"""

def _environment(): return '<rect width="1920" height="1080" fill="url(#bg)"/><ellipse cx="930" cy="560" rx="900" ry="450" fill="url(#spot)"/><path d="M0 850 Q500 690 960 790 T1920 740 V1080 H0 Z" fill="url(#road)"/><path d="M0 910 Q500 770 960 860 T1920 810" fill="none" stroke="#2B333C" stroke-width="4"/><g opacity=".24">'+''.join(f'<path d="M{x} 180 L{x-120} 850" stroke="#56616C" stroke-width="2"/>' for x in range(160,1880,220))+'</g>'
def _chips(calls):
    out=[]
    for i,value in enumerate(calls[:4]):
        x=1370;y=240+i*132;out.append(f'<rect x="{x}" y="{y}" width="455" height="100" rx="20" fill="#0C1116" fill-opacity=".92" stroke="#39434E"/>');out.append(_text(value,x+28,y+61,25,650,"start",TEXT));out.append(f'<circle cx="{x+420}" cy="{y+50}" r="7" fill="{ACCENT}"/>')
    return ''.join(out)
def _semantic_overlay(kind,scene):
    if kind=="performance": return f'<path d="M1390 770 H1810" stroke="{LINE}" stroke-width="10"/><path d="M1390 770 L1690 690" stroke="{ACCENT}" stroke-width="10"/><circle cx="1690" cy="690" r="15" fill="{ACCENT}"/>'+_text("PERFORMANCE / RESPONSE",1390,835,20,700,"start",MUTED)
    if kind=="design": return f'<path d="M1380 760 Q1550 650 1810 735" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1550" cy="700" r="11" fill="{ACCENT}"/>'+_text("FORM / AERODYNAMICS",1380,835,20,700,"start",MUTED)
    if kind=="interior": return f'<rect x="1370" y="700" width="455" height="150" rx="20" fill="#0C1116" stroke="#39434E"/><path d="M1410 805 L1480 755 L1560 790 L1640 735 L1775 790" fill="none" stroke="{ACCENT}" stroke-width="6"/>'+_text("CABIN / EXPERIENCE",1395,735,20,700,"start",MUTED)
    if kind=="technology": return '<path d="M1390 760 H1800" stroke="#39434E" stroke-width="4"/>'+''.join(f'<circle cx="{1420+i*125}" cy="760" r="13" fill="{ACCENT}"/>' for i in range(4))+_text("SYSTEM ARCHITECTURE",1390,835,20,700,"start",MUTED)
    if kind=="efficiency": return f'<rect x="1380" y="730" width="430" height="22" rx="11" fill="#303944"/><rect x="1380" y="730" width="280" height="22" rx="11" fill="{ACCENT}"/>'+_text("RANGE / EFFICIENCY",1380,700,20,700,"start",MUTED)
    if kind=="charging": return f'<path d="M1390 760 H1800" stroke="#39434E" stroke-width="8"/><path d="M1390 760 L1550 700 L1700 735 L1800 675" fill="none" stroke="{ACCENT}" stroke-width="7"/>'+_text("CHARGING CURVE",1390,835,20,700,"start",MUTED)
    if kind=="safety": return f'<circle cx="1600" cy="770" r="75" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="1600" cy="770" r="45" fill="none" stroke="#66717C" stroke-width="3"/>'+_text("SAFETY SYSTEMS",1510,870,20,700,"start",MUTED)
    if kind=="price": return f'<path d="M1390 800 H1800" stroke="#39434E" stroke-width="8"/><circle cx="1620" cy="800" r="15" fill="{ACCENT}"/>'+_text("VALUE POSITION",1390,735,20,700,"start",MUTED)
    return _text("AUTOMOTIVE EDITORIAL",1390,815,20,700,"start",MUTED)
def _composition(scene_id:int):
    return [
        ("front_3q",40,180,.94,1,"front"),
        ("low_angle",-25,245,1.02,1,"front"),
        ("front_close",-170,130,1.16,1,"front"),
        ("rear_3q",1540,175,.94,-1,"full"),
        ("wide_scene",130,250,.84,1,"full"),
        ("three_quarter_high",75,95,.80,1,"glass"),
        ("side_profile",-90,305,.88,1,"full"),
        ("rear_close",1460,230,1.04,-1,"wheel"),
    ][(scene_id-1)%8]


def render_scene_svg(scene,topic:str,out:Path)->None:
    out.parent.mkdir(parents=True,exist_ok=True);layout=scene.layout.casefold();kind=_kind(scene);family=_visual_family(kind,scene.id);calls=[str(c) for c in scene.callouts[:4]];intent=str(scene.visual_intent).strip();safe_topic=html.escape(topic[:90]);camera,x,y,scale,mirror,focus=_composition(scene.id);car_transform=f'<g transform="translate({x},{y}) scale({mirror*scale},{scale})">{_car_hero(0,0,1.0,variant=scene.id+len(kind),focus=focus)}</g>';topic_x=1810 if _has_arabic(safe_topic) else 70
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-family="{family}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}" data-camera-angle="{camera}" data-visual-intent="{html.escape(intent[:240])}" data-asset-quality="premium_automotive_editorial_v2" data-motion="camera_push_pan">{_defs()}{_environment()}<path d="M70 105 H1850" stroke="{ACCENT}" stroke-width="3" opacity=".65"/>{_text(safe_topic,topic_x,78,29,700,"start",TEXT)}{car_transform}{_semantic_overlay(kind,scene)}{_chips(calls)}</svg>'''
    out.write_text(svg,encoding='utf-8')
def generate_visuals(story:Story,out_dir:Path=RUN/"scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    for scene in story.scenes: render_scene_svg(scene,story.topic,out_dir/f"scene_{scene.id:02d}.svg")
