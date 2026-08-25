#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)
OUT = RUN_DIR / "github_assistants.json"

ASSISTANTS = [
    {
        "name": "yt-dlp",
        "repo": "yt-dlp/yt-dlp",
        "role": "YouTube research metadata/search/media retrieval",
        "integration": "research",
        "license": "Unlicense",
        "enabled_by_default": True,
    },
    {
        "name": "PySceneDetect",
        "repo": "Breakthrough/PySceneDetect",
        "role": "content-aware scene detection and representative frame sampling",
        "integration": "optional-render-qa",
        "license": "BSD-3-Clause",
        "enabled_by_default": False,
    },
    {
        "name": "WhisperX",
        "repo": "m-bain/whisperX",
        "role": "word-level transcription/alignment for captions and clip boundaries",
        "integration": "optional-transcript-qa",
        "license": "verify-at-integration-time",
        "enabled_by_default": False,
    },
    {
        "name": "pyannote-audio",
        "repo": "pyannote/pyannote-audio",
        "role": "speaker diarization and speech activity analysis",
        "integration": "optional-audio-qa",
        "license": "MIT",
        "enabled_by_default": False,
    },
    {
        "name": "YT-Shorts-Automator",
        "repo": "edyahcks/YT-Shorts-Automator",
        "role": "local Whisper/Ollama/FFmpeg short-selection patterns",
        "integration": "research-reference",
        "license": "verify-at-integration-time",
        "enabled_by_default": False,
    },
    {
        "name": "clipforge-local",
        "repo": "jayadevrana/clipforge-local",
        "role": "local long-video-to-clip experimentation",
        "integration": "research-reference",
        "license": "verify-at-integration-time",
        "enabled_by_default": False,
    },
]


def main() -> int:
    payload = {
        "schema_version": "1.1",
        "mode": "local_first_optional",
        "assistants": ASSISTANTS,
        "policy": (
            "External assistants augment internal systems only. They cannot replace "
            "Visual QA, Final Feature QA, production contracts, or fail-closed behavior."
        ),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
