from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app.blender_automotive import BLENDER_SCRIPT, blender_binary


def test_blender_script_exists():
    assert BLENDER_SCRIPT.is_file()


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

    out = tmp_path / "car.png"
    result = render_scene_blender(Scene(), "smoke car", out, (640, 360), "front_3q")
    assert result["renderer"] == "blender_eevee_automotive_v1"
    assert result["resolution"] == [640, 360]
    assert out.is_file() and out.stat().st_size > 1024
    assert out.with_suffix(".blender.json").is_file()
