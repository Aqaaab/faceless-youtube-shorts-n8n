import html
from pathlib import Path
from .core import RUN, Story

W,H=1080,1920
BG="#0B0D10"; PANEL="#151A20"; TEXT="#F5F7FA"; MUTED="#8D949C"; ACCENT="#E8B44A"; GRID="#242A31"


def _text(text,x,y,size,weight=500,anchor="start",fill=TEXT):
    return f'<text x="{x}" y="{y}" font-family="Noto Sans Arabic,Noto Sans,DejaVu Sans,sans-serif" font-size="{size}px" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{html.escape(str(text)[:100])}</text>'


def _car(x=70,y=420,scale=.55,fill="#BFC5CC"):
    return f'''<g transform="translate({x},{y}) scale({scale})"><path d="M110 430 C170 330 310 285 545 280 L930 285 C1080 295 1215 350 1305 430 L1360 505 L1290 565 L160 565 L90 505 Z" fill="{fill}" stroke="{TEXT}" stroke-width="7"/><path d="M350 290 L505 180 L825 185 L1000 295 Z" fill="#1A242F" stroke="{MUTED}" stroke-width="6"/><circle cx="285" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="15"/><circle cx="1135" cy="560" r="92" fill="{BG}" stroke="{MUTED}" stroke-width="15"/><path d="M155 430 H1290" stroke="{ACCENT}" stroke-width="10"/></g>'''


def _panel(label,value,y):
    return f'<rect x="70" y="{y}" width="940" height="105" rx="16" fill="{PANEL}" stroke="#343C45"/>{_text(label,100,y+38,20,650,"start",MUTED)}{_text(value,100,y+78,28,750,"start",ACCENT)}'


def _kind(scene):
    text=(scene.narration+" "+scene.visual_intent).casefold()
    groups={
      "performance":["أداء","قوة","حصان","عزم","تسارع","سرعة","power","torque","horsepower","acceleration","speed"],
      "design":["تصميم","هيكل","شكل","ديناميكية","design","exterior","body","aerodynamic"],
      "interior":["مقصورة","داخلية","مقاعد","شاشة","تابلوه","interior","cabin","seat","dashboard","screen"],
      "technology":["تقنية","تقنيات","حساس","كاميرا","مساعدة","technology","sensor","camera","assist"],
      "efficiency":["مدى","كفاءة","استهلاك","بطارية","كهربائية","range","efficiency","consumption","battery","electric"],
      "safety":["أمان","فرامل","وسادة","تصادم","safety","brake","airbag","collision"],
      "price":["سعر","تكلفة","قيمة","price","cost","value"]}
    for name,words in groups.items():
        if any(w in text for w in words): return name
    return scene.layout.casefold()


