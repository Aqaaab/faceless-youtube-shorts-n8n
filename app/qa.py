from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from .core import RUN, Story
from .story_visuals import _kind

MIN_LONG, MAX_LONG = 420.0, 900.0
SHORT_MIN, SHORT_MAX = 28.0, 59.0
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_RESOLUTION = (1080, 1920)
MASTER_RESOLUTION = (1920, 1080)
MIN_WPS, MAX_WPS = 1.60, 2.10
MIN_PUBLISH_SCORE = 9.0
DEBUG_MARKERS = ("MODE_FACT_SOURCE_REQUIRED", "hud_only", "STORY CALLOUT", "VISUAL INTENT", "WHY IT MATTERS")


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _probe(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    return json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def _streams(path: Path, kind: str) -> list[dict]:
    return [stream for stream in _probe(path).get("streams", []) if stream.get("codec_type") == kind]


def _duration(path: Path) -> float:
    value = _probe(path).get("format", {}).get("duration")
    return float(value)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _arabic(text: str) -> int:
    return len(re.findall(r"[\u0600-\u06ff]", str(text)))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audio_quality(path: Path) -> tuple[bool, str]:
    if not _streams(path, "audio"):
        return False, "no audio stream"
    result = _run(["ffmpeg", "-v", "error", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], False)
    text = result.stderr or ""
    mean = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    peak = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    if mean and float(mean.group(1)) < -32:
        return False, f"audio mean level too low ({mean.group(1)} dB)"
    if peak and float(peak.group(1)) > -0.2:
        return False, f"audio peak too close to clipping ({peak.group(1)} dB)"
    silence = _run(["ffmpeg", "-v", "error", "-i", str(path), "-af", "silencedetect=noise=-42dB:d=1.5", "-f", "null", "-"], False).stderr or ""
    starts = len(re.findall(r"silence_start", silence))
    ends = len(re.findall(r"silence_end", silence))
    if starts > 3 or ends > 3:
        return False, f"unexpected extended silence ({starts} intervals)"
    return True, "ok"


def _frame_at(path: Path, seconds: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["ffmpeg", "-y", "-ss", str(max(0.0, seconds)), "-i", str(path), "-frames:v", "1", "-vf", "format=rgb24", str(output)], False)
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"could not sample frame at {seconds:.2f}s from {path}")


def _image_metrics(path: Path, vertical: bool = False) -> dict:
    with Image.open(path).convert("RGB") as image:
        small = image.resize((64, 64))
        stat = ImageStat.Stat(small)
        mean = sum(stat.mean) / 3.0
        variance = sum(stat.var) / 3.0
        edges = small.filter(ImageFilter.FIND_EDGES)
        edge_mean = sum(ImageStat.Stat(edges).mean) / 3.0
        pixels = list(small.getdata())
        corner = pixels[0]
        diff = sum(1 for p in pixels if sum(abs(p[i] - corner[i]) for i in range(3)) > 24) / len(pixels)
        width, height = image.size
        roi = image.crop((int(width * 0.05), int(height * (0.18 if not vertical else 0.16)), int(width * 0.88), int(height * (0.82 if not vertical else 0.70))))
        roi_small = roi.resize((64, 64))
        roi_edges = roi_small.filter(ImageFilter.FIND_EDGES)
        roi_edge_mean = sum(ImageStat.Stat(roi_edges).mean) / 3.0
        arr = [sum(p) / 3.0 for p in pixels]
        border = []
        for x in range(64):
            for y in range(4):
                border.append(arr[y * 64 + x]); border.append(arr[(63 - y) * 64 + x])
        for y in range(4, 60):
            border.append(arr[y * 64]); border.append(arr[y * 64 + 63])
        border_mean = sum(border) / max(1, len(border))
        center = arr[16 * 64 + 32]
        hash_bytes = bytes(int(max(0, min(255, v))) for v in arr)
        return {
            "width": width,
            "height": height,
            "mean_luma": round(mean, 2),
            "variance": round(variance, 2),
            "edge_mean": round(edge_mean, 2),
            "non_background_ratio": round(diff, 4),
            "car_roi_edge_mean": round(roi_edge_mean, 2),
            "border_mean_luma": round(border_mean, 2),
            "center_luma": round(center, 2),
            "pixel_hash": hashlib.sha256(hash_bytes).hexdigest(),
        }


