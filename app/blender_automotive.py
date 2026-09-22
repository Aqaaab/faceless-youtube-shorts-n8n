from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER_SCRIPT = ROOT / "scripts" / "blender_automotive_scene.py"
DEFAULT_TIMEOUT = int(os.getenv("BLENDER_RENDER_TIMEOUT", "180"))


def blender_binary() -> str:
    value = os.getenv("BLENDER_BIN", "").strip()
    if value:
        return value
    found = shutil.which("blender")
    if not found:
        raise RuntimeError("Blender renderer is required but no Blender executable was found.")
    return found


def render_scene_blender(scene, topic: str, out: Path, size: tuple[int, int], camera: str) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = map(int, size)
    metadata_path = out.with_suffix(".blender.json")
    cmd = [
        blender_binary(), "--background", "--factory-startup", "--python",
        str(BLENDER_SCRIPT),
    ]
    env = os.environ.copy()
    env.update({
        "AUTOMOTIVE_RENDER_OUTPUT": str(out.resolve()),
        "AUTOMOTIVE_RENDER_METADATA": str(metadata_path.resolve()),
        "AUTOMOTIVE_RENDER_WIDTH": str(width),
        "AUTOMOTIVE_RENDER_HEIGHT": str(height),
        "AUTOMOTIVE_RENDER_CAMERA": str(camera),
        "AUTOMOTIVE_RENDER_SCENE_ID": str(getattr(scene, "id", 0)),
        "AUTOMOTIVE_RENDER_TOPIC": str(topic)[:240],
        "AUTOMOTIVE_RENDER_MODE": str(getattr(scene, "visual_intent", ""))[:240],
    })
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, env=env,
                              timeout=DEFAULT_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Blender render timed out after {DEFAULT_TIMEOUT}s: {camera}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("Blender executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Blender render failed for {camera}:\n{(exc.stdout or '')[-6000:]}") from exc
    if not out.is_file() or out.stat().st_size < 1024:
        raise RuntimeError(f"Blender did not produce a valid PNG: {out}\n{proc.stdout[-6000:]}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Missing/invalid Blender metadata: {metadata_path}") from exc
    if metadata.get("renderer") != "blender_eevee_automotive_v1":
        raise RuntimeError(f"Unexpected renderer metadata: {metadata}")
    if metadata.get("resolution") != [width, height]:
        raise RuntimeError(f"Blender resolution contract failed: {metadata}")
    return {
        "renderer": metadata["renderer"],
        "camera": camera,
        "scene_id": getattr(scene, "id", 0),
        "resolution": [width, height],
        "output": str(out),
        "metadata": str(metadata_path),
        "stdout_tail": proc.stdout[-1200:],
    }
