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


def test_road_follow_is_geometrically_distinct_from_rear_telephoto():
    import ast
    import math

    source = Path("scripts/automotive_shots.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    library_node = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SHOT_LIBRARY" for target in node.targets)
    )
    library = ast.literal_eval(library_node.value)
    road_position, road_target, road_lens = library["road_follow"]
    rear_position, rear_target, rear_lens = library["rear_long_lens"]

    assert road_lens <= 40
    assert road_position[2] <= 1.5
    assert math.dist(road_position, road_target) >= 30
    assert rear_lens >= 90
    assert rear_position[2] >= 2.5
    assert math.dist(rear_position, rear_target) <= 25

    model = Path("scripts/automotive_model.py").read_text(encoding="utf-8")
    assert '"road_follow": "track"' in model
