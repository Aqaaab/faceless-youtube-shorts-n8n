from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from app.blender_automotive import BLENDER_SCRIPT, blender_binary

def test_blender_script_exists():
    assert BLENDER_SCRIPT.is_file()


def test_renderer_invokes_canonical_script_without_python_expr():
    source = (Path(__file__).parents[1] / "app" / "blender_automotive.py").read_text(encoding="utf-8")
    assert "--python-expr" not in source
    assert '"--python", str(BLENDER_SCRIPT)' in source

def test_blender_is_required_in_ci():
    if os.getenv("CI") == "true":
        assert shutil.which(os.getenv("BLENDER_BIN", "blender")) is not None

def test_blender_scene_script_is_isolated():
    source = BLENDER_SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("urllib", "requests", "subprocess", "os.system", "eval(", "exec("):
        assert forbidden not in source

@pytest.mark.skipif(not shutil.which("blender"), reason="Blender not installed locally")
def test_blender_smoke_render(tmp_path):
    from app.blender_automotive import render_scene_blender
    class Scene:
        id = 1
        visual_intent = "smoke render"
    out = tmp_path / "car.png"
    result = render_scene_blender(Scene(), "smoke car", out, (640, 360), "front_3q")
    assert result["renderer"] == "blender_eevee_automotive_v3"
    assert result["resolution"] == [640, 360]
    assert out.is_file() and out.stat().st_size > 4096
    assert out.with_suffix(".blender.json").is_file()

def test_production_visual_modules_use_blender():
    root = Path(__file__).parents[1]
    for name in ("app/story_visuals.py", "app/vertical_visuals.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "render_scene_raster(" not in source
        assert "from .raster_automotive import render_scene_raster" not in source
        assert "render_scene_blender(" in source

def test_renderer_contract_contains_automotive_geometry():
    source = BLENDER_SCRIPT.read_text(encoding="utf-8")
    for marker in ("body_shell", "fender_arch", "steering_wheel", "AutomotiveGlass", "BLENDER_EEVEE_NEXT"):
        assert marker in source


def test_interior_camera_is_outside_opaque_dashboard_volume():
    import ast

    source = (Path(__file__).parents[1] / "scripts" / "blender_automotive_scene.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cameras = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "CAMERAS":
                    cameras = ast.literal_eval(node.value)
                    break
    assert cameras and "interior" in cameras
    (x, y, z), target, lens = cameras["interior"]
    # dash_top occupies x[-0.55, 1.65], y[-0.90, 0.90], z[1.695, 1.765].
    # The camera must not start inside that opaque volume, which previously made
    # interior scene 20 render effectively black.
    inside_dashboard = (-0.55 <= x <= 1.65 and -0.90 <= y <= 0.90 and 1.695 <= z <= 1.765)
    assert not inside_dashboard
    assert y <= -0.90
    assert 1.30 <= z <= 1.70


def test_interior_render_hides_opaque_outer_body_shell():
    source = BLENDER_SCRIPT.read_text(encoding="utf-8")
    assert 'for name in ("body_shell", "cabin_shell", "left_glass", "right_glass", "windshield", "rear_glass", "roof_center"):' in source


def test_blender_interior_smoke_is_not_black(tmp_path):
    if not shutil.which(os.getenv("BLENDER_BIN", "blender")):
        pytest.skip("Blender not installed locally")
    from app.blender_automotive import render_scene_blender

    class Scene:
        id = 20
        visual_intent = "interior cockpit regression"

    out = tmp_path / "interior.png"
    render_scene_blender(Scene(), "smoke car", out, (640, 360), "interior")
    with Image.open(out).convert("L") as im:
        stat = ImageStat.Stat(im)
        hist = im.histogram()
        dark_ratio = sum(hist[:8]) / float(im.width * im.height)
        assert stat.mean[0] >= 8.0
        assert dark_ratio <= 0.82
