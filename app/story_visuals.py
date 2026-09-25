from __future__ import annotations

import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .core import RUN, Story
from .raster_automotive import png_as_data_svg
from .blender_automotive import render_scene_blender

W, H = 1920, 1080

def _kind(scene):
    text = (scene.narration + " " + scene.visual_intent).casefold()
    groups = {
        "performance": ["power","performance","horsepower","torque","acceleration","speed","أداء","قوة","حصان","عزم","تسارع","سرعة"],
        "design": ["design","exterior","body","style","aerodynamic","تصميم","هيكل","شكل","خارجية","ديناميكية"],
        "interior": ["interior","cabin","seat","dashboard","screen","مقصورة","داخلية","مقاعد","شاشة","تابلوه"],
        "technology": ["technology","tech","software","sensor","camera","assist","تقنية","تقنيات","حساس","كاميرا","مساعدة"],
        "efficiency": ["range","efficiency","consumption","battery","electric","مدى","كفاءة","استهلاك","بطارية","كهربائية"],
        "charging": ["charging","charge","شحن","الشحن"],
        "safety": ["safety","brake","airbag","collision","أمان","فرامل","وسادة","تصادم"],
        "price": ["price","cost","value","سعر","تكلفة","قيمة"],
    }
    for name, words in groups.items():
        if any(w in text for w in words):
            return name
    return "hero"

def _visual_family(kind, scene_id):
    if kind == "design":
        return "aero" if scene_id in {12,19} else ("wide_scene" if scene_id == 23 else "design_detail")
    return {"performance":"performance","interior":"interior","technology":"technology","efficiency":"battery","charging":"charging","safety":"safety","price":"wide_scene","hero":"front_3q"}.get(kind,"front_3q")

def _camera(scene_id):
    return ["front_3q","low_angle","front_close","rear_3q","wide_scene","three_quarter_high","side_profile","rear_close"][(scene_id - 1) % 8]

def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(scene)
    camera = "interior" if kind == "interior" else _camera(scene.id)
    png = out.with_suffix(".png")
    render_scene_blender(scene, topic, png, (W, H), camera)
    svg = png_as_data_svg(
        png,
        W,
        H,
        {
            "visual-family": _visual_family(kind, scene.id),
            "visual-mode": kind,
            "layout": str(scene.layout).casefold(),
            "camera-angle": camera,
            "visual-intent": str(scene.visual_intent).strip()[:240],
            "asset-quality": "blender_eevee_automotive_v3",
            "motion": "camera_push_pan",
            "car-layer": "primary",
        },
    )
    out.write_text(svg, encoding="utf-8")

def generate_visuals(story: Story, out_dir: Path = RUN / "scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda s: render_scene_svg(s, story.topic, out_dir / f"scene_{s.id:02d}.svg"), story.scenes))
