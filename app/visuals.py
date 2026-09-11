import html
import re
from pathlib import Path

from .core import RUN, Story

W, H = 1920, 1080
ACCENT = "#E8B44A"
BG = "#0B0D10"
PANEL = "#151A20"
TEXT = "#F5F7FA"
MUTED = "#8D949C"
GRID = "#242A31"


def _text(text, x, y, size, weight=500, anchor="start", fill=TEXT):
    safe = html.escape(str(text)[:120])
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{safe}</text>'


def _car(x=80, y=315, scale=1.0, fill="#BFC5CC"):
    return f'''<g transform="translate({x},{y}) scale({scale})">
      <path d="M110 430 C170 330 310 285 545 280 L930 285 C1080 295 1215 350 1305 430 L1360 505 L1290 565 L160 565 L90 505 Z" fill="{fill}" stroke="{TEXT}" stroke-width="6"/>
      <path d="M350 290 L505 180 L825 185 L1000 295 Z" fill="#1A242F" stroke="{MUTED}" stroke-width="5"/>
      <path d="M520 190 L520 285 M820 190 L820 285" stroke="{MUTED}" stroke-width="4"/>
      <circle cx="285" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/><circle cx="1135" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/>
      <path d="M155 430 H1290" stroke="{ACCENT}" stroke-width="9"/>
    </g>'''


def _grid():
    return ''.join(f'<path d="M0 {y} H1920" stroke="{GRID}" stroke-width="1" opacity=".65"/>' for y in range(180, 1000, 80))


def _card(x, y, w, h, label, value, fill=PANEL):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" stroke="#343C45"/>{_text(label,x+24,y+34,18,600,"start",MUTED)}{_text(value,x+24,y+76,28,700,"start",ACCENT)}'


def _keywords(scene):
    text=(scene.narration+" "+scene.visual_intent).casefold()
    groups={
        "performance": ["power","performance","horsepower","torque","acceleration","speed","أداء","قوة","حصان","عزم","تسارع","سرعة"],
        "design": ["design","exterior","body","style","aerodynamic","تصميم","هيكل","شكل","خارجية","ديناميكية"],
        "interior": ["interior","cabin","seat","dashboard","screen","مقصورة","داخلية","مقاعد","شاشة","تابلوه"],
        "technology": ["technology","tech","software","sensor","camera","assist","تقنية","تقنيات","حساس","كاميرا","مساعدة"],
        "efficiency": ["range","efficiency","consumption","battery","electric","مدى","كفاءة","استهلاك","بطارية","كهربائية"],
        "safety": ["safety","brake","airbag","collision","أمان","فرامل","وسادة","تصادم"],
        "price": ["price","cost","value","سعر","تكلفة","قيمة"],
    }
    return [name for name, words in groups.items() if any(word in text for word in words)]


def _semantic_visual(scene, kind):
    """Make semantic modes materially different instead of only tagging the same car card."""
    if kind == "performance":
        return _car(fill="#D5DADE") + '<circle cx="700" cy="500" r="210" fill="none" stroke="#343C45" stroke-width="18"/><path d="M700 500 L835 395" stroke="'+ACCENT+'" stroke-width="14"/>'
    if kind == "design":
        return _car(fill="#D5DADE") + '<path d="M130 700 C350 500 600 520 820 690 S1120 850 1270 610" fill="none" stroke="'+ACCENT+'" stroke-width="8"/><circle cx="820" cy="690" r="14" fill="'+ACCENT+'"/>'
    if kind == "interior":
        return '<rect x="120" y="220" width="1120" height="610" rx="28" fill="'+PANEL+'" stroke="#343C45"/><rect x="170" y="280" width="620" height="470" rx="24" fill="#1A242F" stroke="#343C45"/><rect x="840" y="280" width="350" height="210" rx="18" fill="#1A242F"/><rect x="840" y="530" width="350" height="220" rx="18" fill="#1A242F"/>'+_text("DRIVER",480,535,42,700,"middle",ACCENT)+_text("DISPLAY",1015,405,30,700,"middle",ACCENT)+_text("COMFORT",1015,660,30,700,"middle",ACCENT)
    if kind == "technology":
        return '<path d="M180 520 H1180" stroke="#343C45" stroke-width="10"/>'+''.join(f'<circle cx="{220+i*300}" cy="520" r="62" fill="{BG}" stroke="{ACCENT}" stroke-width="6"/>{_text(str(i+1),220+i*300,532,30,750,"middle")}' for i in range(4))+_text("SENSOR → PROCESSING → CONTROL → RESPONSE",680,700,28,700,"middle",ACCENT)
    if kind == "efficiency":
        return '<text x="680" y="330" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="34px" font-weight="700" text-anchor="middle" fill="'+ACCENT+'">ENERGY / RANGE</text><rect x="180" y="470" width="1000" height="44" rx="22" fill="#343C45"/><rect x="180" y="470" width="790" height="44" rx="22" fill="'+ACCENT+'"/><circle cx="970" cy="492" r="30" fill="'+ACCENT+'"/>'+_text("OPTIMIZED ZONE",970,590,25,650,"middle",MUTED)
    if kind == "safety":
        return '<circle cx="680" cy="500" r="230" fill="none" stroke="'+ACCENT+'" stroke-width="7"/><circle cx="680" cy="500" r="140" fill="none" stroke="#343C45" stroke-width="6"/><path d="M680 270 V730 M450 500 H910" stroke="#343C45" stroke-width="5"/>'+_text("360° PROTECTION",680,825,30,700,"middle",ACCENT)
    if kind == "price":
        return ''.join(f'<rect x="{180+i*270}" y="{820-score}" width="170" height="{score}" rx="12" fill="{ACCENT if i==2 else "#343C45"}"/>{_text(label,265+i*270,860,20,650,"middle",MUTED)}' for i,(label,score) in enumerate([("BASE",170),("FEATURES",260),("VALUE",350),("MARKET",230)]))
    return _car()


