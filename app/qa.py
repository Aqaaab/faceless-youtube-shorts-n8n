from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

from .core import RUN, Story
from .story_visuals import _kind

MIN_LONG, MAX_LONG = 420.0, 900.0
MIN_WORDS, MAX_WORDS = 25, 75
SHORT_MIN, SHORT_MAX = 28.0, 59.0
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_RESOLUTION = (1080, 1920)  # explicit 1080,1920 contract
VALID_VISUAL_MODES = {"performance", "design", "interior", "technology", "efficiency", "safety", "price", "hero"}
MIN_WPS, MAX_WPS = 1.60, 2.10
DEBUG_MARKERS = ("SCENE ", "VISUAL INTENT", "STORY CALLOUT", "WHY IT MATTERS", "hud_only", "generic", "MODE_FACT_SOURCE_REQUIRED")


def _probe(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def _streams(path: Path, kind: str) -> list[dict]:
    return [s for s in _probe(path).get("streams", []) if s.get("codec_type") == kind]


def _duration(path: Path) -> float:
    return float(_probe(path)["format"]["duration"])


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


def _audio_quality(path: Path) -> tuple[bool, str]:
    streams = _streams(path, "audio")
    if not streams:
        return False, "no audio stream"
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, check=False)
    text = p.stderr or ""
    mean = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    peak = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    if mean and float(mean.group(1)) < -32:
        return False, f"audio mean level too low ({mean.group(1)} dB)"
    if peak and float(peak.group(1)) > -0.2:
        return False, f"audio peak too close to clipping ({peak.group(1)} dB)"
    return True, "ok"


def _black_bars(path: Path) -> bool:
    try:
        info = _streams(path, "video")[0]
        W, H = int(info.get("width", 0)), int(info.get("height", 0))
        duration = _duration(path)
        samples = [max(0.0, min(duration - 1.0, x)) for x in (2, 12, 30)]
        for ss in sorted(set(samples)):
            p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(ss), "-i", str(path), "-frames:v", "20", "-vf", "cropdetect=0.02:16:0", "-f", "null", "-"], capture_output=True, text=True, check=False)
            for line in (p.stderr or "").splitlines():
                if "crop=" not in line:
                    continue
                crop = line.split("crop=", 1)[1].split()[0]
                cw, ch, cx, cy = (int(v) for v in crop.split(":")[:4])
                if cw < W - 8 or ch < H - 8 or cx > 4 or cy > 4:
                    return True
        return False
    except Exception:
        return True


def _srt(path: Path, expected_cues: int) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 50:
        return False, "subtitle file missing/empty"
    text = path.read_text(encoding="utf-8")
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    cues = len(re.findall(r"^\d+\s*$", text, flags=re.M))
    if arabic < 20:
        return False, "subtitle file contains insufficient Arabic text"
    if cues != expected_cues:
        return False, f"expected {expected_cues} subtitle cues, got {cues}"
    if any(len(line) > 68 for line in text.splitlines() if not re.match(r"^\d|\d{2}:\d{2}:\d{2},", line)):
        return False, "subtitle line is too long for readable burn"
    return True, "ok"


def _master_subtitles() -> tuple[bool, str]:
    ok, reason = _srt(RUN / "arabic.srt", 25)
    if not ok:
        return False, reason
    marker = RUN / "subtitle_burn.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        srt = RUN / "arabic.srt"; out = RUN / "master_final.mp4"
        if data.get("burned") is not True or data.get("source") != "master.mp4" or data.get("output") != out.name:
            return False, "master subtitle burn marker invalid"
        if data.get("subtitle_sha256") != hashlib.sha256(srt.read_bytes()).hexdigest():
            return False, "master subtitle hash mismatch"
        if data.get("output_sha256") != hashlib.sha256(out.read_bytes()).hexdigest():
            return False, "master subtitle output hash mismatch"
    except Exception as exc:
        return False, f"master subtitle evidence missing: {exc}"
    return True, "Arabic master subtitles verified"


