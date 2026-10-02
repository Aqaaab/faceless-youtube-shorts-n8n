from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.arabic_font import ensure_ready
from app.blender_automotive import render_scene_blender

ROOT = Path(__file__).parents[1]


def main() -> None:
    if not shutil.which(os.getenv("BLENDER_BIN", "blender")):
        raise SystemExit("Blender is required for temporal smoke")
    os.environ["AUTOMOTIVE_RENDER_MOTION"] = "1"
    os.environ["AUTOMOTIVE_MOTION_FPS"] = "8"
    os.environ["BLENDER_RENDER_SCALE"] = "0.25"
    os.environ["BLENDER_RENDER_MIN_DIM"] = "160"
    # Smoke validates the temporal contract, not final image fidelity.
    # Keep EEVEE sampling intentionally small so this gate stays fast on CPU-only CI.
    os.environ["BLENDER_RENDER_SAMPLES"] = "4"

    work = ROOT / "work" / "temporal-smoke"
    work.mkdir(parents=True, exist_ok=True)

    font = ensure_ready(work / "arabic_font_gate.json", strict=True)
    assert font["passed"] is True

    class Scene:
        id = 1
        duration = 0.25
        visual_intent = "temporal smoke test"

    out = work / "scene.png"
    result = render_scene_blender(Scene(), "smoke car", out, (640, 360), "front_3q", duration=0.25)
    motion = Path(result["motion_output"])
    assert out.is_file() and out.stat().st_size > 4096, out
    assert motion.is_file() and motion.stat().st_size > 32768, motion

    metadata = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
    assert metadata["renderer"] == "blender_eevee_automotive_v5_temporal", metadata
    assert metadata["asset_external"] is False, metadata
    assert metadata["motion"]["enabled"] is True, metadata
    assert int(metadata["motion"]["frames"]) > 1, metadata
    print("TEMPORAL SMOKE PASSED:", json.dumps({
        "renderer": metadata["renderer"],
        "frames": metadata["motion"]["frames"],
        "fps": metadata["motion"]["fps"],
        "motion_size": motion.stat().st_size,
    }))


if __name__ == "__main__":
    main()