def _semantic_panel(scene, kinds):
    kind=kinds[0] if kinds else scene.layout.lower()
    if kind == "performance":
        bars=[("POWER",82),("TORQUE",74),("RESPONSE",91)]
        return ''.join(_card(1370,190+i*150,label,str(score)+" / 100") + f'<rect x="1394" y="{295+i*150}" width="380" height="8" rx="4" fill="#343C45"/><rect x="1394" y="{295+i*150}" width="{3.8*score}" height="8" rx="4" fill="{ACCENT}"/>' for i,(label,score) in enumerate(bars))
    if kind == "technology": return _card(1370,190,450,120,"SYSTEM","CONNECTED") + _card(1370,330,450,120,"SENSORS","MULTI-LAYER") + _card(1370,470,450,120,"CONTROL","ADAPTIVE")
    if kind == "efficiency": return _card(1370,190,450,120,"RANGE","LONG DISTANCE") + _card(1370,330,450,120,"ENERGY","OPTIMIZED") + _card(1370,470,450,120,"USAGE","LOW LOSS")
    if kind == "safety": return _card(1370,190,450,120,"ACTIVE","BRAKING") + _card(1370,330,450,120,"VISION","360°") + _card(1370,470,450,120,"PROTECTION","MULTI-ZONE")
    if kind == "interior": return _card(1370,190,450,120,"CABIN","DRIVER FOCUSED") + _card(1370,330,450,120,"DISPLAY","DIGITAL") + _card(1370,470,450,120,"COMFORT","PREMIUM")
    if kind == "price": return _card(1370,190,450,120,"POSITION","MARKET VALUE") + _card(1370,330,450,120,"PACKAGE","FEATURE RICH") + _card(1370,470,450,120,"VERDICT","WORTH CHECKING")
    return _card(1370,190,450,120,"VISUAL MODE",scene.layout.upper()) + _card(1370,330,450,120,"FOCUS","AUTOMOTIVE")