def _visual_product_gate(story: Story) -> tuple[list[str], dict]:
    errors = []
    hashes, modes = [], []
    quality_scores = []
    car_assets = 0
    motion_assets = 0
    for s in story.scenes:
        p = RUN / "scenes" / f"scene_{s.id:02d}.svg"
        if not p.exists():
            errors.append(f"scene {s.id} visual asset missing")
            continue
        text = p.read_text(encoding="utf-8")
        score = 0
        if 'data-asset-quality="premium_automotive_editorial_v2"' in text:
            score += 20
        if 'data-car-style="premium_3q_editorial"' in text:
            score += 25; car_assets += 1
        if 'data-motion="camera_push_pan"' in text:
            score += 10; motion_assets += 1
        if text.count("<path") >= 12 and text.count("<circle") >= 4 and "linearGradient" in text:
            score += 20
        if any(marker in text for marker in DEBUG_MARKERS):
            errors.append(f"scene {s.id} contains debug/UI presentation language")
        else:
            score += 10
        if html.escape(str(s.visual_intent).strip()[:120]) not in text:
            errors.append(f"scene {s.id} visual intent not rendered")
        for callout in s.callouts[:5]:
            if html.escape(str(callout)[:120]) not in text:
                errors.append(f"scene {s.id} callout not rendered: {callout}")
        mode_match = re.search(r'data-visual-mode="([^"]+)"', text)
        layout_match = re.search(r'data-layout="([^"]+)"', text)
        if not mode_match or mode_match.group(1).casefold() not in VALID_VISUAL_MODES:
            errors.append(f"scene {s.id} has invalid/missing visual mode")
        else:
            mode = mode_match.group(1).casefold(); modes.append(mode)
            if mode != _kind(s):
                errors.append(f"scene {s.id} visual mode mismatch: asset={mode}, expected={_kind(s)}")
        if not layout_match or not layout_match.group(1).strip():
            errors.append(f"scene {s.id} missing visual layout evidence")
        if score < 80:
            errors.append(f"scene {s.id} visual product score {score}/100 below 80")
        quality_scores.append(score)
        hashes.append(hashlib.sha256(text.encode()).hexdigest())

    if len(set(hashes)) < 23:
        errors.append(f"visual diversity too low: only {len(set(hashes))}/25 unique assets")
    if len(set(modes)) < 4:
        errors.append(f"semantic visual diversity too low: only {len(set(modes))} modes")
    if car_assets < 20:
        errors.append(f"car-first gate failed: only {car_assets}/25 scenes contain the premium vehicle asset")
    if motion_assets < 25:
        errors.append(f"motion metadata gate failed: {motion_assets}/25 scenes advertise camera motion")
    score = round(sum(quality_scores) / max(1, len(quality_scores)), 1)
    if score < 85:
        errors.append(f"visual product gate failed: average {score}/100 < 85")
    return errors, {"average_score": score, "car_first_scenes": car_assets, "motion_scenes": motion_assets, "unique_assets": len(set(hashes)), "unique_modes": len(set(modes))}