def _bar_check(path: Path) -> tuple[bool, str]:
    duration = _duration(path)
    points = sorted(set(max(0.0, min(duration - 0.1, x)) for x in (0.5, 2.0, duration * 0.5, max(0.0, duration - 1.0))))
    tmp = Path(tempfile.mkdtemp(prefix="qa-bars-"))
    try:
        for index, seconds in enumerate(points):
            frame = tmp / f"{index}.png"
            _frame_at(path, seconds, frame)
            with Image.open(frame).convert("RGB") as image:
                metric = _image_metrics(frame)
                if metric["width"] <= 0 or metric["height"] <= 0:
                    return True, "invalid frame dimensions"
                border = metric["border_mean_luma"]
                center = metric["center_luma"]
                if border < 3.0 and center - border > 18.0:
                    return True, f"possible black border at {seconds:.2f}s"
        return False, "ok"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _srt(path: Path, expected: int) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 50:
        return False, "subtitle file missing/empty"
    text = path.read_text(encoding="utf-8")
    cues = len(re.findall(r"^\d+\s*$", text, re.M))
    if _arabic(text) < 20:
        return False, "subtitle file contains insufficient Arabic text"
    if cues != expected:
        return False, f"expected {expected} subtitle cues, got {cues}"
    for line in text.splitlines():
        if re.match(r"^\d+$", line) or re.match(r"^\d{2}:\d{2}:\d{2},\d{3}", line) or not line.strip():
            continue
        if len(line) > 68:
            return False, "subtitle line exceeds readable length"
    if any(marker in text for marker in DEBUG_MARKERS):
        return False, "subtitle contains internal/debug text"
    return True, "ok"


def _subtitle_evidence(root: Path, shorts: list[Path]) -> tuple[bool, str]:
    ok, reason = _srt(root / "arabic.srt", 25)
    if not ok:
        return False, reason
    try:
        master_data = json.loads((root / "subtitle_burn.json").read_text(encoding="utf-8"))
        master = root / "master_final.mp4"
        srt = root / "arabic.srt"
        if master_data.get("burned") is not True or master_data.get("output") != master.name:
            return False, "master subtitle evidence invalid"
        if master_data.get("output_sha256") != _sha(master):
            return False, "master subtitle output hash mismatch"
        if master_data.get("subtitle_sha256") != _sha(srt):
            return False, "master subtitle input hash mismatch"
        short_data = json.loads((root / "short_subtitles_burn.json").read_text(encoding="utf-8"))
        records = short_data.get("shorts", [])
        if len(records) != 4:
            return False, "expected four Short subtitle evidence records"
        for index, (record, path) in enumerate(zip(records, shorts), 1):
            if record.get("burned") is not True or record.get("file") != str(path):
                return False, f"Short {index} subtitle evidence invalid"
            if record.get("output_sha256") != _sha(path):
                return False, f"Short {index} subtitle output hash mismatch"
            srt_path = Path(record.get("srt", ""))
            ok, reason = _srt(srt_path, 2)
            if not ok:
                return False, f"Short {index}: {reason}"
        return True, "Arabic subtitle burn evidence verified"
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return False, f"subtitle evidence invalid: {exc}"


