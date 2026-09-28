from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from automotive_model import build_car, configure_scene, hide_for_interior, lights, set_camera


def main():
    output = os.environ.get("AUTOMOTIVE_RENDER_OUTPUT", "")
    metadata = os.environ.get("AUTOMOTIVE_RENDER_METADATA", "")
    width = int(os.environ.get("AUTOMOTIVE_RENDER_WIDTH", "1920"))
    height = int(os.environ.get("AUTOMOTIVE_RENDER_HEIGHT", "1080"))
    camera = os.environ.get("AUTOMOTIVE_RENDER_CAMERA", "front_3q")
    scene_id = int(os.environ.get("AUTOMOTIVE_RENDER_SCENE_ID", "1"))
    topic = os.environ.get("AUTOMOTIVE_RENDER_TOPIC", "")
    if not output or not metadata:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        p = argparse.ArgumentParser()
        p.add_argument("--output", required=True)
        p.add_argument("--metadata", required=True)
        p.add_argument("--width", type=int, required=True)
        p.add_argument("--height", type=int, required=True)
        p.add_argument("--camera", required=True)
        p.add_argument("--scene-id", type=int, required=True)
        p.add_argument("--topic", default="")
        a = p.parse_args(argv)
        output, metadata, width, height, camera, scene_id, topic = (
            a.output, a.metadata, a.width, a.height, a.camera, a.scene_id, a.topic
        )

    bpy = __import__("bpy")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_car()
    configure_scene(width, height)
    if camera == "interior":
        hide_for_interior()
    set_camera(camera, width, height, scene_id)
    lights(camera, scene_id, (None, None, None))
    scene = bpy.context.scene
    scene.render.filepath = str(Path(output).resolve())
    bpy.ops.render.render(write_still=True)

    meta_path = Path(metadata)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["topic"] = topic
    meta["render_output"] = str(Path(output).resolve())
    meta["render_engine"] = scene.render.engine
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