def _short_burn_evidence(shorts: list[Path]) -> tuple[bool, str]:
    marker = RUN / "short_subtitles_burn.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8")); items = data.get("shorts", [])
        if len(items) != 4:
            return False, "expected 4 Shorts subtitle records"
        for i, (item, path) in enumerate(zip(items, shorts), 1):
            if item.get("burned") is not True or item.get("file") != str(path):
                return False, f"Short {i} burn evidence invalid"
            if not path.exists() or item.get("output_size") != path.stat().st_size:
                return False, f"Short {i} output size evidence mismatch"
            if item.get("output_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
                return False, f"Short {i} output hash mismatch"
            ok, reason = _srt(Path(item.get("srt", "")), 2)
            if not ok:
                return False, f"Short {i} {reason}"
        return True, "4 Shorts subtitle outputs verified"
    except Exception as exc:
        return False, f"short subtitle evidence missing: {exc}"


def qa(story: Story, master: Path, shorts: list[Path], report: Path = RUN/"qa_report.json"):
    errors = []
    if not master.exists(): errors.append("master missing")
    if len(story.scenes) != 25: errors.append(f"expected exactly 25 scenes, got {len(story.scenes)}")
    ids = [s.id for s in story.scenes]
    if ids != list(range(1, 26)): errors.append("scene ids must be exactly 1..25")
    planned = sum(float(s.duration) for s in story.scenes)
    if not MIN_LONG <= planned <= MAX_LONG: errors.append(f"planned duration {planned:.2f}s outside 420-900")

    layouts, intents = set(), set()
    for s in story.scenes:
        words = _words(s.narration)
        if words < MIN_WORDS or words > MAX_WORDS: errors.append(f"scene {s.id} narration must be 25-75 words (got {words})")
        if not re.search(r"[\u0600-\u06ff]", s.narration): errors.append(f"scene {s.id} narration is not Arabic")
        if not 5 <= float(s.duration) <= 60: errors.append(f"scene {s.id} duration outside 5-60s")
        if len(s.callouts) > 5: errors.append(f"scene {s.id} has more than 5 callouts")
        layouts.add(s.layout.strip().lower()); intents.add(s.visual_intent.strip().casefold())
    if len(layouts) < 4: errors.append("layout diversity too low")
    if len(intents) < 20: errors.append("visual intent diversity too low")

    for n, group in enumerate(SHORT_GROUPS, 1):
        d = sum(float(story.scenes[i - 1].duration) for i in group)
        if not SHORT_MIN <= d <= SHORT_MAX: errors.append(f"Short {n} source duration {d:.2f}s outside 28-59s")

    visual_errors, visual_metrics = _visual_product_gate(story)
    errors.extend(visual_errors)

    master_duration = None
    if master.exists():
        try:
            videos = _streams(master, "video")
            if not videos: errors.append("master has no video stream")
            else:
                v = videos[0]
                if (v.get("width"), v.get("height")) != (1920, 1080): errors.append("master must be 1920x1080")
                if v.get("pix_fmt") not in {"yuv420p", "yuvj420p"}: errors.append("master pixel format is not delivery-safe")
            master_duration = _duration(master)
            if not MIN_LONG <= master_duration <= MAX_LONG: errors.append(f"master duration {master_duration:.2f}s outside 420-900")
            if abs(master_duration - planned) > 2.0: errors.append(f"master/planned duration drift is {abs(master_duration-planned):.2f}s")
            ok, reason = _audio_quality(master)
            if not ok: errors.append(f"master audio failed: {reason}")
            if _black_bars(master): errors.append("master appears to contain unintended black bars/cropping")
        except Exception as exc:
            errors.append(f"master probe failed: {exc}")

    short_reports = []
    if len(shorts) != 4: errors.append(f"expected exactly 4 shorts, got {len(shorts)}")
    for i, path in enumerate(shorts, 1):
        item = {"file": str(path), "exists": path.exists()}
        if not path.exists():
            errors.append(f"short {i} missing"); short_reports.append(item); continue
        try:
            v = _streams(path, "video"); d = _duration(path)
            item.update({"duration": d, "resolution": [v[0].get("width"), v[0].get("height")] if v else None, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            if not SHORT_MIN <= d <= SHORT_MAX: errors.append(f"short {i} duration {d:.2f}s outside 28-59s")
            if not v or (v[0].get("width"), v[0].get("height")) != SHORT_RESOLUTION: errors.append(f"short {i} must be native 1080x1920")
            ok, reason = _audio_quality(path)
            if not ok: errors.append(f"short {i} audio failed: {reason}")
            if _black_bars(path): errors.append(f"short {i} appears to contain unintended black bars/cropping")
            if path.stat().st_size < 100_000: errors.append(f"short {i} file is suspiciously small")
        except Exception as exc:
            errors.append(f"short {i} probe failed: {exc}")
        short_reports.append(item)

    sub_ok, sub_reason = _master_subtitles()
    if not sub_ok: errors.append(sub_reason)
    short_ok, short_reason = _short_burn_evidence(shorts)
    if not short_ok: errors.append(short_reason)

    title = str(story.title).strip(); description = str(story.description).strip(); tags = story.tags
    if not title or title.casefold() in {"untitled", "untitled story"}: errors.append("weak/missing title")
    if not 20 <= len(title) <= 100: errors.append("title must be 20-100 characters")
    if len(description) < 120: errors.append("description must be at least 120 characters")
    if not isinstance(tags, list) or len(tags) < 5: errors.append("at least 5 tags are required")

    result = {
        "passed": not errors, "errors": errors, "scene_count": len(story.scenes),
        "scene_ids_valid": ids == list(range(1, 26)), "planned_duration": planned,
        "master_duration": master_duration, "shorts": short_reports,
        "subtitle_stage": sub_reason, "short_subtitle_stage": short_reason,
        "visual_layouts": sorted(layouts), "visual_intent_count": len(intents),
        "visual_product_gate": visual_metrics, "stock_media": False, "legacy_manifest": False,
        "black_bar_gate": "failed" if any("black bars" in e for e in errors) else "passed",
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors))
    return result
