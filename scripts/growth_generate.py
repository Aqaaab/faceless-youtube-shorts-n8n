#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

# The previous growth generator could fail the entire pipeline because an AI provider
# returned incomplete JSON or because its editorial refinement hit a provider 429.
# Keep generation fail-safe by using the repository's validated multi-provider
# baseline generator. The publication gate remains responsible for visual QA.
BASE_GENERATOR = Path(__file__).with_name("generate_job.py")


def main() -> None:
    if not BASE_GENERATOR.is_file():
        raise SystemExit(f"Missing baseline generator: {BASE_GENERATOR}")

    result = subprocess.run(
        [sys.executable, str(BASE_GENERATOR)],
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    job_path = RUN_DIR / "job.json"
    if not job_path.is_file() or not job_path.stat().st_size:
        raise SystemExit("Baseline generator did not create job.json")

    data = json.loads(job_path.read_text(encoding="utf-8"))
    scenes = data.get("scenes") or []
    if len(scenes) != 5:
        raise SystemExit("job.json must contain exactly 5 scenes")

    # Renderer-facing fields are deterministic and always derived from scene text.
    data["script"] = " ".join(str(scene["text_en"]).strip() for scene in scenes)
    data["narration"] = data["script"]
    data["hook"] = str(scenes[0]["text_en"]).strip()
    data["pexels_query"] = str(scenes[0]["pexels_query"]).strip()
    data["provider"] = data.get("provider", "baseline-fallback")

    # Deterministic guard for the translation error found in production.
    for index, scene in enumerate(scenes, 1):
        english = str(scene.get("text_en", "")).lower()
        arabic = str(scene.get("text_ar", ""))
        if "chameleon" in english and "حرباء" not in arabic:
            raise SystemExit(
                f"Unsafe Arabic translation in scene {index}: chameleon must translate to حرباء"
            )

    job_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Growth generation completed through resilient validated generator")


if __name__ == "__main__":
    main()
