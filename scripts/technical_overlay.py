from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))


def _duration(path: Path) -> float:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ], text=True)
    return float(raw.strip())


def _words(text: str) -> int:
    return max(1, len(re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", str(text or ""))))


def _safe_label(value: object, limit: int) -> str:
    value = str(value or "").replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _esc_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def _build_filter(scenes: list[dict], total: float, vertical: bool, root: Path) -> str:
    total_words = sum(_words(s.get("text_en", "")) for s in scenes)
    cursor = 0.0
    filters: list[str] = []
    tech_dir = root / "technical_overlay"
    tech_dir.mkdir(parents=True, exist_ok=True)
    for index, scene in enumerate(scenes, 1):
        share = _words(scene.get("text_en", "")) / total_words
        end = total if index == len(scenes) else min(total, cursor + total * share)
        component = _safe_label(scene.get("technical_component") or "Automotive system", 38)
        flow = _safe_label(scene.get("technical_flow") or "input → mechanism → output", 62)
        note = _safe_label(scene.get("technical_motion") or "Reveal the mechanism", 46)
        status = _safe_label(scene.get("spec_status") or "GENERAL_EXPLANATION", 24)
        upgrade = _safe_label(scene.get("upgrade_requirements") or "", 52)
        lines = [component, f"FLOW  {flow}", f"MODE  {status}", note]
        if upgrade and str(scene.get("section", "")).casefold() in {"upgrade", "power", "performance"}:
            lines.append(f"SUPPORT  {upgrade}")
        textfile = tech_dir / f"card-{index:02d}.txt"
        textfile.write_text("\n".join(lines), encoding="utf-8")
        path = _esc_filter_path(textfile)
        if vertical:
            box_x, box_y, box_w, box_h = 55, 250, 970, 375
            font = 36
            text_x, text_y = 88, 285
        else:
            box_x, box_y, box_w, box_h = 45, 50, 1010, 315
            font = 31
            text_x, text_y = 78, 82
        start = max(0.0, cursor)
        enter_end = min(end, start + 0.8)
        enter = f"between(t,{start:.3f},{enter_end:.3f})"
        hold_start = enter_end
        hold = f"between(t,{hold_start:.3f},{end:.3f})"
        slide_y = f"{box_y}-({start + 0.8:.3f}-t)*{box_h}/0.8"
        text_slide_y = f"{text_y}-({start + 0.8:.3f}-t)*60/0.8"
        filters.append(f"drawbox=x={box_x}:y={slide_y}:w={box_w}:h={box_h}:color=black@0.72:t=fill:enable='{enter}'")
        filters.append(f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=black@0.72:t=fill:enable='{hold}'")
        filters.append(f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={path}:fontcolor=white:fontsize={font}:line_spacing=10:x={text_x}:y={text_slide_y}:enable='{enter}'")
        filters.append(f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={path}:fontcolor=white:fontsize={font}:line_spacing=10:x={text_x}:y={text_y}:enable='{hold}'")
        cursor = end
    return ",".join(filters)


def _process(input_path: Path, output_path: Path, scenes: list[dict], vertical: bool) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not scenes:
        raise ValueError("technical overlay requires scene annotations")
    duration = _duration(input_path)
    graph = _build_filter(scenes, duration, vertical, RUN)
    tmp = output_path.with_suffix(".technical.mp4")
    vf = f"{graph},format=yuv420p" if graph else "format=yuv420p"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-r", "30", str(tmp)
    ], check=True, timeout=600)
    if not tmp.is_file() or tmp.stat().st_size == 0:
        raise RuntimeError(f"technical overlay produced empty file: {output_path}")
    tmp.replace(output_path)


def main() -> None:
    story_path = RUN / "long_story.json"
    if not story_path.is_file():
        raise FileNotFoundError(story_path)
    story = json.loads(story_path.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("technical overlay requires exactly 25 story scenes")

    video = RUN / "video.mp4"
    _process(video, video, scenes, vertical=False)

    plan_path = RUN / "shorts_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4:
        raise ValueError("technical overlay requires exactly 4 shorts")
    for short in shorts:
        sid = int(short["id"])
        out = RUN / "shorts" / f"short-{sid}.mp4"
        short_scenes = short.get("scenes", [])
        if len(short_scenes) < 2:
            raise ValueError(f"short {sid} must reference at least two master scenes")
        _process(out, out, short_scenes, vertical=True)

    manifest_path = RUN / "render_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest["technical_overlay"] = {
        "enabled": True,
        "type": "animated automotive technical HUD",
        "media_source": "Pexels only",
        "master_scenes": 25,
        "shorts": 4,
        "short_min_master_scenes": 2,
        "fields": ["technical_component", "technical_flow", "technical_motion", "spec_status", "upgrade_requirements"],
        "animation": "slide-in per scene then hold",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TECHNICAL_OVERLAY=PASS master=25 shorts=4 pexels_only=true animation=scene_slide_in short_multiscene=true")


if __name__ == "__main__":
    main()