def _semantic_overlay(scene, kinds):
    kind=kinds[0] if kinds else scene.layout.lower()
    if kind == "performance": return '<path d="M150 780 H1240" stroke="#343C45" stroke-width="4"/>' + ''.join(f'<circle cx="{250+i*260}" cy="780" r="16" fill="{ACCENT}"/>{_text(label,250+i*260,835,18,600,"middle",MUTED)}' for i,label in enumerate(["LAUNCH","MID","PEAK","CONTROL"]))
    if kind == "design": return '<path d="M150 760 C360 610 620 610 850 760 S1180 910 1280 700" fill="none" stroke="'+ACCENT+'" stroke-width="5"/><circle cx="850" cy="760" r="12" fill="'+ACCENT+'"/>'
    if kind == "interior": return '<rect x="120" y="735" width="1120" height="170" rx="20" fill="'+PANEL+'" stroke="#343C45"/><rect x="170" y="775" width="360" height="90" rx="12" fill="#1A242F"/><rect x="565" y="775" width="290" height="90" rx="12" fill="#1A242F"/><rect x="890" y="775" width="300" height="90" rx="12" fill="#1A242F"/>' + _text("DRIVER",350,830,22,650,"middle",ACCENT) + _text("DISPLAY",710,830,22,650,"middle",ACCENT) + _text("COMFORT",1040,830,22,650,"middle",ACCENT)
    if kind == "technology": return ''.join(f'<circle cx="{260+i*250}" cy="800" r="42" fill="{BG}" stroke="{ACCENT}" stroke-width="4"/>{_text(str(i+1),260+i*250,810,22,700,"middle")}' for i in range(4))
    if kind == "efficiency": return '<path d="M150 830 H1200" stroke="#343C45" stroke-width="10"/><path d="M150 830 H1010" stroke="'+ACCENT+'" stroke-width="10"/><circle cx="1010" cy="830" r="18" fill="'+ACCENT+'"/>' + _text("OPTIMIZED ZONE",1010,785,20,650,"middle",ACCENT)
    if kind == "safety": return '<circle cx="700" cy="820" r="95" fill="none" stroke="'+ACCENT+'" stroke-width="4"/><circle cx="700" cy="820" r="55" fill="none" stroke="#343C45" stroke-width="3"/><path d="M700 710 V930 M590 820 H810" stroke="#343C45" stroke-width="3"/>'
    if kind == "price": return ''.join(f'<rect x="{180+i*250}" y="{850-score}" width="150" height="{score}" rx="10" fill="{ACCENT if i==2 else "#343C45"}"/>{_text(label,255+i*250,900,18,600,"middle",MUTED)}' for i,(label,score) in enumerate([("BASE",120),("FEATURES",210),("VALUE",290),("MARKET",180)]))
    return '<circle cx="700" cy="790" r="150" fill="none" stroke="#343C45" stroke-width="3" stroke-dasharray="8 14"/><circle cx="700" cy="790" r="95" fill="none" stroke="'+ACCENT+'" stroke-width="4"/>'


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    layout=scene.layout.lower()
    calls=[str(c) for c in scene.callouts[:5]]
    kinds=_keywords(scene)
    kind=kinds[0] if kinds else layout
    visual=_semantic_visual(scene, kind)
    cards=_semantic_panel(scene,kinds)

    if layout == "technical":
        visual += '<path d="M520 470 L420 180 M820 470 L900 180 M1130 470 L1290 180" stroke="#E8B44A" stroke-width="3"/><circle cx="420" cy="180" r="10" fill="#E8B44A"/><circle cx="900" cy="180" r="10" fill="#E8B44A"/><circle cx="1290" cy="180" r="10" fill="#E8B44A"/>'
    elif layout == "comparison":
        visual += '<path d="M960 250 V720" stroke="#343C45" stroke-width="3" stroke-dasharray="10 10"/><rect x="90" y="790" width="760" height="120" rx="14" fill="'+PANEL+'" stroke="#343C45"/><rect x="1070" y="790" width="760" height="120" rx="14" fill="'+PANEL+'" stroke="#343C45"/>' + _text("THIS CAR",470,835,24,700,"middle",ACCENT) + _text("REFERENCE",1450,835,24,700,"middle",MUTED)
    elif layout == "timeline":
        visual += '<path d="M120 820 H1800" stroke="#343C45" stroke-width="8"/>' + ''.join(f'<circle cx="{220+i*420}" cy="820" r="18" fill="{ACCENT}"/>' + _text(str(i+1),220+i*420,775,22,700,"middle") for i in range(4))
    elif layout == "spec":
        visual += ''.join(f'<rect x="{90+i*255}" y="790" width="220" height="115" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(c,200+i*255,835,19,700,"middle",ACCENT)}{_text("SPEC",200+i*255,875,18,500,"middle",MUTED)}' for i,c in enumerate(calls[:4]))

    visual += _semantic_overlay(scene,kinds)
    intent=scene.visual_intent.strip()
    footer=_text(intent,110,1007,22,500)
    header=_text(topic,80,88,34,700)+_text(f"SCENE {scene.id:02d} • {kind.upper()}",1840,88,24,650,"end",MUTED)
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}"><rect width="100%" height="100%" fill="{BG}"/>{_grid()}<path d="M0 140 H1920 M0 950 H1920" stroke="#343C45" stroke-width="2"/>{header}{visual}{cards}<rect x="80" y="965" width="1760" height="64" rx="12" fill="{PANEL}" stroke="#343C45"/>{footer}</svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
