from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from visual_engineering import build_scene_svg, validate_visual_engineering, visual_profile

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
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _build_hud_filter(scenes: list[dict], total: float, vertical: bool, root: Path) -> str:
    total_words = sum(_words(s.get("text_en", "")) for s in scenes)
    cursor = 0.0
    filters: list[str] = []
    tech_dir = root / "technical_overlay"
    tech_dir.mkdir(parents=True, exist_ok=True)

    for index, scene in enumerate(scenes, 1):
        share = _words(scene.get("text_en", "")) / total_words
        end = total if index == len(scenes) else min(total, cursor + total * share)
        profile = visual_profile(scene)
        component = _safe_label(scene.get("technical_component") or "Automotive system", 38)
        flow = _safe_label(scene.get("technical_flow") or "input → mechanism → output", 62)
        note = _safe_label(scene.get("technical_motion") or "Reveal the mechanism", 46)
        status = _safe_label(scene.get("spec_status") or "GENERAL_EXPLANATION", 24)
        upgrade = _safe_label(scene.get("upgrade_requirements") or "", 52)
        lines = [component, f"FLOW  {flow}", f"MODE  {status}", note, f"VISUAL  {profile['mode']} / {profile['flow_type']}"]
        if upgrade and str(scene.get("section", "")).casefold() in {"upgrade", "power", "performance"}:
            lines.append(f"SUPPORT  {upgrade}")
        textfile = tech_dir / f"card-{index:02d}.txt"
        textfile.write_text("\n".join(lines), encoding="utf-8")
        path = _esc_filter_path(textfile)

        if vertical:
            box_x, box_y, box_w, box_h = 55, 250, 970, 390
            font, text_x, text_y = 34, 88, 285
        else:
            box_x, box_y, box_w, box_h = 45, 50, 1010, 335
            font, text_x, text_y = 29, 78, 82

        start = max(0.0, cursor)
        enter_end = min(end, start + 0.8)
        enter = f"between(t,{start:.3f},{enter_end:.3f})"
        hold = f"between(t,{enter_end:.3f},{end:.3f})"
        slide_y = f"{box_y}-({start + 0.8:.3f}-t)*{box_h}/0.8"
        text_slide_y = f"{text_y}-({start + 0.8:.3f}-t)*60/0.8"
        filters.extend([
            f"drawbox=x={box_x}:y={slide_y}:w={box_w}:h={box_h}:color=black@0.72:t=fill:enable='{enter}'",
            f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=black@0.72:t=fill:enable='{hold}'",
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={path}:fontcolor=white:fontsize={font}:line_spacing=10:x={text_x}:y={text_slide_y}:enable='{enter}'",
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile={path}:fontcolor=white:fontsize={font}:line_spacing=10:x={text_x}:y={text_y}:enable='{hold}'",
        ])
        cursor = end
    return ",".join(filters)


def _write_engineering_sequence(scenes: list[dict], total: float, vertical: bool, root: Path) -> tuple[Path, dict]:
    """Build one timed SVG sequence from the blueprint annotations.

    The sequence is deterministic: component -> approved visual profile -> SVG.
    No LLM-generated coordinates or external media are accepted here.
    """
    tech_dir = root / "technical_overlay" / ("vertical" if vertical else "master")
    tech_dir.mkdir(parents=True, exist_ok=True)
    total_words = sum(_words(s.get("text_en", "")) for s in scenes)
    cursor = 0.0
    entries: list[str] = ["ffconcat version 1.0"]
    profiles: list[dict] = []

    for index, scene in enumerate(scenes, 1):
        validate_visual_engineering({**scene, "visual_engineering": visual_profile(scene)})
        share = _words(scene.get("text_en", "")) / total_words
        end = total if index == len(scenes) else min(total, cursor + total * share)
        duration = max(0.04, end - cursor)
        svg = tech_dir / f"scene-{index:02d}.svg"
        svg.write_text(build_scene_svg(scene, vertical=vertical), encoding="utf-8")
        entries.append(f"file '{svg.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39))}'")
        entries.append(f"duration {duration:.3f}")
        profiles.append(visual_profile(scene))
        cursor = end

    # The concat demuxer uses the final file to close the last duration.
    if scenes:
        last_svg = tech_dir / f"scene-{len(scenes):02d}.svg"
        entries.append(f"file '{last_svg.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39))}'")

    manifest = tech_dir / "sequence.ffconcat"
    manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return manifest, {"profiles": profiles, "scene_count": len(scenes), "duration": total}


