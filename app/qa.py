from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .core import RUN, Story

MIN_LONG = 420.0
MAX_LONG = 900.0
SHORT_MIN = 28.0
SHORT_MAX = 59.0


def _probe(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(p.stdout)


def _duration(path: Path) -> float:
    return float(_probe(path)["format"]["duration"])


def _streams(path: Path, kind: str) -> list[dict]:
    return [s for s in _probe(path).get("streams", []) if s.get("codec_type") == kind]


def _audio_ok(path: Path) -> tuple[bool, str]:
    streams = _streams(path, "audio")
    if not streams:
        return False, "no audio stream"
    codec = streams[0].get("codec_name")
    if codec not in {"aac", "mp3", "opus", "vorbis", "flac"}:
        return False, f"unsupported audio codec {codec}"
    return True, "ok"


def _black_bars(path: Path) -> bool:
    """Return True when cropdetect finds a non-full-frame crop on sampled frames."""
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "2", "-i", str(path), "-frames:v", "30",
             "-vf", "cropdetect=24:16:0", "-f", "null", "-"],
            capture_output=True, text=True, check=False,
        )
        for line in (p.stderr or "").splitlines():
            if "crop=" in line:
                crop = line.split("crop=", 1)[1].split()[0]
                w, h, x, y = (int(v) for v in crop.split(":")[:4])
                info = _streams(path, "video")[0]
                if w < int(info.get("width", 0)) - 8 or h < int(info.get("height", 0)) - 8 or x > 4 or y > 4:
                    return True
    except Exception:
        return True
    return False


def _subtitle_evidence() -> tuple[bool, str]:
    srt = RUN / "arabic.srt"
    marker = RUN / "subtitle_burn.json"
    if not srt.exists() or srt.stat().st_size < 50:
        return False, "Arabic SRT missing/empty"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if not data.get("burned") or data.get("source") != "master.mp4":
            return False, "subtitle burn marker invalid"
        if data.get("subtitle_file") != str(srt):
            return False, "subtitle marker points to wrong SRT"
    except Exception as exc:
        return False, f"subtitle burn evidence missing: {exc}"
    return True, "burn stage completed"


def qa(story: Story, master: Path, shorts: list[Path], report: Path = RUN / "qa_report.json"):
    errors: list[str] = []

    if not master.exists():
        errors.append("master missing")
    if len(story.scenes) != 25:
        errors.append(f"expected exactly 25 scenes, got {len(story.scenes)}")

    ids = [s.id for s in story.scenes]
    if ids != list(range(1, 26)):
        errors.append(f"scene ids must be exactly 1..25, got {ids}")

    planned = sum(float(s.duration) for s in story.scenes)
    if not MIN_LONG <= planned <= MAX_LONG:
        errors.append(f"planned duration {planned:.2f}s outside {MIN_LONG:.0f}-{MAX_LONG:.0f}")

    for s in story.scenes:
        if not s.narration.strip():
            errors.append(f"scene {s.id} has empty narration")
        if not s.visual_intent.strip():
            errors.append(f"scene {s.id} has empty visual intent")
        if float(s.duration) < 5 or float(s.duration) > 60:
            errors.append(f"scene {s.id} duration {s.duration:.2f}s is outside 5-60s")
        if len(s.callouts) > 5:
            errors.append(f"scene {s.id} has more than 5 callouts")

    master_duration = None
    if master.exists():
        try:
            info = _probe(master)
            videos = _streams(master, "video")
            if not videos:
                errors.append("master has no video stream")
            else:
                v = videos[0]
                if (v.get("width"), v.get("height")) != (1920, 1080):
                    errors.append(f"master resolution is {v.get('width')}x{v.get('height')}, expected 1920x1080")
                if v.get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
                    errors.append(f"master pixel format {v.get('pix_fmt')} is not delivery-safe")
            master_duration = _duration(master)
            if not MIN_LONG <= master_duration <= MAX_LONG:
                errors.append(f"master duration {master_duration:.2f}s outside {MIN_LONG:.0f}-{MAX_LONG:.0f}")
            ok, reason = _audio_ok(master)
            if not ok:
                errors.append(f"master audio failed: {reason}")
            if _black_bars(master):
                errors.append("master appears to contain unintended black bars/cropping")
        except Exception as exc:
            errors.append(f"master probe failed: {exc}")

    if len(shorts) != 4:
        errors.append(f"expected exactly 4 shorts, got {len(shorts)}")

    short_reports = []
    for i, path in enumerate(shorts, 1):
        item = {"file": str(path), "exists": path.exists()}
        if not path.exists():
            errors.append(f"short {i} missing")
            short_reports.append(item)
            continue
        try:
            info = _probe(path)
            v = _streams(path, "video")
            d = _duration(path)
            item.update({"duration": d, "resolution": [v[0].get("width"), v[0].get("height")] if v else None})
            if not SHORT_MIN <= d <= SHORT_MAX:
                errors.append(f"short {i} duration {d:.2f}s outside {SHORT_MIN:.0f}-{SHORT_MAX:.0f}")
            if not v or (v[0].get("width"), v[0].get("height")) != (1080, 1920):
                errors.append(f"short {i} must be native 1080x1920")
            if v and v[0].get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
                errors.append(f"short {i} pixel format is not delivery-safe")
            ok, reason = _audio_ok(path)
            if not ok:
                errors.append(f"short {i} audio failed: {reason}")
            if _black_bars(path):
                errors.append(f"short {i} appears to contain unintended black bars/cropping")
            if path.stat().st_size < 100_000:
                errors.append(f"short {i} file is suspiciously small ({path.stat().st_size} bytes)")
        except Exception as exc:
            errors.append(f"short {i} probe failed: {exc}")
        short_reports.append(item)

    sub_ok, sub_reason = _subtitle_evidence()
    if not sub_ok:
        errors.append(sub_reason)

    required = {"title", "description", "tags"}
    missing_meta = [k for k in required if not getattr(story, k, None)]
    if missing_meta:
        errors.append("metadata missing: " + ", ".join(sorted(missing_meta)))
    if len(story.title.strip()) < 12:
        errors.append("title is too weak/short")
    if len(story.description.strip()) < 80:
        errors.append("description is too short for publishing")
    if len(story.tags) < 3:
        errors.append("at least 3 tags are required")

    result = {
        "passed": not errors,
        "errors": errors,
        "scene_count": len(story.scenes),
        "scene_ids_valid": ids == list(range(1, 26)),
        "planned_duration": planned,
        "master_duration": master_duration,
        "shorts": short_reports,
        "subtitle_stage": sub_reason,
        "stock_media": False,
        "legacy_manifest": False,
        "black_bar_gate": "passed" if not any("black bars" in e for e in errors) else "failed",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors))
    return result