def _scene_visual_metrics(story: Story) -> tuple[list[str], dict]:
    errors: list[str] = []
    metrics: list[dict] = []
    hashes: set[str] = set()
    modes: set[str] = set()
    cameras: set[str] = set()
    car_count = 0
    motion_count = 0
    rendered_intents = 0
    grounded_callouts = 0
    score_values: list[float] = []
    for scene in story.scenes:
        svg_path = RUN / "scenes" / f"scene_{scene.id:02d}.svg"
        png_path = RUN / "frames" / f"scene_{scene.id:02d}.png"
        if not svg_path.exists() or not png_path.exists():
            errors.append(f"scene {scene.id} visual source/frame missing")
            continue
        svg = svg_path.read_text(encoding="utf-8")
        if any(marker in svg for marker in DEBUG_MARKERS):
            errors.append(f"scene {scene.id} contains debug/internal presentation text")
        mode = re.search(r'data-visual-mode="([^"]+)"', svg)
        camera = re.search(r'data-camera-angle="([^"]+)"', svg)
        intent = re.search(r'data-visual-intent="([^"]+)"', svg)
        if not mode:
            errors.append(f"scene {scene.id} is missing visual mode evidence")
        else:
            modes.add(mode.group(1).casefold())
            if mode.group(1).casefold() != _kind(scene):
                errors.append(f"scene {scene.id} visual mode mismatch")
        if not camera:
            errors.append(f"scene {scene.id} is missing camera evidence")
        else:
            cameras.add(camera.group(1))
        if not intent or scene.visual_intent[:120] not in html_unescape(intent.group(1)):
            errors.append(f"scene {scene.id} is missing visual-intent metadata")
        elif scene.visual_intent[:120].strip():
            rendered_intents += 1
        if 'data-car-style="premium_3q_editorial"' in svg:
            car_count += 1
        if 'data-motion="camera_push_pan"' in svg:
            motion_count += 1
        visible_text = " ".join(re.findall(r">([^<>]+)<", svg))
        if scene.visual_intent.strip() and scene.visual_intent.strip() in visible_text:
            errors.append(f"scene {scene.id} exposes internal visual-intent copy in the rendered text")
        for callout in scene.callouts[:5]:
            if str(callout) in visible_text:
                grounded_callouts += 1
            else:
                errors.append(f"scene {scene.id} callout not visibly rendered: {callout}")
        metric = _image_metrics(png_path)
        hashes.add(metric["pixel_hash"])
        score = 0.0
        if metric["width"], metric["height"] == (1920, 1080):
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
        if camera:
            score += 5
        if mode:
            score += 5
        metrics.append({"scene_id": scene.id, **metric, "pixel_score": round(score, 1)})
        score_values.append(score)
    average = round(sum(score_values) / max(1, len(score_values)), 1)
    if len(hashes) < 18:
        errors.append(f"rendered visual diversity too low: {len(hashes)}/25 unique pixel hashes")
    if len(modes) < 4:
        errors.append(f"semantic visual diversity too low: {len(modes)} modes")
    if len(cameras) < 4:
        errors.append(f"camera composition diversity too low: {len(cameras)} compositions")
    if car_count < 20:
        errors.append(f"car-first coverage failed: {car_count}/25")
    if motion_count < 25:
        errors.append(f"motion coverage failed: {motion_count}/25")
    if rendered_intents != 25:
        errors.append(f"visual-intent metadata incomplete: {rendered_intents}/25")
    if average < 85:
        errors.append(f"visual product pixel score {average}/100 below 85")
    return errors, {
        "average_score": average,
        "unique_pixel_assets": len(hashes),
        "unique_modes": len(modes),
        "unique_camera_angles": len(cameras),
        "car_first_scenes": car_count,
        "motion_scenes": motion_count,
        "rendered_intents": rendered_intents,
        "grounded_callouts_visible": grounded_callouts,
        "scene_metrics": metrics,
    }


def html_unescape(value: str) -> str:
    return value.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#x27;", "'")


def _metadata_errors(story: Story) -> list[str]:
    errors = []
    title = story.title.strip()
    description = story.description.strip()
    tags = [str(tag).strip() for tag in story.tags if str(tag).strip()]
    if not title or title.casefold() in {"untitled", "untitled story"}:
        errors.append("weak/missing title")
    if not 20 <= len(title) <= 100:
        errors.append("title must be 20-100 characters")
    if len(description) < 120:
        errors.append("description must be at least 120 characters")
    if len(tags) < 5:
        errors.append("at least 5 tags are required")
    if not isinstance(story.short_titles, list) or len(story.short_titles) != 4:
        errors.append("exactly 4 short titles are required")
    return errors


