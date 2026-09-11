from __future__ import annotations

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
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{html.escape(str(text)[:120])}</text>'


def _kind(scene):
    text=(scene.narration+" "+scene.visual_intent).casefold()
    groups={
        "performance":["power","performance","horsepower","torque","acceleration","speed","أداء","قوة","حصان","عزم","تسارع","سرعة"],
        "design":["design","exterior","body","style","aerodynamic","تصميم","هيكل","شكل","خارجية","ديناميكية"],
        "interior":["interior","cabin","seat","dashboard","screen","مقصورة","داخلية","مقاعد","شاشة","تابلوه"],
        "technology":["technology","tech","software","sensor","camera","assist","تقنية","تقنيات","حساس","كاميرا","مساعدة"],
        "efficiency":["range","efficiency","consumption","battery","electric","مدى","كفاءة","استهلاك","بطارية","كهربائية"],
        "safety":["safety","brake","airbag","collision","أمان","فرامل","وسادة","تصادم"],
        "price":["price","cost","value","سعر","تكلفة","قيمة"],
    }
    for name,words in groups.items():
        if any(w in text for w in words): return name
    return scene.layout.casefold()


def _card(x,y,w,h,label,value):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{PANEL}" stroke="#343C45"/>{_text(label,x+24,y+34,18,650,"start",MUTED)}{_text(value,x+24,y+76,27,700,"start",ACCENT)}'


def _callout_cards(calls):
    parts=[]
    for i,call in enumerate(calls[:5]):
        y=190+i*145
        parts.append(_card(1370,y,450,120,"STORY CALLOUT",call))
    return "".join(parts)


def _car(x=70,y=300,scale=.95):
    return f'''<g transform="translate({x},{y}) scale({scale})"><path d="M110 430 C170 330 310 285 545 280 L930 285 C1080 295 1215 350 1305 430 L1360 505 L1290 565 L160 565 L90 505 Z" fill="#D5DADE" stroke="{TEXT}" stroke-width="6"/><path d="M350 290 L505 180 L825 185 L1000 295 Z" fill="#1A242F" stroke="{MUTED}" stroke-width="5"/><circle cx="285" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/><circle cx="1135" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/><path d="M155 430 H1290" stroke="{ACCENT}" stroke-width="9"/></g>'''


def _visual(kind, scene):
    calls=[str(c) for c in scene.callouts[:5]]
    labels=calls or [scene.visual_intent]
    if kind == "performance":
        return _car()+"<circle cx=\"700\" cy=\"500\" r=\"205\" fill=\"none\" stroke=\"#343C45\" stroke-width=\"18\"/><path d=\"M700 500 L835 395\" stroke=\"#E8B44A\" stroke-width=\"14\"/>" + "".join(_text(c,180+i*360,860,22,650,"middle",ACCENT) for i,c in enumerate(labels[:4]))
    if kind == "design":
        return _car()+"<path d=\"M120 700 C350 470 610 520 850 700 S1160 820 1310 590\" fill=\"none\" stroke=\"#E8B44A\" stroke-width=\"8\"/><circle cx=\"850\" cy=\"700\" r=\"14\" fill=\"#E8B44A\"/>"+_text(labels[0],700,880,24,650,"middle",ACCENT)
    if kind == "interior":
        return '<rect x="100" y="220" width="1160" height="620" rx="28" fill="'+PANEL+'" stroke="#343C45"/><rect x="150" y="280" width="620" height="480" rx="24" fill="#1A242F" stroke="#343C45"/><rect x="820" y="280" width="370" height="220" rx="18" fill="#1A242F"/><rect x="820" y="540" width="370" height="220" rx="18" fill="#1A242F"/>'+_text(labels[0],460,535,30,700,"middle",ACCENT)+_text(labels[1] if len(labels)>1 else "",1005,405,24,700,"middle",ACCENT)+_text(labels[2] if len(labels)>2 else "",1005,665,24,700,"middle",ACCENT)
    if kind == "technology":
        nodes=[]
        for i,label in enumerate(labels[:4]):
            x=210+i*300
            nodes.append(f'<circle cx="{x}" cy="520" r="64" fill="{BG}" stroke="{ACCENT}" stroke-width="6"/>'+_text(str(i+1),x,530,28,750,"middle")+_text(label,x,635,19,600,"middle",MUTED))
        return '<path d="M210 520 H1110" stroke="#343C45" stroke-width="10"/>'+"".join(nodes)
    if kind == "efficiency":
        return '<text x="680" y="320" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="34px" font-weight="700" text-anchor="middle" fill="#E8B44A">ENERGY / RANGE</text><rect x="180" y="470" width="1000" height="44" rx="22" fill="#343C45"/>'+_text(labels[0],680,600,25,650,"middle",ACCENT)
    if kind == "safety":
        return '<circle cx="680" cy="500" r="230" fill="none" stroke="#E8B44A" stroke-width="7"/><circle cx="680" cy="500" r="140" fill="none" stroke="#343C45" stroke-width="6"/><path d="M680 270 V730 M450 500 H910" stroke="#343C45" stroke-width="5"/>'+_text(labels[0],680,825,27,700,"middle",ACCENT)
    if kind == "price":
        return '<path d="M160 760 H1200" stroke="#343C45" stroke-width="12"/><circle cx="700" cy="760" r="28" fill="#E8B44A"/>'+_text(labels[0],700,680,30,700,"middle",ACCENT)
    return _car()