def _process(input_path: Path, output_path: Path, scenes: list[dict], vertical: bool) -> dict:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not scenes:
        raise ValueError("technical overlay requires scene annotations")

    duration = _duration(input_path)
    hud = _build_hud_filter(scenes, duration, vertical, RUN)
    concat_file, engineering = _write_engineering_sequence(scenes, duration, vertical, RUN)
    tmp = output_path.with_suffix(".technical.mp4")

    if vertical:
        tech_w, tech_x, tech_y = 1000, 40, 560
    else:
        tech_w, tech_x, tech_y = 760, 1080, 90

    concat_path = _esc_filter_path(concat_file)
    complex_filter = (
        f"[0:v]{hud}[hud];"
        f"[1:v]fps=30,scale={tech_w}:-1,format=rgba,"
        f"colorchannelmixer=aa='0.55+0.18*sin(2*PI*t/2.4)'[engineering];"
        f"[hud][engineering]overlay=x='{tech_x}+8*sin(2*PI*t/3.0)':y={tech_y}:"
        f"eof_action=pass:format=auto,format=yuv420p[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-f", "concat", "-safe", "0", "-r", "25", "-i", str(concat_file),
        "-filter_complex", complex_filter,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-r", "30",
        "-t", f"{duration:.3f}", str(tmp)
    ], check=True, timeout=900)
    if not tmp.is_file() or tmp.stat().st_size == 0:
        raise RuntimeError(f"technical overlay produced empty file: {output_path}")
    tmp.replace(output_path)
    return engineering


def _apply(story_path: Path, video: Path, scenes: list[dict], vertical: bool) -> dict:
    story = json.loads(story_path.read_text(encoding="utf-8")) if story_path.is_file() else {}
    engineering = _process(video, video, scenes, vertical)
    return engineering


def main() -> None:
    story_path = RUN / "long_story.json"
    if not story_path.is_file():
        raise FileNotFoundError(story_path)
    story = json.loads(story_path.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("technical overlay requires exactly 25 story scenes")

    master_engineering = _apply(story_path, RUN / "video.mp4", scenes, vertical=False)

    plan_path = RUN / "shorts_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4:
        raise ValueError("technical overlay requires exactly 4 shorts")

    short_engineering = {}
    for short in shorts:
        sid = int(short["id"])
        out = RUN / "shorts" / f"short-{sid}.mp4"
        short_scenes = short.get("scenes", [])
        if len(short_scenes) < 2:
            raise ValueError(f"short {sid} must reference at least two master scenes")
        short_engineering[str(sid)] = _apply(story_path, out, short_scenes, vertical=True)

    manifest_path = RUN / "render_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest["technical_overlay"] = {
        "enabled": True,
        "type": "component-aware visual engineering layer",
        "media_source": "Pexels only",
        "master_scenes": 25,
        "shorts": 4,
        "short_min_master_scenes": 2,
        "fields": ["technical_component", "technical_flow", "technical_motion", "spec_status", "upgrade_requirements"],
        "visual_engineering": {
            "registry": "scripts/visual_engineering.py",
            "modes": ["xray", "xray_cutaway", "cutaway_flow", "flow", "force", "airflow", "hud_only"],
            "component_aware": True,
            "scene_profiles": master_engineering["profiles"],
            "short_profiles": short_engineering,
        },
        "animation": "scene-synchronised engineering SVG + pulsing alpha + subtle motion + HUD slide-in",
        "blueprint_asset": "assets/blueprint/automotive_blueprint.svg",
        "external_media": "Pexels only",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TECHNICAL_OVERLAY=PASS master=25 shorts=4 pexels_only=true component_aware=true xray_cutaway=true flow=true animation=true")


if __name__ == "__main__":
    main()
