from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
COMMON_ENGLISH_IN_ARABIC = {"the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at", "of", "to", "for", "with", "from", "flame", "fire", "secret", "story", "city", "found", "people", "street"}
ARABIC_COMMON_MISTAKES = {
    "فالقائز": "الفائز",
    "القائز": "الفائز",
    "يسام من": "يعاني من",
    "سيارة دعم قائمة": "سيارة دعم",
}


def probe(path: Path) -> dict:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True)
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
    assert float(video.get("duration") or 0) > 0, f"{path.name} video duration is invalid"
    assert float(audio.get("duration") or 0) > 0, f"{path.name} audio duration is invalid"


def _assert_arabic_quality(story: dict) -> None:
    for index, scene in enumerate(story.get("scenes", []), 1):
        ar = str(scene.get("text_ar", "")).strip()
        assert len(re.findall(r"[\u0600-\u06ff]", ar)) >= 12, f"scene {index} Arabic subtitle is too short or not Arabic"
        latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", ar)]
        leaked = [w for w in latin if w in COMMON_ENGLISH_IN_ARABIC]
        assert not leaked, f"scene {index} Arabic contains ordinary English words: {leaked[:3]}"
        for bad, good in ARABIC_COMMON_MISTAKES.items():
            assert bad not in ar, f"scene {index} Arabic contains known bad phrase '{bad}'; use '{good}'"
        assert "street" not in ar.casefold(), f"scene {index} Arabic contains untranslated 'street'"
        assert not re.search(r"[\u0000-\u001f\u007f]", ar), f"scene {index} Arabic contains control characters"


def _assert_metadata(run_dir: Path, story: dict, plan: dict) -> None:
    metadata_path = run_dir / "metadata.json"
    assert metadata_path.is_file(), "metadata.json is missing"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata.get("title") == story.get("title"), "metadata title does not match story title"
    assert metadata.get("description") == story.get("description"), "metadata description does not match story description"
    assert metadata.get("tags") == story.get("tags"), "metadata tags do not match story tags"
    title = str(metadata.get("title", "")).strip()
    assert title and title.lower() not in {"untitled", "untitled story", "story"}, "metadata title is generic"
    assert len(title) <= 100, "metadata title exceeds YouTube-safe limit"
    tags = [str(x).strip().casefold() for x in metadata.get("tags", []) if str(x).strip()]
    assert len(tags) == len(set(tags)), "metadata tags contain duplicates"
    description = str(metadata.get("description", ""))
    hashtags = re.findall(r"#[A-Za-z0-9_-]+", description)
    assert len(hashtags) == len(set(h.casefold() for h in hashtags)), "metadata description contains duplicate hashtags"
    assert len(hashtags) <= 3, "metadata description contains too many hashtags"
    shorts = plan.get("shorts", [])
    titles = [str(s.get("title", "")).strip() for s in shorts]
    assert all(titles), "one or more Shorts have an empty title"
    assert len(set(titles)) == len(titles), "Short titles must be unique"
    assert all("part " not in t.lower() for t in titles), "Short titles must not use Part numbering"
    assert all(18 <= len(t) <= 68 for t in titles), "Short title is outside strict mobile-safe range"
    assert all(not re.search(r"\b\w+,$", t) for t in titles), "Short title ends with an incomplete comma fragment"
    for index, scene_index in enumerate((1, 7, 13, 19), 1):
        scene = story["scenes"][scene_index - 1]
        assert str(scene.get("beat", "")).lower() == "hook", f"Short {index} opening scene {scene_index} is not hook"
        hook = str(scene.get("text_en", "")).strip()
        assert not re.match(r"^(in|on)\s+\d{4}\b", hook, re.I), f"Short {index} opens with a dry date"


def _assert_short_contract(run_dir: Path, plan: dict) -> None:
    shorts = plan.get("shorts", [])
    for short in shorts:
        scenes = short.get("scenes", [])
        assert len(scenes) == 6, f"Short {short.get('id')} must contain exactly 6 scenes"
        for scene in scenes:
            assert str(scene.get("text_ar", "")).strip(), f"Short {short.get('id')} contains a scene without Arabic subtitle"
        assert int(short["scene_end"]) - int(short["scene_start"]) + 1 == 6, f"Short {short.get('id')} scene range is not 6 scenes"


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
    _assert_arabic_quality(story)

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    assert len(shorts) == CFG["production"]["short_count"]
    expected = [(1, 6), (7, 12), (13, 18), (19, 24)]
    assert [(s["scene_start"], s["scene_end"]) for s in shorts] == expected
    _assert_metadata(run_dir, story, plan)
    _assert_short_contract(run_dir, plan)

    for i in range(1, CFG["production"]["short_count"] + 1):
        path = run_dir / "shorts" / f"short-{i}.mp4"
        assert path.is_file() and path.stat().st_size > 0, f"short-{i}.mp4 missing or empty"
        sd = duration(path)
        slo = CFG["production"]["short_duration_seconds"]["min"]
        shi = CFG["production"]["short_duration_seconds"]["max"]
        assert slo <= sd <= shi, f"short-{i} duration {sd:.2f}s outside {slo}-{shi}s"
        _assert_media(path, width=1080, height=1920, fps=CFG["production"]["short_fps"])

    print(f"PRODUCTION_QA=PASS provider={provider} long={d:.2f}s shorts={len(shorts)} metadata=consistent arabic=strict short_contract=strict")


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/run"))
