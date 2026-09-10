import html, json, math
from pathlib import Path
from .core import RUN, Story

W, H = 1920, 1080

def _svg_text(text: str, x: int, y: int, size: int, weight: int = 500, anchor: str = "start") -> str:
    safe = html.escape(text[:110])
    return f'<text x="{x}" y="{y}" font-family="DejaVu Sans, sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="#F5F7FA">{safe}</text>'


def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    accent = "#E8B44A"
    bg = "#0B0D10"
    layout = scene.layout.lower()
    # Original vector artwork: no stock-media provider or legacy asset lookup.
    car_x, car_y = 430, 560
    body = '<path d="M270 620 C340 510 470 470 690 465 L1160 470 C1290 480 1430 535 1530 620 L1580 700 L1510 760 L390 760 L290 705 Z" fill="#BFC5CC" stroke="#F5F7FA" stroke-width="6"/>'
    wheels = '<circle cx="500" cy="755" r="105" fill="#0B0D10" stroke="#8D949C" stroke-width="14"/><circle cx="1370" cy="755" r="105" fill="#0B0D10" stroke="#8D949C" stroke-width="14"/>'
    glass = '<path d="M580 475 L760 355 L1110 360 L1280 480 Z" fill="#1A242F" stroke="#8D949C" stroke-width="5"/>'
    if "technical" in layout or "spec" in layout or scene.callouts:
        extras = ''.join(f'<rect x="1380" y="{170+i*92}" width="430" height="66" rx="10" fill="#151A20" stroke="#343C45"/><circle cx="1415" cy="203" r="7" fill="{accent}"/>{_svg_text(c,1450,213,25,650)}' for i,c in enumerate(scene.callouts[:5]))
    else:
        extras = f'<rect x="1320" y="170" width="500" height="150" rx="18" fill="#151A20" stroke="#343C45"/>{_svg_text("AUTOMOTIVE EDITORIAL",1570,225,28,700,"middle")}{_svg_text("DESIGNED SCENE",1570,275,22,400,"middle")}'
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="{bg}"/><path d="M0 140 H1920" stroke="#242A31" stroke-width="2"/><path d="M0 930 H1920" stroke="#242A31" stroke-width="2"/>{_svg_text(topic,90,90,36,700)}{_svg_text(f"SCENE {scene.id:02d}",1830,90,25,600,"end")}<g>{body}{wheels}{glass}<path d="M330 625 H1510" stroke="{accent}" stroke-width="8"/><path d="M760 470 V360 M1110 470 V360" stroke="#8D949C" stroke-width="4"/></g>{extras}<rect x="90" y="840" width="1120" height="80" rx="14" fill="#151A20" stroke="#343C45"/>{_svg_text(scene.visual_intent,125,892,25,500)}</svg>'''
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in story.scenes:
        render_scene_svg(s, story.topic, out_dir / f"scene_{s.id:02d}.svg")
