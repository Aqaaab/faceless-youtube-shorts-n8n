from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from automotive_model import render_scene


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
    render_scene(Path(output), Path(metadata), width, height, camera, scene_id, topic)


if __name__ == "__main__":
    main()