def _visual(kind,scene):
    if kind=="performance":
        bars=''.join(f'<text x="{100+i*290}" y="850" font-size="22" fill="{MUTED}">{label}</text><rect x="{100+i*290}" y="875" width="230" height="18" rx="9" fill="#343C45"/><rect x="{100+i*290}" y="875" width="{score*2.3}" height="18" rx="9" fill="{ACCENT}"/>' for i,(label,score) in enumerate([("POWER",88),("TORQUE",76),("RESPONSE",92)]))
        return _car(fill="#D5DADE")+'<circle cx="540" cy="620" r="155" fill="none" stroke="#343C45" stroke-width="18"/><path d="M540 620 L640 535" stroke="'+ACCENT+'" stroke-width="14"/>'+bars
    if kind=="design":
        return _car(fill="#D5DADE")+'<path d="M90 720 C260 560 440 560 610 700 S850 850 1000 660" fill="none" stroke="'+ACCENT+'" stroke-width="8"/><circle cx="610" cy="700" r="14" fill="'+ACCENT+'"/>'+_text("AERODYNAMIC PROFILE",540,805,24,700,"middle",ACCENT)
    if kind=="interior":
        return '<rect x="70" y="350" width="940" height="520" rx="28" fill="'+PANEL+'" stroke="#343C45"/><rect x="110" y="400" width="500" height="330" rx="24" fill="#1A242F" stroke="#343C45"/><rect x="650" y="400" width="310" height="150" rx="18" fill="#1A242F"/><rect x="650" y="580" width="310" height="150" rx="18" fill="#1A242F"/>'+_text("DRIVER",360,570,34,700,"middle",ACCENT)+_text("DISPLAY",805,490,27,700,"middle",ACCENT)+_text("COMFORT",805,670,27,700,"middle",ACCENT)
    if kind=="technology":
        nodes=''.join(f'<circle cx="{180+i*240}" cy="600" r="52" fill="{BG}" stroke="{ACCENT}" stroke-width="5"/>{_text(str(i+1),180+i*240,610,28,750,"middle")}' for i in range(4))
        return '<path d="M180 600 H900" stroke="#343C45" stroke-width="8"/>'+nodes+_text("SENSOR → PROCESSING → CONTROL → RESPONSE",540,760,25,700,"middle",ACCENT)
    if kind=="efficiency":
        return '<rect x="100" y="500" width="880" height="32" rx="16" fill="#343C45"/><rect x="100" y="500" width="690" height="32" rx="16" fill="'+ACCENT+'"/><circle cx="790" cy="516" r="24" fill="'+ACCENT+'"/>'+_text("ENERGY / RANGE",540,430,30,700,"middle",ACCENT)+_text("OPTIMIZED ZONE",790,610,24,650,"middle",MUTED)
    if kind=="safety":
        return '<circle cx="540" cy="600" r="190" fill="none" stroke="'+ACCENT+'" stroke-width="6"/><circle cx="540" cy="600" r="110" fill="none" stroke="#343C45" stroke-width="5"/><path d="M540 410 V790 M350 600 H730" stroke="#343C45" stroke-width="4"/>'+_text("360° PROTECTION",540,865,28,700,"middle",ACCENT)
    if kind=="price":
        bars=[]
        for i,(label,score) in enumerate([("BASE",150),("FEATURES",230),("VALUE",320),("MARKET",205)]):
            fill = ACCENT if i == 2 else "#343C45"
            bars.append(f'<rect x="{100+i*220}" y="{850-score}" width="140" height="{score}" rx="10" fill="{fill}"/>{_text(label,170+i*220,900,20,650,"middle",MUTED)}')
        return ''.join(bars)
    return _car()


def vertical_scene_svg(scene,topic:str,out:Path):
    out.parent.mkdir(parents=True,exist_ok=True)
    kind=_kind(scene); layout=scene.layout.upper(); calls=[str(c) for c in scene.callouts[:3]]
    visual=_visual(kind,scene)
    callout=''.join(_panel("KEY DATA",c,1030+i*120) for i,c in enumerate(calls))
    intent=html.escape(str(scene.visual_intent)[:150])
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="{BG}"/><path d="M70 125 H1010" stroke="{ACCENT}" stroke-width="6"/>{_text(topic,70,88,30,700)}{_text(f"SCENE {scene.id:02d} • {kind.upper()}",1010,88,20,650,"end",MUTED)}<rect x="70" y="160" width="940" height="64" rx="12" fill="{PANEL}" stroke="#343C45"/>{_text(layout,100,203,22,700,"start",ACCENT)}{visual}{callout}<rect x="70" y="1400" width="940" height="330" rx="20" fill="{PANEL}" stroke="#343C45"/><path d="M100 1460 H980" stroke="#343C45" stroke-width="8"/>{_text("WHY IT MATTERS",100,1515,24,700,"start",ACCENT)}{_text(intent,100,1580,25,500)}<rect x="70" y="1780" width="940" height="70" rx="14" fill="#101318" stroke="#343C45"/>{_text("AUTOMOTIVE EDITORIAL • {kind.upper()}",540,1825,20,700,"middle",MUTED)}</svg>'''
    out.write_text(svg,encoding='utf-8')


def generate_vertical_visuals(story:Story,out_dir:Path=RUN/'vertical_scenes'):
    out_dir.mkdir(parents=True,exist_ok=True)
    for s in story.scenes: vertical_scene_svg(s,story.topic,out_dir/f'scene_{s.id:02d}.svg')
