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


def test_road_follow_geometry_is_distinct_from_rear_telephoto():
    import ast
    import math

    source = Path("scripts/automotive_shots.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    assignment = next(
        node for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SHOT_LIBRARY" for target in node.targets)
    )
    shots = ast.literal_eval(assignment.value)
    road_pos, road_target, road_lens = shots["road_follow"]
    rear_pos, rear_target, rear_lens = shots["rear_long_lens"]

    road_distance = math.dist(road_pos, road_target)
    rear_distance = math.dist(rear_pos, rear_target)
    assert road_lens <= 50, "road_follow must remain a wide environmental chase shot"
    assert rear_lens >= 90, "rear_long_lens must remain a tight telephoto shot"
    assert road_distance >= rear_distance * 1.5, "camera separation must be structural, not metadata-only"
