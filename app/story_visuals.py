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

SHOT_FAMILIES = {
    "hero_front": "front_3q", "hero_rear": "rear_3q",
    "low_tracking": "low_angle", "side_tracking": "side_profile",
    "high_reveal": "three_quarter_high", "front_macro": "front_close",
    "rear_macro": "rear_close", "wheel_macro": "wheel_detail",
    "cockpit": "interior", "road_follow": "wide_scene",
    "orbit_left": "design_detail", "orbit_right": "aero",
    "top_detail": "technology", "front_low_wide": "low_angle",
    "rear_low_wide": "low_angle", "side_front": "side_profile",
    "side_rear": "side_profile", "front_long_lens": "front_close",
    "rear_long_lens": "rear_close", "overhead_reveal": "three_quarter_high",
    "ground_wide": "wide_scene", "charging_threeq": "charging",
    "city_reveal": "wide_scene", "mountain_reveal": "wide_scene",
    "track_follow": "performance",
}

def _visual_family(kind, scene_id, shot=""):
    # Family evidence describes the rendered composition, not merely the topic.
    shot = str(shot or "").strip()
    if kind == "interior" or shot == "cockpit":
        return "interior"
    if kind == "charging" and shot == "charging_threeq":
        return "charging"
    if kind == "technology" and shot == "top_detail":
        return "technology"
    if kind == "performance" and shot == "track_follow":
        return "performance"
    return SHOT_FAMILIES.get(
        shot,
        {"performance":"performance","interior":"interior","technology":"technology",
         "efficiency":"battery","charging":"charging","safety":"safety",
         "price":"wide_scene","design":"design_detail","hero":"front_3q"}.get(kind,"front_3q"),
    )


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
    # Use the complete authored shot library. A 12-shot cycle yielded only 11
    # effective cameras because interior scenes intentionally resolve to cockpit.
    from .production_contract import SCENE_COUNT
    shot_plan = (
        "hero_front", "hero_rear", "low_tracking", "side_tracking", "high_reveal",
        "front_macro", "rear_macro", "wheel_macro", "cockpit", "road_follow",
        "orbit_left", "orbit_right", "top_detail", "front_low_wide", "rear_low_wide",
        "side_front", "side_rear", "front_long_lens", "rear_long_lens", "overhead_reveal",
        "ground_wide", "charging_threeq", "city_reveal", "mountain_reveal", "track_follow",
    )
    if scene_id < 1:
        raise ValueError("scene_id must be positive")
    return shot_plan[(scene_id - 1) % min(SCENE_COUNT, len(shot_plan))]

def render_scene_svg(scene, topic: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _kind(scene)
    camera = "interior" if kind == "interior" else _camera(scene.id)
    png = out.with_suffix(".png")
    info = render_scene_blender(scene, topic, png, (W, H), camera, duration=float(scene.duration))
    shot = str(info.get("shot", camera))
    apply_callout_overlay(png, scene.callouts, vertical=False)
    svg = png_as_data_svg(
        png,
        W,
        H,
        {
            "visual-family": _visual_family(kind, scene.id, shot),
            "visual-mode": kind,
            "layout": str(scene.layout).casefold(),
            "camera-angle": shot,
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
