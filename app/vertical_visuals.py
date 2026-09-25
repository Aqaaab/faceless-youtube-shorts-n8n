from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .core import RUN, Story
from .raster_automotive import png_as_data_svg
from .blender_automotive import render_scene_blender
from .story_visuals import _kind

W, H = 1080, 1920
SEMANTIC_MODES = {"performance","design","interior","technology","efficiency","safety","price"}

def _camera(scene_id):
    return ["front_3q","low_angle","front_close","rear_3q","wide_scene","three_quarter_high","side_profile","rear_close"][(scene_id - 1) % 8]

def vertical_scene_svg(scene, topic: str, out: Path) -> None:
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
            "visual-mode": kind,
            "layout": str(scene.layout).casefold(),
            "camera-angle": camera,
            "visual-intent": str(scene.visual_intent).strip()[:240],
            "asset-quality": "blender_eevee_automotive_v3_vertical",
            "motion": "vertical_push_pan",
            "car-layer": "primary",
        },
    )
    out.write_text(svg, encoding="utf-8")

def generate_vertical_visuals(story: Story, out_dir: Path = RUN / "vertical_scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda s: vertical_scene_svg(s, story.topic, out_dir / f"scene_{s.id:02d}.svg"), story.scenes))
