from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from .core import RUN, Story
from .story_visuals import _kind

MASTER_SIZE = (1920, 1080)
SHORT_SIZE = (1080, 1920)
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
MIN_WPS, MAX_WPS = 1.60, 2.10
MIN_LONG, MAX_LONG = 420.0, 900.0
SHORT_MIN, SHORT_MAX = 28.0, 59.0
MIN_PUBLISH_SCORE = 9.0
DEBUG_MARKERS = ("MODE_FACT_SOURCE_REQUIRED", "hud_only", "STORY CALLOUT", "VISUAL INTENT", "WHY IT MATTERS")


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _probe(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    return json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def _streams(path: Path, kind: str) -> list[dict]:
    return [s for s in _probe(path).get("streams", []) if s.get("codec_type") == kind]


def _duration(path: Path) -> float:
    return float(_probe(path)["format"]["duration"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _arabic(text: str) -> int:
    return len(re.findall(r"[\u0600-\u06ff]", str(text)))


def _image_metrics(path: Path) -> dict:
    with Image.open(path).convert("RGB") as image:
        small = image.resize((64, 64))
        stat = ImageStat.Stat(small)
        mean = sum(stat.mean) / 3.0
        variance = sum(stat.var) / 3.0
        edges = small.filter(ImageFilter.FIND_EDGES)
        edge_mean = sum(ImageStat.Stat(edges).mean) / 3.0
        pixels = list(small.getdata())
        corner = pixels[0]
        non_background = sum(1 for pixel in pixels if sum(abs(pixel[i] - corner[i]) for i in range(3)) > 24) / len(pixels)
        luma = [sum(pixel) / 3.0 for pixel in pixels]
        border = []
        for x in range(64):
            for y in range(4):
                border.extend((luma[y * 64 + x], luma[(63 - y) * 64 + x]))
        for y in range(4, 60):
            border.extend((luma[y * 64], luma[y * 64 + 63]))
        roi = small.crop((3, 10, 57, 53))
        roi_edge_mean = sum(ImageStat.Stat(roi.filter(ImageFilter.FIND_EDGES)).mean) / 3.0
        payload = bytes(int(max(0, min(255, value))) for value in luma)
        return {
            "width": image.width,
            "height": image.height,
            "mean_luma": round(mean, 2),
            "variance": round(variance, 2),
            "edge_mean": round(edge_mean, 2),
            "non_background_ratio": round(non_background, 4),
            "car_roi_edge_mean": round(roi_edge_mean, 2),
            "border_mean_luma": round(sum(border) / len(border), 2),
            "center_luma": round(luma[16 * 64 + 32], 2),
            "pixel_hash": hashlib.sha256(payload).hexdigest(),
        }


def _sample_frame(video: Path, seconds: float, out: Path) -> None:
    result = _run(["ffmpeg", "-y", "-ss", str(max(0.0, seconds)), "-i", str(video), "-frames:v", "1", "-vf", "format=rgb24", str(out)], False)
    if result.returncode or not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"failed to sample {video} at {seconds:.2f}s")


def _sample_video(video: Path, vertical: bool = False) -> dict:
    duration = _duration(video)
    points = sorted(set(max(0.0, min(duration - 0.05, point)) for point in (0.5, duration * 0.33, duration * 0.66, max(0.0, duration - 0.5))))
    temp = Path(tempfile.mkdtemp(prefix="artifact-samples-"))
    try:
        frames = []
        for index, point in enumerate(points):
            frame = temp / f"{index}.png"
            _sample_frame(video, point, frame)
            frames.append(_image_metrics(frame))
        return {
            "frames": frames,
            "average_non_background_ratio": round(sum(x["non_background_ratio"] for x in frames) / len(frames), 4),
            "average_edge_mean": round(sum(x["edge_mean"] for x in frames) / len(frames), 2),
            "unique_hashes": len({x["pixel_hash"] for x in frames}),
            "vertical": vertical,
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def _audio_quality(path: Path) -> tuple[bool, str]:
    if not _streams(path, "audio"):
        return False, "no audio stream"
    level = _run(["ffmpeg", "-v", "error", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], False).stderr or ""
    mean = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", level)
    peak = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", level)
    if mean and float(mean.group(1)) < -32:
        return False, f"mean level too low ({mean.group(1)} dB)"
    if peak and float(peak.group(1)) > -0.2:
        return False, f"peak too high ({peak.group(1)} dB)"
    silence = _run(["ffmpeg", "-v", "error", "-i", str(path), "-af", "silencedetect=noise=-42dB:d=1.5", "-f", "null", "-"], False).stderr or ""
    starts = len(re.findall(r"silence_start", silence))
    ends = len(re.findall(r"silence_end", silence))
    if starts > 3 or ends > 3:
        return False, f"extended silence detected ({starts} intervals)"
    return True, "ok"


def _black_bars(path: Path) -> tuple[bool, str]:
    sample = _sample_video(path)
    for index, frame in enumerate(sample["frames"]):
        if frame["border_mean_luma"] < 2.0 and frame["center_luma"] - frame["border_mean_luma"] > 24.0:
            return True, f"sample {index} has a near-black border"
    return False, "ok"


def _srt(path: Path, expected: int) -> tuple[bool, str]:
    if not path.is_file() or path.stat().st_size < 50:
        return False, "subtitle file missing/empty"
    text = path.read_text(encoding="utf-8")
    cues = len(re.findall(r"^\d+\s*$", text, re.M))
    if _arabic(text) < 20:
        return False, "insufficient Arabic subtitle text"
    if cues != expected:
        return False, f"expected {expected} cues, got {cues}"
    for line in text.splitlines():
        if not line.strip() or re.fullmatch(r"\d+", line) or re.match(r"^\d{2}:\d{2}:\d{2},\d{3}", line):
            continue
        if len(line) > 68:
            return False, "subtitle line is too long"
    if any(marker in text for marker in DEBUG_MARKERS):
        return False, "subtitle contains internal/debug text"
    return True, "ok"


def _subtitle_gate(root: Path, shorts: list[Path]) -> tuple[bool, str]:
    ok, reason = _srt(root / "arabic.srt", 25)
    if not ok:
        return False, reason
    try:
        master = json.loads((root / "subtitle_burn.json").read_text(encoding="utf-8"))
        final = root / "master_final.mp4"
        srt = root / "arabic.srt"
        if master.get("burned") is not True or master.get("output") != final.name:
            return False, "master subtitle marker invalid"
        if master.get("output_sha256") != _sha(final) or master.get("subtitle_sha256") != _sha(srt):
            return False, "master subtitle evidence hash mismatch"
        records = json.loads((root / "short_subtitles_burn.json").read_text(encoding="utf-8")).get("shorts", [])
        if len(records) != 4:
            return False, "expected four Short subtitle records"
        for index, (record, path) in enumerate(zip(records, shorts), 1):
            if record.get("burned") is not True or record.get("file") != str(path):
                return False, f"Short {index} subtitle marker invalid"
            if record.get("output_sha256") != _sha(path):
                return False, f"Short {index} subtitle output hash mismatch"
            ok, reason = _srt(Path(record.get("srt", "")), 2)
            if not ok:
                return False, f"Short {index}: {reason}"
        return True, "subtitle burn evidence verified"
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return False, f"subtitle evidence invalid: {exc}"


def _visual_gate(story: Story) -> tuple[list[str], dict]:
    errors: list[str] = []
    hashes: set[str] = set()
    modes: set[str] = set()
    cameras: set[str] = set()
    scene_metrics: list[dict] = []
    car_count = 0
    motion_count = 0
    intent_count = 0
    visible_callouts = 0
    for scene in story.scenes:
        svg_path = RUN / "scenes" / f"scene_{scene.id:02d}.svg"
        png_path = RUN / "frames" / f"scene_{scene.id:02d}.png"
        if not svg_path.is_file() or not png_path.is_file():
            errors.append(f"scene {scene.id} visual frame missing")
            continue
        svg = svg_path.read_text(encoding="utf-8")
        if any(marker in svg for marker in DEBUG_MARKERS):
            errors.append(f"scene {scene.id} contains forbidden internal presentation text")
        mode = re.search(r'data-visual-mode="([^"]+)"', svg)
        camera = re.search(r'data-camera-angle="([^"]+)"', svg)
        intent = re.search(r'data-visual-intent="([^"]*)"', svg)
        if not mode:
            errors.append(f"scene {scene.id} missing visual mode")
        else:
            modes.add(mode.group(1).casefold())
            if mode.group(1).casefold() != _kind(scene):
                errors.append(f"scene {scene.id} visual mode mismatch")
        if not camera:
            errors.append(f"scene {scene.id} missing camera composition")
        else:
            cameras.add(camera.group(1))
        if not intent or html.unescape(intent.group(1)).strip() != scene.visual_intent.strip()[:240]:
            errors.append(f"scene {scene.id} visual intent metadata mismatch")
        else:
            intent_count += 1
        if 'data-car-style="premium_3q_editorial"' in svg:
            car_count += 1
        if 'data-motion="camera_push_pan"' in svg:
            motion_count += 1
        visible_text = " ".join(re.findall(r">([^<>]+)<", svg))
        if scene.visual_intent.strip() and scene.visual_intent.strip() in visible_text:
            errors.append(f"scene {scene.id} exposes visual intent in visible text")
        for callout in scene.callouts[:5]:
            if str(callout) not in visible_text:
                errors.append(f"scene {scene.id} callout is not visibly rendered: {callout}")
            else:
                visible_callouts += 1
        metric = _image_metrics(png_path)
        hashes.add(metric["pixel_hash"])
        score = 0.0
        if (metric["width"], metric["height"]) == MASTER_SIZE:
            score += 15
        if metric["variance"] >= 120:
            score += 15
        if metric["edge_mean"] >= 8:
            score += 15
        if metric["non_background_ratio"] >= 0.12:
            score += 15
        if metric["car_roi_edge_mean"] >= max(3.0, metric["edge_mean"] * 0.85):
            score += 20
        if metric["mean_luma"] >= 8:
            score += 5
        if mode and camera:
            score += 10
        if not any(marker in svg for marker in DEBUG_MARKERS):
            score += 5
        metric["scene_id"] = scene.id
        metric["pixel_score"] = round(score, 1)
        scene_metrics.append(metric)
    average = round(sum(x["pixel_score"] for x in scene_metrics) / max(1, len(scene_metrics)), 1)
    if len(hashes) < 18:
        errors.append(f"rendered asset diversity too low: {len(hashes)}/25 pixel-unique scenes")
    if len(modes) < 4:
        errors.append(f"semantic diversity too low: {len(modes)} visual modes")
    if len(cameras) < 4:
        errors.append(f"camera diversity too low: {len(cameras)} compositions")
    if car_count < 20:
        errors.append(f"car-first coverage failed: {car_count}/25")
    if motion_count < 25:
        errors.append(f"motion metadata coverage failed: {motion_count}/25")
    if intent_count != 25:
        errors.append(f"visual intent metadata incomplete: {intent_count}/25")
    if average < 85:
        errors.append(f"pixel visual score {average}/100 below 85")
    return errors, {
        "average_score": average,
        "unique_pixel_assets": len(hashes),
        "unique_modes": len(modes),
        "unique_camera_angles": len(cameras),
        "car_first_scenes": car_count,
        "motion_scenes": motion_count,
        "visual_intents_verified": intent_count,
        "visible_callouts_verified": visible_callouts,
        "scene_metrics": scene_metrics,
    }


def qa(story: Story, master: Path, shorts: list[Path], report: Path = RUN / "qa_report.json") -> dict:
    errors: list[str] = []
    if not master.is_file() or master.stat().st_size == 0:
        errors.append("master missing")
    if len(story.scenes) != 25 or [s.id for s in story.scenes] != list(range(1, 26)):
        errors.append("story must contain exactly scenes 1..25")
    planned = sum(float(s.duration) for s in story.scenes)
    if not MIN_LONG <= planned <= MAX_LONG:
        errors.append(f"planned duration {planned:.2f}s outside 420-900s")
    for scene in story.scenes:
        audio = RUN / "audio" / f"scene_{scene.id:02d}.mp3"
        if not audio.is_file():
            errors.append(f"scene {scene.id} audio missing")
            continue
        words = _words(scene.narration)
        actual = _duration(audio)
        if words and actual > 0:
            wps = words / actual
            if not MIN_WPS <= wps <= MAX_WPS:
                errors.append(f"scene {scene.id} TTS pacing {wps:.2f} outside {MIN_WPS:.2f}-{MAX_WPS:.2f}")
            if actual > float(scene.duration) + 0.75:
                errors.append(f"scene {scene.id} audio exceeds duration by {actual - float(scene.duration):.2f}s")
    visual_errors, visual_metrics = _visual_gate(story)
    errors.extend(visual_errors)

    master_duration = None
    master_samples = None
    if master.is_file():
        try:
            videos = _streams(master, "video")
            if not videos:
                errors.append("master has no video stream")
            else:
                stream = videos[0]
                if (stream.get("width"), stream.get("height")) != MASTER_SIZE:
                    errors.append("master must be 1920x1080")
                if stream.get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
                    errors.append("master pixel format is not delivery-safe")
            master_duration = _duration(master)
            if not MIN_LONG <= master_duration <= MAX_LONG:
                errors.append(f"master duration {master_duration:.2f}s outside 420-900s")
            if abs(master_duration - planned) > 2.0:
                errors.append(f"master/planned duration drift {abs(master_duration - planned):.2f}s")
            audio_ok, audio_reason = _audio_quality(master)
            if not audio_ok:
                errors.append(f"master audio failed: {audio_reason}")
            bars, bar_reason = _black_bars(master)
            if bars:
                errors.append(f"master black-bar gate failed: {bar_reason}")
            master_samples = _sample_video(master)
        except Exception as exc:
            errors.append(f"master probe failed: {exc}")

    if len(shorts) != 4:
        errors.append(f"expected 4 Shorts, got {len(shorts)}")
    short_reports: list[dict] = []
    for index, path in enumerate(shorts, 1):
        item = {"file": str(path), "exists": path.is_file()}
        if not path.is_file():
            errors.append(f"short {index} missing")
            short_reports.append(item)
            continue
        try:
            videos = _streams(path, "video")
            duration = _duration(path)
            item.update({"duration": duration, "sha256": _sha(path), "resolution": [videos[0].get("width"), videos[0].get("height")] if videos else None})
            if not videos or (videos[0].get("width"), videos[0].get("height")) != SHORT_SIZE:
                errors.append(f"short {index} must be native 1080x1920")
            if not SHORT_MIN <= duration <= SHORT_MAX:
                errors.append(f"short {index} duration {duration:.2f}s outside 28-59s")
            expected = sum(float(story.scenes[sid - 1].duration) for sid in SHORT_GROUPS[index - 1])
            if abs(duration - expected) > 2.0:
                errors.append(f"short {index} duration drift {abs(duration - expected):.2f}s")
            audio_ok, audio_reason = _audio_quality(path)
            if not audio_ok:
                errors.append(f"short {index} audio failed: {audio_reason}")
            bars, bar_reason = _black_bars(path)
            if bars:
                errors.append(f"short {index} black-bar gate failed: {bar_reason}")
            item["samples"] = _sample_video(path, vertical=True)
        except Exception as exc:
            errors.append(f"short {index} probe failed: {exc}")
        short_reports.append(item)

    subtitle_ok, subtitle_reason = _subtitle_gate(RUN, shorts)
    if not subtitle_ok:
        errors.append(subtitle_reason)

    metadata_errors = []
    title = story.title.strip()
    description = story.description.strip()
    tags = [str(tag).strip() for tag in story.tags if str(tag).strip()]
    if not title or title.casefold() in {"untitled", "untitled story"}:
        metadata_errors.append("weak/missing title")
    if not 20 <= len(title) <= 100:
        metadata_errors.append("title must be 20-100 characters")
    if len(description) < 120:
        metadata_errors.append("description must be at least 120 characters")
    if len(tags) < 5:
        metadata_errors.append("at least 5 tags are required")
    if not isinstance(story.short_titles, list) or len(story.short_titles) != 4:
        metadata_errors.append("exactly 4 short titles are required")
    errors.extend(metadata_errors)

    categories = {
        "Script / Story": 10.0 if not any("story must" in e or "TTS pacing" in e for e in errors) else 0.0,
        "Visual Quality": min(10.0, visual_metrics["average_score"] / 10.0),
        "Scene Relevance": 10.0 if visual_metrics["car_first_scenes"] >= 20 and visual_metrics["unique_modes"] >= 4 else 0.0,
        "Audio / Voice": 10.0 if not any("audio failed" in e or "TTS pacing" in e for e in errors) else 0.0,
        "Arabic Subtitles": 10.0 if subtitle_ok else 0.0,
        "Synchronization": 10.0 if not any("drift" in e or "exceeds duration" in e for e in errors) else 0.0,
        "Shorts": 10.0 if len(shorts) == 4 and not any(e.startswith("short ") for e in errors) else 0.0,
        "Metadata / Publishing": 10.0 if not metadata_errors else 0.0,
    }
    weights = {"Script / Story": .15, "Visual Quality": .25, "Scene Relevance": .15, "Audio / Voice": .10, "Arabic Subtitles": .10, "Synchronization": .10, "Shorts": .10, "Metadata / Publishing": .05}
    weighted = round(sum(categories[key] * weights[key] for key in weights), 2)
    if weighted < MIN_PUBLISH_SCORE:
        errors.append(f"weighted product score {weighted:.2f}/10 below publish threshold {MIN_PUBLISH_SCORE:.1f}")

    result = {
        "passed": not errors,
        "errors": errors,
        "scene_count": len(story.scenes),
        "scene_ids_valid": [s.id for s in story.scenes] == list(range(1, 26)),
        "planned_duration": planned,
        "master_duration": master_duration,
        "master_samples": master_samples,
        "shorts": short_reports,
        "visual_product_gate": visual_metrics,
        "subtitle_stage": subtitle_reason,
        "weighted_score_10": weighted,
        "score_categories": categories,
        "publish_threshold_10": MIN_PUBLISH_SCORE,
        "stock_media": False,
        "legacy_manifest": False,
        "master_sha256": _sha(master) if master.is_file() else None,
        "short_shas": [_sha(path) if path.is_file() else None for path in shorts],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors))
    return result