def _layout_overlay(layout, calls):
    if layout == "technical":
        return '<path d="M500 450 L390 180 M780 450 L850 180 M1060 450 L1250 180" stroke="#E8B44A" stroke-width="3"/>' + ''.join(f'<circle cx="{x}" cy="180" r="10" fill="#E8B44A"/>' for x in (390,850,1250))
    if layout == "comparison":
        return '<path d="M960 240 V720" stroke="#343C45" stroke-width="3" stroke-dasharray="10 10"/><rect x="90" y="760" width="760" height="130" rx="14" fill="'+PANEL+'" stroke="#343C45"/><rect x="1070" y="760" width="760" height="130" rx="14" fill="'+PANEL+'" stroke="#343C45"/>'+_text(calls[0] if calls else "THIS CAR",470,835,24,700,"middle",ACCENT)+_text(calls[1] if len(calls)>1 else "REFERENCE",1450,835,24,700,"middle",MUTED)
    if layout == "timeline":
        return '<path d="M120 820 H1800" stroke="#343C45" stroke-width="8"/>' + ''.join(f'<circle cx="{220+i*420}" cy="820" r="18" fill="#E8B44A"/>{_text(c,220+i*420,775,19,650,"middle",MUTED)}' for i,c in enumerate(calls[:4]))
    if layout == "spec":
        return ''.join(f'<rect x="{90+i*255}" y="790" width="220" height="115" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(c,200+i*255,850,21,650,"middle",ACCENT)}' for i,c in enumerate(calls[:5]))
    return ""


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    layout=scene.layout.casefold()
    calls=[str(c) for c in scene.callouts[:5]]
    kind=_kind(scene)
    visual=_visual(kind,scene)
    overlay=_layout_overlay(layout,calls)
    intent=str(scene.visual_intent).strip()
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" data-visual-mode="{html.escape(kind)}" data-layout="{html.escape(layout)}"><rect width="100%" height="100%" fill="{BG}"/><path d="M0 160 H1920" stroke="{GRID}" stroke-width="2"/>{_text(topic,70,90,30,700)}{_text(f"SCENE {scene.id:02d} • {kind.upper()}",1850,90,20,650,"end",MUTED)}<rect x="70" y="120" width="1780" height="70" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(layout.upper(),105,165,22,700,"start",ACCENT)}{visual}{overlay}{_callout_cards(calls)}<rect x="70" y="900" width="1780" height="120" rx="18" fill="{PANEL}" stroke="#343C45"/>{_text("VISUAL INTENT",100,935,18,650,"start",MUTED)}{_text(intent,100,975,22,500)}<rect x="70" y="1035" width="1780" height="20" rx="10" fill="#101318"/></svg>'''
    out.write_text(svg,encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
