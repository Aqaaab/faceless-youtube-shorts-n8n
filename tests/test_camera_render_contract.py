from pathlib import Path

from app.blender_renderer import camera_for_scene


def test_camera_presets_have_distinct_scene_mapping():
    cameras=[camera_for_scene(i,"") for i in range(1,10)]
    assert len(set(cameras[:8])) == 8
    assert cameras[8] == "interior"


def test_story_visuals_uses_blender_renderer():
    src=Path("app/story_visuals.py").read_text(encoding="utf-8")
    assert "render_blender_scenes" in src
    assert "blender_eevee_automotive_v3" in src
