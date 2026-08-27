from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))


def duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def _provider_allowed(provider: str) -> bool:
    return provider in {"Odysseus", "YouTubeFallback", "GeminiFallback"} or provider.startswith("fallback:")


def main(run_dir: Path) -> None:
    story_path = run_dir / "long_story.json"
    video = run_dir / "video.mp4"
    plan_path = run_dir / "shorts_plan.json"
    assert story_path.is_file(), "long_story.json is missing"
    assert video.is_file() and video.stat().st_size > 0, "video.mp4 is missing or empty"
    assert plan_path.is_file(), "shorts_plan.json is missing"

    story = json.loads(story_path.read_text(encoding="utf-8"))
    provider = str(story.get("provider", ""))
    assert _provider_allowed(provider), f"unsupported provider: {provider}"
    assert len(story.get("scenes", [])) == CFG["production"]["long_scene_count"]

    d = duration(video)
    lo = CFG["production"]["long_duration_seconds"]["min"]
    hi = CFG["production"]["long_duration_seconds"]["max"]
    assert lo <= d <= hi, f"long video duration {d:.2f}s outside {lo}-{hi}s"

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    assert len(shorts) == CFG["production"]["short_count"]
    expected = [(1, 6), (7, 12), (13, 18), (19, 24)]
    assert [(s["scene_start"], s["scene_end"]) for s in shorts] == expected

    for i in range(1, CFG["production"]["short_count"] + 1):
        path = run_dir / "shorts" / f"short-{i}.mp4"
        assert path.is_file() and path.stat().st_size > 0, f"short-{i}.mp4 missing or empty"
        sd = duration(path)
        slo = CFG["production"]["short_duration_seconds"]["min"]
        shi = CFG["production"]["short_duration_seconds"]["max"]
        assert slo <= sd <= shi, f"short-{i} duration {sd:.2f}s outside {slo}-{shi}s"

    print(f"PRODUCTION_QA=PASS provider={provider} long={d:.2f}s shorts={len(shorts)}")


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/run"))