def _short_report(story: Story, shorts: list[Path], errors: list[str]) -> list[dict]:
    reports = []
    for index, path in enumerate(shorts, 1):
        item = {"file": str(path), "exists": path.exists()}
        if not path.exists():
            errors.append(f"short {index} missing")
            reports.append(item)
            continue
        try:
            streams = _streams(path, "video")
            duration = _duration(path)
            item.update({"duration": duration, "resolution": [streams[0].get("width"), streams[0].get("height")] if streams else None, "sha256": _sha(path)})
            if not SHORT_MIN <= duration <= SHORT_MAX:
                errors.append(f"short {index} duration {duration:.2f}s outside 28-59s")
            if not streams or (streams[0].get("width"), streams[0].get("height")) != SHORT_RESOLUTION:
                errors.append(f"short {index} must be 1080x1920")
            expected = sum(float(story.scenes[scene_id - 1].duration) for scene_id in SHORT_GROUPS[index - 1])
            if abs(duration - expected) > 2.0:
                errors.append(f"short {index} duration drift {abs(duration - expected):.2f}s")
            audio_ok, audio_reason = _audio_quality(path)
            if not audio_ok:
                errors.append(f"short {index} audio failed: {audio_reason}")
            bars, bar_reason = _bar_check(path)
            if bars:
                errors.append(f"short {index} black-bar gate failed: {bar_reason}")
            metric = _image_metrics_from_video(path, duration, vertical=True)
            item["sample_metrics"] = metric
        except Exception as exc:
            errors.append(f"short {index} probe failed: {exc}")
        reports.append(item)
    return reports


