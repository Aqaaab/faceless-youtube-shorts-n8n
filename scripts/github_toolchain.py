#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "github_toolchain.json"
RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
OUT = RUN_DIR / "github_toolchain_health.json"


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    checks = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "yt-dlp": shutil.which("yt-dlp") is not None,
        "python": shutil.which("python") is not None or shutil.which("python3") is not None,
    }
    enabled = {
        "scene_detect": bool(os.environ.get("ENABLE_SCENE_DETECT", "0") == "1"),
        "speaker_diarization": bool(os.environ.get("ENABLE_SPEAKER_DIARIZATION", "0") == "1"),
        "word_alignment": bool(os.environ.get("ENABLE_WORD_ALIGNMENT", "0") == "1"),
    }
    payload = {
        "schema_version": "1.0",
        "mode": "local_first_optional",
        "catalog_tools": [x["name"] for x in catalog.get("tools", [])],
        "binary_checks": checks,
        "optional_features": enabled,
        "policy": "Missing optional tools must never silently downgrade production QA; they may only disable their optional stage.",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
