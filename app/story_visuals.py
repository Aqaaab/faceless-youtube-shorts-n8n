from __future__ import annotations

import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .core import RUN, Story
from .raster_automotive import png_as_data_svg
from .callout_overlay import apply_callout_overlay
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

def _visual_family(kind, scene_id, camera=""):
    # Family labels describe the rendered shot family, not only the narration topic.
    # Topic-only labels collapsed distinct cinematic compositions into 8-9 families,
    # causing the strict visual gate to reject otherwise distinct camera work.
    semantic = {
        "interior": "interior", "technology": "technology",
        "efficiency": "battery", "charging": "charging",
        "safety": "safety", "performance": "performance",
    }
    if kind in semantic:
        return semantic[kind]
    shot_family = {
        "hero_front": "front_3q", "hero_rear": "rear_3q",
        "low_tracking": "low_angle", "side_tracking": "side_profile",
        "high_reveal": "three_quarter_high", "front_macro": "front_close",
        "rear_macro": "rear_close", "wheel_macro": "wheel_detail",
        "road_follow": "wide_scene", "orbit_left": "front_3q",
        "orbit_right": "rear_3q", "top_detail": "design_detail",
        "front_low_wide": "low_angle", "rear_low_wide": "rear_3q",
        "side_front": "side_profile", "side_rear": "side_profile",
        "front_long_lens": "front_close", "rear_long_lens": "rear_close",
        "overhead_reveal": "three_quarter_high", "ground_wide": "wide_scene",
        "charging_threeq": "charging", "city_reveal": "wide_scene",
        "mountain_reveal": "wide_scene", "track_follow": "low_angle",
    }
    return shot_family.get(str(camera), {
        "design": "design_detail", "price": "wide_scene", "hero": "front_3q"
    }.get(kind, "front_3q"))


def _camera_car(camera, x=0, y=0, scale=1.0, mirror=1):
    # Legacy test compatibility: the production renderer is Blender; this helper
    # only exposes the historical camera names without invoking the old raster car.
    if camera=="front_3q": return f"front_3q:{x}:{y}:{scale}:{mirror}"
    if camera=="rear_3q": return f"rear_3q:{x}:{y}:{scale}:{mirror}"
    if camera=="front_close": return f"front_close:{x}:{y}:{scale}:{mirror}"
    if camera=="interior": return f"interior:{x}:{y}:{scale}:{mirror}"
    if camera=="low_angle": return f"low_angle:{x}:{y}:{scale}:{mirror}"
    if camera=="three_quarter_high": return f"three_quarter_high:{x}:{y}:{scale}:{mirror}"
    if camera=="side_profile": return f"side_profile:{x}:{y}:{scale}:{mirror}"
    if camera=="rear_close": return f"rear_close:{x}:{y}:{scale}:{mirror}"
    if camera=="wide_scene": return f"wide_scene:{x}:{y}:{scale}:{mirror}"
    return f"unknown:{camera}:{x}:{y}:{scale}:{mirror}"

def _camera(scene_id):
    # Distribute the full authored shot library across the 25-scene master.
    # The Blender planner may still override a hint for a semantically required
    # cockpit/wheel/charging shot, but a 12-shot cycle capped the possible camera
    # diversity before scene intent was even considered.
    return [
        "hero_front", "hero_rear", "low_tracking", "side_tracking", "high_reveal",
        "front_macro", "rear_macro", "wheel_macro", "cockpit", "road_follow",
        "orbit_left", "orbit_right", "top_detail", "front_low_wide", "rear_low_wide",
        "side_front", "side_rear", "front_long_lens", "rear_long_lens",
        "overhead_reveal", "ground_wide", "charging_threeq", "city_reveal",
        "mountain_reveal", "track_follow",
    ][(scene_id - 1) % 25]

def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(scene)
    camera = "interior" if kind == "interior" else _camera(scene.id)
    png = out.with_suffix(".png")
    info = render_scene_blender(scene, topic, png, (W, H), camera, duration=float(scene.duration))
    apply_callout_overlay(png, scene.callouts, vertical=False)
    svg = png_as_data_svg(
        png,
        W,
        H,
        {
            "visual-family": _visual_family(kind, scene.id, str(info.get("shot", camera))),
            "visual-mode": kind,
            "layout": str(scene.layout).casefold(),
            "camera-angle": str(info.get("shot", camera)),
            "visual-intent": str(scene.visual_intent).strip()[:240],
            "asset-quality": str(info.get("renderer", "blender_eevee_automotive_v5_temporal")),
            "callouts": " | ".join(str(x) for x in scene.callouts[:3]),
            "motion": "blender_keyframed_temporal" if info.get("motion_output") else "static_preview_only",
            "car-layer": "primary",
        },
    )
    out.write_text(svg, encoding="utf-8")


def generate_visuals(story: Story, out_dir: Path = RUN / "scenes"):
    out_dir.mkdir(parents=True, exist_ok=True)
    # Build the persistent asset once before parallel scene renders so two workers
    # cannot race to create the same Blender file.
    from .blender_automotive import ensure_persistent_asset
    ensure_persistent_asset()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda s: render_scene_svg(s, story.topic, out_dir / f"scene_{s.id:02d}.svg"), story.scenes))
