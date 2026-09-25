from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .core import RUN, Story

ROOT = Path(__file__).resolve().parents[1]
BLENDER_SCRIPT = ROOT / "scripts" / "blender_automotive_scene.py"
CAMERAS = (
    "front_3q",
    "low_angle",
    "front_close",
    "rear_3q",
    "wide_scene",
    "three_quarter_high",
    "side_profile",
    "rear_close",
    "interior",
)


def _blender_binary() -> str:
    binary = os.getenv("BLENDER_BIN", "blender")
    if shutil.which(binary) is None:
        raise RuntimeError(
            "Blender is required for production automotive visuals but was not found. "
            "Install Blender or set BLENDER_BIN."
        )
    return binary


def camera_for_scene(scene_id: int, kind: str) -> str:
    if kind == "interior":
        return "interior"
    return CAMERAS[(int(scene_id) - 1) % 8]


def _render_one(args: tuple[str, Path, Path, int, int, int, str, str]) -> None:
    binary, output, metadata, width, height, scene_id, camera, topic = args
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 100_000 and metadata.exists():
        return
    cmd = [
        binary,
        "-b",
        "--factory-startup",
        "--python",
        str(BLENDER_SCRIPT),
        "--",
        "--output",
        str(output),
        "--metadata",
        str(metadata),
        "--width",
        str(width),
        "--height",
        str(height),
        "--camera",
        camera,
        "--scene-id",
        str(scene_id),
        "--topic",
        topic,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).splitlines()[-40:])
        raise RuntimeError(f"Blender scene {scene_id} ({camera}) failed with code {proc.returncode}:\n{tail}")
    if not output.is_file() or output.stat().st_size <= 100_000:
        raise RuntimeError(f"Blender scene {scene_id} produced no valid PNG: {output}")
    if not metadata.is_file():
        raise RuntimeError(f"Blender scene {scene_id} produced no metadata: {metadata}")


def render_blender_scenes(
    story: Story,
    out_dir: Path,
    *,
    width: int,
    height: int,
    vertical: bool = False,
) -> None:
    """Render every production scene from the same deterministic Blender 3D asset."""
    binary = _blender_binary()
    out_dir.mkdir(parents=True, exist_ok=True)
    max_workers = max(1, min(4, int(os.getenv("BLENDER_RENDER_WORKERS", "3"))))
    jobs = []
    for scene in story.scenes:
        kind = "interior" if "interior" in (scene.narration + " " + scene.visual_intent).casefold() or "مقصورة" in (scene.narration + " " + scene.visual_intent) else ""
        camera = camera_for_scene(scene.id, kind)
        output = out_dir / f"scene_{scene.id:02d}.png"
        metadata = out_dir / f"scene_{scene.id:02d}.json"
        jobs.append((binary, output, metadata, width, height, int(scene.id), camera, story.topic))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_render_one, jobs))


def ensure_blender_scene_metadata(out_dir: Path) -> dict:
    metadata = {}
    for path in sorted(out_dir.glob("scene_*.json")):
        metadata[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    if len(metadata) != 25:
        raise RuntimeError(f"Expected Blender metadata for 25 scenes, got {len(metadata)}")
    return metadata
