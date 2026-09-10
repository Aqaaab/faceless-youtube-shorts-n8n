import html
from pathlib import Path
from .core import RUN, Story

W,H=1080,1920
BG="#0B0D10"; PANEL="#151A20"; TEXT="#F5F7FA"; MUTED="#8D949C"; ACCENT="#E8B44A"


def _text(text,x,y,size,weight=500,anchor="start",fill=TEXT):
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{html.escape(str(text)[:100])}</text>'


def _car():
    return '''<g transform="translate(-145,470) scale(.72)"><path d="M110 430 C170 330 310 285 545 280 L930 285 C1080 295 1215 350 1305 430 L1360 505 L1290 565 L160 565 L90 505 Z" fill="#BFC5CC" stroke="#F5F7FA" stroke-width="7"/><path d="M350 290 L505 180 L825 185 L1000 295 Z" fill="#1A242F" stroke="#8D949C" stroke-width="6"/><circle cx="285" cy="560" r="92" fill="#0B0D10" stroke="#8D949C" stroke-width="15"/><circle cx="1135" cy="560" r="92" fill="#0B0D10" stroke="#8D949C" stroke-width="15"/><path d="M155 430 H1290" stroke="#E8B44A" stroke-width="10"/></g>'''


def vertical_scene_svg(scene,topic:str,out:Path):
    out.parent.mkdir(parents=True,exist_ok=True)
    cards=''.join(f'<rect x="70" y="1080" width="940" height="76" rx="12" fill="{PANEL}" stroke="#343C45"/><circle cx="105" cy="1118" r="6" fill="{ACCENT}"/>{_text(c,130,1127,25,650)}' for c in scene.callouts[:1])
    intent=html.escape(str(scene.visual_intent)[:180])
    layout=scene.layout.upper()
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="{BG}"/><path d="M70 125 H1010" stroke="{ACCENT}" stroke-width="6"/>{_text(topic,70,88,30,700)}{_text(f"SCENE {scene.id:02d}",1010,88,21,650,"end",MUTED)}<rect x="70" y="160" width="940" height="64" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(layout,105,203,23,700,"start",ACCENT)}{_car()}<path d="M70 1000 H1010" stroke="#343C45" stroke-width="2"/>{cards}<rect x="70" y="1250" width="940" height="440" rx="20" fill="{PANEL}" stroke="#343C45"/><rect x="95" y="1280" width="890" height="10" rx="5" fill="#343C45"/><rect x="95" y="1280" width="{min(820,max(180,scene.id*32))}" height="10" rx="5" fill="{ACCENT}"/>{_text("WHY IT MATTERS",105,1360,24,700,"start",ACCENT)}{_text(intent,105,1425,27,500)}<rect x="70" y="1740" width="940" height="92" rx="16" fill="#101318" stroke="#343C45"/>{_text("AUTOMOTIVE EDITORIAL",540,1797,23,700,"middle",MUTED)}</svg>'''
    out.write_text(svg,encoding='utf-8')


def generate_vertical_visuals(story:Story,out_dir:Path=RUN/'vertical_scenes'):
    out_dir.mkdir(parents=True,exist_ok=True)
    for s in story.scenes: vertical_scene_svg(s,story.topic,out_dir/f'scene_{s.id:02d}.svg')
