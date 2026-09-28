from pathlib import Path
import os
import shutil
import json

import pytest

ROOT = Path(__file__).parents[1]
BLENDER_SCRIPT = ROOT / "scripts" / "blender_automotive_scene.py"
MODEL = ROOT / "scripts" / "automotive_model.py"


def test_renderer_uses_modular_v4_model():
    source = BLENDER_SCRIPT.read_text(encoding="utf-8")
    model = MODEL.read_text(encoding="utf-8")
    assert "from automotive_model import" in source
    assert "blender_eevee_automotive_v4" in model
    assert "body_shell" in model
    assert "AutomotiveGlass" in model


def test_interior_camera_is_dedicated_cockpit_composition():
    source = MODEL.read_text(encoding="utf-8")
    assert '"interior": ((0.15, -2.05, 1.52), (0.85, -0.02, 1.50), 48)' in source
    assert 'pos = (0.35, -1.72, 1.50)' in source
    assert 'lens = 42' in source


def test_interior_render_uses_real_cockpit_geometry():
    source = MODEL.read_text(encoding="utf-8")
    for marker in (
        "dash_main", "instrument_cluster", "infotainment_screen", "center_console",
        "steering_wheel", "driver_seat", "passenger_seat", "door_panel_l", "door_panel_r",
        "center_vent",
    ):
        assert marker in source


def test_exterior_contract_contains_wheels_lights_and_wells():
    source = MODEL.read_text(encoding="utf-8")
    for marker in (
        "wheel_fl_arch", "wheel_fr_arch", "wheel_rl_arch", "wheel_rr_arch",
        "tire_fl", "tire_fr", "tire_rl", "tire_rr",
        "rim_fl", "rim_fr", "rim_rl", "rim_rr",
        "brake_fl", "brake_fr", "brake_rl", "brake_rr",
        "headlamp_l", "headlamp_r", "tail_lamp_l", "tail_lamp_r",
    ):
        assert marker in source


def test_blender_smoke_render(tmp_path):
    if not shutil.which(os.getenv("BLENDER_BIN", "blender")):
        pytest.skip("Blender not installed locally")
    from app.blender_automotive import render_scene_blender

    class Scene:
        id = 1
        visual_intent = "front three quarter smoke"

    out = tmp_path / "car.png"
    result = render_scene_blender(Scene(), "smoke car", out, (640, 360), "front_3q")
    assert out.is_file() and out.stat().st_size > 4096
    assert result["renderer"] == "blender_eevee_automotive_v4"
    meta = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
    assert meta["scene_contract"] == "exterior_automotive_v2"
    assert meta["object_count"] >= 50


def test_blender_interior_smoke_is_not_black(tmp_path):
    if not shutil.which(os.getenv("BLENDER_BIN", "blender")):
        pytest.skip("Blender not installed locally")
    from app.blender_automotive import render_scene_blender

    class Scene:
        id = 20
        visual_intent = "interior cockpit regression"

    out = tmp_path / "interior.png"
    result = render_scene_blender(Scene(), "smoke car", out, (640, 360), "interior")
    from PIL import Image, ImageStat
    with Image.open(out).convert("L") as im:
        assert ImageStat.Stat(im).mean[0] > 8.0
    meta = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
    assert meta["scene_contract"] == "interior_cockpit_v2"
