from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

from .core import RUN, Story

MASTER_SIZE = (1920, 1080)
SHORT_SIZE = (1080, 1920)
FAMILIES = {
    "front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene", "front_close",
    "rear_close", "three_quarter_high", "design_detail", "technology", "performance",
    "safety", "battery", "charging", "interior", "wheel_detail", "aero", "comparison",
}
MOTIONS = {"push_in", "pull_out", "orbit_left", "orbit_right", "rack_focus", "tracking", "rise"}
DEBUG_MARKERS = ("MODE_FACT_SOURCE_REQUIRED", "hud_only", "STORY CALLOUT", "VISUAL INTENT", "WHY IT MATTERS")


def _sample_frame(video: Path, seconds: float, out: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(max(0.0, seconds)), "-i", str(video), "-frames:v", "1", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"failed to sample {video} at {seconds:.2f}s: {result.stderr[-300:]}")


def _metric(path: Path) -> dict:
    with Image.open(path).convert("RGB") as image:
        small = image.resize((96, 54))
        stat = ImageStat.Stat(small)
        edge = small.filter(ImageFilter.FIND_EDGES)
        px = list(small.getdata())
        corner = px[0]
        non_background = sum(1 for p in px if sum(abs(p[i] - corner[i]) for i in range(3)) > 24) / len(px)
        return {
            "width": image.width,
            "height": image.height,
            "mean_luma": round(sum(stat.mean) / 3.0, 2),
            "variance": round(sum(stat.var) / 3.0, 2),
            "edge_mean": round(sum(ImageStat.Stat(edge).mean) / 3.0, 2),
            "non_background_ratio": round(non_background, 4),
            "pixel_hash": hashlib.sha256(image.resize((32, 32)).tobytes()).hexdigest(),
        }


def _probe_size(path: Path) -> tuple[int, int]:
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    w, h = raw.split("x", 1)
    return int(w), int(h)


def _duration(path: Path) -> float:
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(raw)


def _caption_diff_bbox(raw: Path, final: Path, seconds: float, vertical: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="caption-vqa-") as td:
        a = Path(td) / "raw.png"; b = Path(td) / "final.png"
        _sample_frame(raw, seconds, a); _sample_frame(final, seconds, b)
        ia = Image.open(a).convert("RGB").resize((270, 480) if vertical else (320, 180))
        ib = Image.open(b).convert("RGB").resize(ia.size)
        diff = ImageChops.difference(ia, ib).convert("L")
        mask = diff.point(lambda p: 255 if p >= 16 else 0)
        bbox = mask.getbbox()
        if not bbox:
            return {"bbox": None, "width_ratio": 0.0, "height_ratio": 0.0, "touches_edge": False, "area_ratio": 0.0}
        x0, y0, x1, y1 = bbox; w, h = mask.size
        area = (x1 - x0) * (y1 - y0) / float(w * h)
        return {
            "bbox": [x0, y0, x1, y1],
            "width_ratio": round((x1 - x0) / w, 4),
            "height_ratio": round((y1 - y0) / h, 4),
            "touches_edge": x0 <= int(w * 0.01) or x1 >= int(w * 0.99),
            "area_ratio": round(area, 4),
        }


def _srt_metrics(path: Path, max_line_chars: int) -> tuple[bool, str, dict]:
    if not path.is_file() or path.stat().st_size < 30:
        return False, "subtitle file missing/empty", {}
    text = path.read_text(encoding="utf-8")
    if "\ufffd" in text:
        return False, "replacement glyph U+FFFD present in subtitles", {}
    cues = len(re.findall(r"^\d+\s*$", text, re.M))
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    lines = []
    for line in text.splitlines():
        if not line.strip() or re.fullmatch(r"\d+", line) or re.match(r"^\d{2}:\d{2}:\d{2},\d{3}", line):
            continue
        if any(marker in line for marker in DEBUG_MARKERS):
            return False, "subtitle contains debug/internal text", {}
        if len(line) > max_line_chars:
            return False, f"subtitle line exceeds {max_line_chars} characters", {"max_line": len(line)}
        lines.append(len(line))
    return True, "ok", {"cue_count": cues, "arabic_chars": arabic, "max_line": max(lines or [0])}


