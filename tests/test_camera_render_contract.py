from pathlib import Path

from app.story_visuals import _camera_car

def test_camera_presets_have_distinct_renderers():
    cameras = ["front_3q","rear_3q","front_close","interior","low_angle","three_quarter_high","side_profile","rear_close"]
    rendered = [_camera_car(c,0,0,1,1) for c in cameras]
    assert all(rendered)
    assert len(set(rendered)) == len(cameras)

def test_renderer_contains_camera_specific_geometry():
    src = Path("app/story_visuals.py").read_text(encoding="utf-8")
    for marker in ("rear_3q","front_close","interior","low_angle","three_quarter_high","side_profile","rear_close"):
        assert f'camera=="{marker}"' in src
