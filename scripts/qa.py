from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))


def probe(path: Path) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        text=True,
    )
    return json.loads(raw)


def duration(path: Path) -> float:
    value = probe(path).get("format", {}).get("duration")
    if value is None:
        raise AssertionError(f"unable to read duration: {path}")
    return float(value)


def _provider_allowed(provider: str) -> bool:
    return provider in {"Odysseus", "YouTubeFallback", "GeminiFallback"} or provider.startswith("fallback:")


def _assert_media(path: Path, *, width: int, height: int, fps: int) -> None:
    info = probe(path)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    assert video is not None, f"video stream missing: {path.name}"
    assert audio is not None, f"audio stream missing: {path.name}"
    assert int(video.get("width", 0)) == width, f"{path.name} width is not {width}"
    assert int(video.get("height", 0)) == height, f"{path.name} height is not {height}"
    rate = str(video.get("r_frame_rate", "0/1"))
    numerator, denominator = (int(x) for x in rate.split("/", 1))
    actual_fps = numerator / denominator if denominator else 0
    assert abs(actual_fps - fps) < 0.01, f"{path.name} fps is {actual_fps}, expected {fps}"
    assert int(audio.get("sample_rate", 0)) == 48000, f"{path.name} audio sample rate is not 48000"


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
    _assert_media(video, width=1920, height=1080, fps=30)

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
        _assert_media(path, width=1080, height=1920, fps=CFG["production"]["short_fps"])

    print(f"PRODUCTION_QA=PASS provider={provider} long={d:.2f}s shorts={len(shorts)}")


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/run"))
