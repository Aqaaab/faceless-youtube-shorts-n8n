#!/usr/bin/env python3
"""Preflight check for the configured Vision provider pool."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

# The workflow executes this file as `python scripts/vision_preflight.py`.
# Import the sibling module directly so the script works without the repository
# root being installed as a Python package.
SCRIPTS_DIR = Path(__file__).resolve().parent
import sys
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import vision_agent  # noqa: E402

PROMPT = '''Vision provider connectivity test. Inspect this simple test image and return ONLY JSON: {"ok":true,"test":"vision"}. Do not use markdown.'''


def make_image(path: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=white:s=320x320:d=0.1",
        "-frames:v", "1", str(path),
    ], check=True, timeout=30)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vision-preflight-") as td:
        image = Path(td) / "test.jpg"
        make_image(image)
        try:
            result = vision_agent.evaluate(PROMPT, [str(image)], kind="preflight")
        except Exception as exc:
            print("VISION_PREFLIGHT_FAIL")
            print(f"{type(exc).__name__}: {exc}")
            return 1

        provider = result.get("provider", "unknown") if isinstance(result, dict) else "unknown"
        print("VISION_PREFLIGHT_PASS")
        print(json.dumps({"passed": True, "provider": provider, "result": result}, ensure_ascii=False, default=str))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