def _image_metrics_from_video(path: Path, duration: float, vertical: bool) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="qa-samples-"))
    try:
        points = sorted(set(max(0.0, min(duration - 0.1, x)) for x in (1.0, duration * 0.5, max(0.0, duration - 1.0))))
        frames = []
        for index, point in enumerate(points):
            frame = tmp / f"{index}.png"
            _frame_at(path, point, frame)
            frames.append(_image_metrics(frame, vertical=vertical))
        return {"average_non_background_ratio": round(sum(x["non_background_ratio"] for x in frames) / max(1, len(frames)), 4), "average_edge_mean": round(sum(x["edge_mean"] for x in frames) / max(1, len(frames)), 2), "unique_hashes": len({x["pixel_hash"] for x in frames}), "frames": frames}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def qa(story: Story, master: Path, shorts: list[Path], report: Path = RUN / "qa_report.json") -> dict:
    errors: list[str] = []
    if not master.exists() or master.stat().st_size == 0:
        errors.append("master missing")
    if len(story.scenes) != 25 or [s.id for s in story.scenes] != list(range(1, 26)):
        errors.append("story must contain exactly scenes 1..25")
    planned = sum(float(scene.duration) for scene in story.scenes)
    if not MIN_LONG <= planned <= MAX_LONG:
        errors.append(f"planned duration {planned:.2f}s outside 420-900s")

    for scene in story.scenes:
        if not 5.0 <= float(scene.duration) <= 60.0:
            errors.append(f"scene {scene.id} duration outside 5-60s")
        words = _words(scene.narration)
        if not 25 <= words <= 75:
            errors.append(f"scene {scene.id} narration must be 25-75 words (got {words})")
        if _arabic(scene.narration) == 0:
            errors.append(f"scene {scene.id} narration is not Arabic")
        wps_data = None
        audio_path = RUN / "audio" / f"scene_{scene.id:02d}.mp3"
        if audio_path.exists() and words:
            actual_audio = _duration(audio_path)
            wps_data = words / actual_audio if actual_audio > 0 else 0
            if not MIN_WPS <= wps_data <= MAX_WPS:
                errors.append(f"scene {scene.id} TTS pacing {wps_data:.2f} words/s outside {MIN_WPS:.2f}-{MAX_WPS:.2f}")
            if actual_audio > float(scene.duration) + 0.75:
                errors.append(f"scene {scene.id} audio exceeds scene duration by {actual_audio - float(scene.duration):.2f}s")
        else:
            errors.append(f"scene {scene.id} audio evidence missing")

    errors.extend(_metadata_errors(story))
    visual_errors, visual_metrics = _scene_visual_metrics(story)
    errors.extend(visual_errors)

    master_duration = None
    master_metric = None
    if master.exists():
        try:
            video_streams = _streams(master, "video")
            if not video_streams:
                errors.append("master has no video stream")
            else:
                v = video_streams[0]
                if (v.get("width"), v.get("height")) != MASTER_RESOLUTION:
                    errors.append("master must be 1920x1080")
                if v.get("pix_fmt") not in {"yuv420p", "yuvj420p"}:
                    errors.append("master pixel format is not delivery-safe")
            master_duration = _duration(master)
            if not MIN_LONG <= master_duration <= MAX_LONG:
                errors.append(f"master duration {master_duration:.2f}s outside 420-900s")
            if abs(master_duration - planned) > 2.0:
                errors.append(f"master/planned duration drift {abs(master_duration - planned):.2f}s")
            ok, reason = _audio_quality(master)
            if not ok:
                errors.append(f"master audio failed: {reason}")
            bars, reason = _bar_check(master)
            if bars:
                errors.append(f"master black-bar gate failed: {reason}")
            tmp = Path(tempfile.mkdtemp(prefix="qa-master-"))
            try:
                points = [0.5, min(master_duration * 0.33, max(0.5, master_duration - 0.1)), min(master_duration * 0.66, max(0.5, master_duration - 0.1)), max(0.0, master_duration - 1.0)]
                samples = []
                for index, point in enumerate(points):
                    frame = tmp / f"{index}.png"
                    _frame_at(master, point, frame)
                    samples.append(_image_metrics(frame))
                master_metric = {"sample_count": len(samples), "average_non_background_ratio": round(sum(s["non_background_ratio"] for s in samples) / len(samples), 4), "average_edge_mean": round(sum(s["edge_mean"] for s in samples) / len(samples), 2), "unique_hashes": len({s["pixel_hash"] for s in samples}), "frames": samples}
                if master_metric["unique_hashes"] < 3:
                    errors.append("master frame diversity is too low")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        except Exception as exc:
            errors.append(f"master probe failed: {exc}")

    subtitle_ok, subtitle_reason = _subtitle_evidence(RUN, shorts)
    if not subtitle_ok:
        errors.append(subtitle_reason)
    short_reports = _short_report(story, shorts, errors) if len(shorts) == 4 else []
    if len(shorts) != 4:
        errors.append(f"expected 4 Shorts, got {len(shorts)}")

    score_categories = {
        "Script / Story": 10.0 if not any("narration" in e or "story must" in e for e in errors) else 0.0,
        "Visual Quality": min(10.0, visual_metrics["average_score"] / 10.0),
        "Scene Relevance": 10.0 if visual_metrics["car_first_scenes"] >= 20 and visual_metrics["unique_modes"] >= 4 else 0.0,
        "Audio / Voice": 10.0 if not any("audio failed" in e or "TTS pacing" in e for e in errors) else 0.0,
        "Arabic Subtitles": 10.0 if subtitle_ok else 0.0,
        "Synchronization": 10.0 if not any("drift" in e or "exceeds scene duration" in e for e in errors) else 0.0,
        "Shorts": 10.0 if len(shorts) == 4 and not any(e.startswith("short ") for e in errors) else 0.0,
        "Metadata / Publishing": 10.0 if not _metadata_errors(story) else 0.0,
    }
    weights = {"Script / Story": 0.15, "Visual Quality": 0.25, "Scene Relevance": 0.15, "Audio / Voice": 0.10, "Arabic Subtitles": 0.10, "Synchronization": 0.10, "Shorts": 0.10, "Metadata / Publishing": 0.05}
    weighted = round(sum(score_categories[key] * weights[key] for key in weights), 2)
    if not  weighted >= MIN_PUBLISH_SCORE:
        errors.append(f"weighted product score {weighted:.2f}/10 is below publish threshold {MIN_PUBLISH_SCORE:.1f}")

    result = {
        "passed": not errors,
        "errors": errors,
        "scene_count": len(story.scenes),
        "scene_ids_valid": [s.id for s in story.scenes] == list(range(1, 26)),
        "planned_duration": planned,
        "master_duration": master_duration,
        "master_samples": master_metric,
        "shorts": short_reports,
        "subtitle_stage": subtitle_reason,
        "visual_product_gate": visual_metrics,
        "weighted_score_10": weighted,
        "score_categories": score_categories,
        "publish_threshold_10": MIN_PUBLISH_SCORE,
        "stock_media": False,
        "legacy_manifest": False,
        "master_sha256": _sha(master) if master.exists() else None,
        "short_shas": [_sha(path) if path.exists() else None for path in shorts],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors))
    return result
