import html
from pathlib import Path
from .core import RUN, Story

def vertical_scene_svg(scene, topic: str, out: Path):
    out.parent.mkdir(parents=True,exist_ok=True)
    callouts=''.join(f'<rect x="70" y="{1040+i*105}" width="940" height="78" rx="12" fill="#151A20" stroke="#343C45"/><text x="105" y="{1090+i*105}" font-family="DejaVu Sans" font-size="26" fill="#F5F7FA">{html.escape(c[:42])}</text>' for i,c in enumerate(scene.callouts[:4]))
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920"><rect width="1080" height="1920" fill="#0B0D10"/><path d="M70 120 H1010" stroke="#E8B44A" stroke-width="6"/><text x="70" y="85" font-family="DejaVu Sans" font-size="30" font-weight="700" fill="#F5F7FA">{html.escape(topic[:45])}</text><text x="1010" y="85" text-anchor="end" font-family="DejaVu Sans" font-size="22" fill="#8D949C">SCENE {scene.id:02d}</text><g transform="translate(-210,380) scale(.76)"><path d="M270 620 C340 510 470 470 690 465 L1160 470 C1290 480 1430 535 1530 620 L1580 700 L1510 760 L390 760 L290 705 Z" fill="#BFC5CC" stroke="#F5F7FA" stroke-width="6"/><circle cx="500" cy="755" r="105" fill="#0B0D10" stroke="#8D949C" stroke-width="14"/><circle cx="1370" cy="755" r="105" fill="#0B0D10" stroke="#8D949C" stroke-width="14"/><path d="M580 475 L760 355 L1110 360 L1280 480 Z" fill="#1A242F" stroke="#8D949C" stroke-width="5"/><path d="M330 625 H1510" stroke="#E8B44A" stroke-width="8"/></g>{callouts}<rect x="70" y="1570" width="940" height="250" rx="18" fill="#151A20" stroke="#343C45"/><text x="105" y="1640" font-family="DejaVu Sans" font-size="24" font-weight="700" fill="#E8B44A">VISUAL INTENT</text><foreignObject x="105" y="1670" width="870" height="120"><div xmlns="http://www.w3.org/1999/xhtml" style="font:24px DejaVu Sans;color:#F5F7FA">{html.escape(scene.visual_intent[:220])}</div></foreignObject></svg>'''
    out.write_text(svg,encoding='utf-8')

def generate_vertical_visuals(story: Story, out_dir: Path=RUN/"vertical_scenes"):
    out_dir.mkdir(parents=True,exist_ok=True)
    for s in story.scenes: vertical_scene_svg(s,story.topic,out_dir/f"scene_{s.id:02d}.svg")
