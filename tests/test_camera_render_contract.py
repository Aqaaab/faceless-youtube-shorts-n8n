from pathlib import Path

from app.story_visuals import _camera_car

def test_camera_presets_have_distinct_renderers():
    cameras = ["front_3q","rear_3q","front_close","interior","low_angle","three_quarter_high","side_profile","rear_close","wide_scene"]
    rendered = [_camera_car(c,0,0,1,1) for c in cameras]
    assert all(rendered)
    assert len(set(rendered)) == len(cameras)

def test_renderer_contains_camera_specific_geometry():
    src = Path("app/story_visuals.py").read_text(encoding="utf-8")
    for marker in ("rear_3q","front_close","interior","low_angle","three_quarter_high","side_profile","rear_close","wide_scene"):
        assert f'camera=="{marker}"' in src

def test_cinematic_shot_plan_has_25_unique_slots():
    src = Path("scripts/automotive_shots.py").read_text(encoding="utf-8")
    start = src.index("SHOT_PLAN=[") + len("SHOT_PLAN=[")
    end = src.index("]\n\nSHOT_LIBRARY", start)
    shots = [x.strip().strip('"') for x in src[start:end].split(",") if x.strip()]
    assert len(shots) == 25
    assert len(set(shots)) == 25
    for shot in shots:
        assert f'"{shot}":' in src
