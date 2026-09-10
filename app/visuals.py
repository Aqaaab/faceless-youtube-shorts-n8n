import html
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
    return f'<text x="{x}" y="{y}" font-family="Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{safe}</text>'


def _car(x=120, y=300, scale=1.0, fill="#BFC5CC"):
    return f'''<g transform="translate({x},{y}) scale({scale})">
      <path d="M110 430 C170 330 310 285 545 280 L930 285 C1080 295 1215 350 1305 430 L1360 505 L1290 565 L160 565 L90 505 Z" fill="{fill}" stroke="{TEXT}" stroke-width="6"/>
      <path d="M350 290 L505 180 L825 185 L1000 295 Z" fill="#1A242F" stroke="{MUTED}" stroke-width="5"/>
      <path d="M520 190 L520 285 M820 190 L820 285" stroke="{MUTED}" stroke-width="4"/>
      <circle cx="285" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/><circle cx="1135" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="14"/>
      <path d="M155 430 H1290" stroke="{ACCENT}" stroke-width="9"/>
    </g>'''


def _grid():
    return ''.join(f'<path d="M0 {y} H1920" stroke="{GRID}" stroke-width="1" opacity=".65"/>' for y in range(180, 1000, 80))


def _callout_card(text, i):
    y=185+i*88
    return f'<rect x="1370" y="{y}" width="450" height="64" rx="10" fill="{PANEL}" stroke="#343C45"/><circle cx="1405" cy="{y+32}" r="6" fill="{ACCENT}"/>{_text(text,1430,y+40,23,650)}'


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    layout=scene.layout.lower(); calls=[str(c) for c in scene.callouts[:5]]
    cards=''.join(_callout_card(c,i) for i,c in enumerate(calls))
    if not cards:
        cards=f'<rect x="1360" y="190" width="460" height="210" rx="18" fill="{PANEL}" stroke="#343C45"/>{_text(layout.upper(),1590,270,34,700,"middle",ACCENT)}{_text("AUTOMOTIVE SYSTEM",1590,325,22,600,"middle",MUTED)}'
    visual=_car()
    if layout == "technical":
        visual += '<path d="M520 470 L420 180 M820 470 L900 180 M1130 470 L1290 180" stroke="#E8B44A" stroke-width="3"/><circle cx="420" cy="180" r="10" fill="#E8B44A"/><circle cx="900" cy="180" r="10" fill="#E8B44A"/><circle cx="1290" cy="180" r="10" fill="#E8B44A"/>'
    elif layout == "spec":
        visual += ''.join(f'<rect x="{90+i*255}" y="790" width="220" height="115" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(c,200+i*255,835,19,700,"middle",ACCENT)}{_text("SPEC",200+i*255,875,18,500,"middle",MUTED)}' for i,c in enumerate(calls[:4]))
    elif layout == "comparison":
        visual += f'<path d="M960 250 V720" stroke="#343C45" stroke-width="3" stroke-dasharray="10 10"/><rect x="90" y="790" width="760" height="120" rx="14" fill="{PANEL}" stroke="#343C45"/><rect x="1070" y="790" width="760" height="120" rx="14" fill="{PANEL}" stroke="#343C45"/>{_text("THIS CAR",470,835,24,700,"middle",ACCENT)}{_text("REFERENCE",1450,835,24,700,"middle",MUTED)}'
    elif layout == "diagram":
        visual += ''.join(f'<path d="M{260+i*300} 760 C{330+i*300} 650 {390+i*300} 650 {460+i*300} 760" fill="none" stroke="{ACCENT}" stroke-width="5"/><circle cx="{260+i*300}" cy="760" r="12" fill="{ACCENT}"/>' for i in range(4))
    elif layout == "timeline":
        visual += '<path d="M120 820 H1800" stroke="#343C45" stroke-width="8"/>' + ''.join(f'<circle cx="{220+i*420}" cy="820" r="18" fill="{ACCENT}"/>' + _text(str(i+1),220+i*420,775,22,700,"middle") for i in range(4))
    else:
        visual += '<circle cx="960" cy="510" r="250" fill="none" stroke="#343C45" stroke-width="2" stroke-dasharray="8 14"/><circle cx="960" cy="510" r="175" fill="none" stroke="#E8B44A" stroke-width="3" opacity=".7"/>'
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="{BG}"/>{_grid()}<path d="M0 140 H1920 M0 950 H1920" stroke="#343C45" stroke-width="2"/>{_text(topic,80,88,34,700)}{_text(f"SCENE {scene.id:02d}",1840,88,24,650,"end",MUTED)}{visual}{cards}<rect x="80" y="965" width="1760" height="64" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(scene.visual_intent,110,1007,22,500)}</svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in story.scenes:
        render_scene_svg(scene, story.topic, out_dir / f"scene_{scene.id:02d}.svg")