def run_visual_product_gate(story: Story, master: Path, shorts: list[Path], report: Path = RUN / "visual_product_gate_v4.json") -> dict:
    errors: list[str] = []
    families: list[str] = []; cameras: list[str] = []; modes: list[str] = []; motions: list[str] = []
    scene_hashes: set[str] = set(); scenes: list[dict] = []
    car_first = 0; visual_intents = set(); family_counts: dict[str, int] = {}

    for scene in story.scenes:
        svg_path = RUN / "scenes" / f"scene_{scene.id:02d}.svg"
        png_path = RUN / "frames" / f"scene_{scene.id:02d}.png"
        if not svg_path.is_file() or not png_path.is_file():
            errors.append(f"scene {scene.id}: missing visual evidence"); continue
        svg = svg_path.read_text(encoding="utf-8")
        if any(marker in svg for marker in DEBUG_MARKERS):
            errors.append(f"scene {scene.id}: forbidden debug marker")
        fm = re.search(r'data-visual-family="([^"]+)"', svg); cm = re.search(r'data-camera-angle="([^"]+)"', svg)
        mm = re.search(r'data-visual-mode="([^"]+)"', svg); mt = re.search(r'data-motion="([^"]+)"', svg)
        im = re.search(r'data-visual-intent="([^"]*)"', svg)
        family = fm.group(1) if fm else ""; camera = cm.group(1) if cm else ""; mode = mm.group(1) if mm else ""; motion = mt.group(1) if mt else ""
        if family not in FAMILIES: errors.append(f"scene {scene.id}: invalid visual family {family!r}")
        if not camera: errors.append(f"scene {scene.id}: missing camera")
        if not mode: errors.append(f"scene {scene.id}: missing visual mode")
        if motion not in MOTIONS: errors.append(f"scene {scene.id}: invalid motion {motion!r}")
        if not im or im.group(1).strip() != scene.visual_intent.strip()[:240]: errors.append(f"scene {scene.id}: visual intent evidence mismatch")
        if 'data-car-layer="primary"' not in svg: errors.append(f"scene {scene.id}: car is not marked primary")
        else: car_first += 1
        families.append(family); cameras.append(camera); modes.append(mode); motions.append(motion)
        visual_intents.add(scene.visual_intent.casefold().strip())
        family_counts[family] = family_counts.get(family, 0) + 1
        m = _metric(png_path); scene_hashes.add(m["pixel_hash"]); m.update({"scene_id": scene.id, "family": family, "camera": camera, "mode": mode, "motion": motion})
        scenes.append(m)

    if len(story.scenes) != 25: errors.append(f"story scene count {len(story.scenes)}/25")
    if car_first < 25: errors.append(f"car-first coverage failed: {car_first}/25")
    if len(scene_hashes) < 20: errors.append(f"rendered scene uniqueness too low: {len(scene_hashes)}/25")
    if len(set(families)) < 10: errors.append(f"visual family diversity too low: {len(set(families))}/10")
    if len(set(cameras)) < 10: errors.append(f"camera diversity too low: {len(set(cameras))}/10")
    if len(set(modes)) < 5: errors.append(f"semantic mode diversity too low: {len(set(modes))}/5")
    if len(set(motions)) < 5: errors.append(f"motion diversity too low: {len(set(motions))}/5")
    if len(visual_intents) < 20: errors.append(f"visual intent diversity too low: {len(visual_intents)}/20")
    if any(v > 4 for v in family_counts.values()): errors.append(f"family repeated more than 4 times: {family_counts}")

    short_reports: list[dict] = []
    for index, path in enumerate(shorts, 1):
        if not path.is_file(): errors.append(f"Short {index} missing"); continue
        try:
            size = _probe_size(path); duration = _duration(path)
        except Exception as exc:
            errors.append(f"Short {index} probe failed: {exc}"); continue
        if size != SHORT_SIZE: errors.append(f"Short {index} is not native 1080x1920")
        if not 28.0 <= duration <= 59.0: errors.append(f"Short {index} duration {duration:.2f}s outside 28-59s")
        srt = RUN / f"short_segments_{index}" / "short.srt"
        ok, reason, sm = _srt_metrics(srt, 52)
        if not ok: errors.append(f"Short {index}: {reason}")
        raw = RUN / f"short_segments_{index}" / "raw.mp4"; diffs = []
        if raw.is_file():
            for point in (max(0.5, duration * .25), max(0.6, duration * .75)):
                try: diffs.append(_caption_diff_bbox(raw, path, min(point, duration - .2), True))
                except Exception as exc: errors.append(f"Short {index}: caption comparison failed: {exc}")
        for d in diffs:
            if d["bbox"] and (d["touches_edge"] or (d["width_ratio"] > .97 and d["height_ratio"] > .10) or d["area_ratio"] > .20):
                errors.append(f"Short {index}: subtitle overlay is oversized or touches frame edges: {d}")
        short_reports.append({"index": index, "duration": round(duration, 3), "resolution": list(size), "subtitle": sm, "caption_diffs": diffs})

    if not master.is_file(): errors.append("master missing")
    else:
        raw_master = RUN / "master.mp4"; diffs = []
        if raw_master.is_file():
            md = _duration(master)
            for point in (max(.5, md*.25), max(.6, md*.75)):
                try: diffs.append(_caption_diff_bbox(raw_master, master, min(point, md-.2), False))
                except Exception as exc: errors.append(f"master caption comparison failed: {exc}")
            for d in diffs:
                if d["bbox"] and (d["touches_edge"] or (d["width_ratio"] > .98 and d["height_ratio"] > .18) or d["area_ratio"] > .25):
                    errors.append(f"master subtitle overlay is oversized or touches frame edges: {d}")

    score = max(0.0, round(100.0 - max(0, 25-car_first)*3 - max(0, 20-len(scene_hashes))*2 - max(0, 10-len(set(families))) - max(0, 10-len(set(cameras))) - max(0, 5-len(set(motions)))*2, 1))
    if errors: score = min(score, 84.0)
    result = {
        "passed": not errors, "gate_version": "v4", "errors": errors, "average_score": score,
        "car_first_scenes": car_first, "unique_pixel_assets": len(scene_hashes), "unique_visual_families": len(set(families)),
        "unique_camera_angles": len(set(cameras)), "unique_modes": len(set(modes)), "unique_motions": len(set(motions)),
        "visual_intents_verified": len(visual_intents), "family_counts": family_counts, "scenes": scenes, "shorts": short_reports,
    }
    report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors: raise RuntimeError("VISUAL PRODUCT GATE V4 FAILED: " + "; ".join(errors))
    return result
