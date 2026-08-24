#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, tempfile
from pathlib import Path
from scripts import vision_agent

PROMPT = '''Vision provider connectivity test. Inspect this simple test image and return ONLY JSON: {"ok":true,"test":"vision"}. Do not use markdown.'''

def make_image(path: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=white:s=320x320:d=0.1",
        "-frames:v", "1", str(path)
    ], check=True, timeout=30)

def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vision-preflight-") as td:
        image = Path(td) / "test.jpg"
        make_image(image)
        try:
            result = vision_agent.evaluate(PROMPT, [str(image)], kind="preflight")
        except Exception as exc:
            print("VISION_PREFLIGHT_FAIL")
            print(str(exc))
            return 1
        provider = result.get("provider", "unknown") if isinstance(result, dict) else "unknown"
        print(json.dumps({"passed": True, "provider": provider, "result": result}, ensure_ascii=False))
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
