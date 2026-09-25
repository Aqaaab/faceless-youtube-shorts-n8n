from pathlib import Path

from app.blender_renderer import camera_for_scene


def test_camera_presets_have_distinct_scene_mapping():
    cameras=[camera_for_scene(i,"") for i in range(1,10)]
    assert len(set(cameras[:8])) == 8
    assert camera_for_scene(1,"interior") == "interior"


def test_story_visuals_uses_blender_renderer():
    src=Path("app/story_visuals.py").read_text(encoding="utf-8")
    assert "render_blender_scenes" in src
    assert "blender_eevee_automotive_v3" in src


def test_production_visual_modules_do_not_call_pillow_car_renderer():
    for path in ("app/story_visuals.py", "app/vertical_visuals.py"):
        src=Path(path).read_text(encoding="utf-8")
        assert "render_scene_raster(" not in src
        assert "render_blender_scenes" in src
