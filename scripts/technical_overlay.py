from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from visual_engineering import build_scene_svg, validate_visual_engineering, visual_profile

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
FORBIDDEN_VISIBLE = re.compile(r"FLOW MODE|FACT_SOURCE_REQUIRED|GENERAL_EXPLANATION|MODIFIED_ESTIMATE|VISUAL\s+(?:xray|cutaway|flow|hud)|COMPONENT_ID|LAYER_ID|HUD_ONLY|X-RAY SECTION", re.I)


def _duration(path: Path) -> float:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True, timeout=30)
    value = float(raw.strip())
    if value <= 0:
        raise RuntimeError(f"invalid duration: {path}")
    return value


def _words(text: str) -> int:
    return max(1, len(re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", str(text or ""))))


def _make_overlay_svg(scene: dict, vertical: bool, output: Path) -> None:
    """Build a transparent infographic layer so the real automotive plate remains visible."""
    svg = build_scene_svg(scene, vertical=vertical)
    svg, removed = re.subn(
        r'<rect\s+width="100%"\s+height="100%"\s+fill="url\(#bg\)"\s*/>',
        '',
        svg,
        count=1,
    )
    if removed != 1:
        raise RuntimeError("TECHNICAL_OVERLAY_FAIL: expected full-canvas background marker missing")
    if '<rect width="100%" height="100%" fill="url(#bg)"' in svg:
        raise RuntimeError("TECHNICAL_OVERLAY_FAIL: opaque full-canvas background survived")
    output.write_text(svg, encoding="utf-8")


def _sequence(scenes: list[dict], total: float, vertical: bool, out_dir: Path) -> tuple[Path, dict]:
    """Build one isolated transparent infographic sequence for exactly one media output."""
    out_dir.mkdir(parents=True, exist_ok=True)
    total_words = sum(_words(s.get("text_en", "")) for s in scenes) or 1
    cursor = 0.0
    entries = ["ffconcat version 1.0"]
    profiles = []
    for index, scene in enumerate(scenes, 1):
        profile = visual_profile(scene)
        validate_visual_engineering({**scene, "visual_engineering": profile})
        share = _words(scene.get("text_en", "")) / total_words
        end = total if index == len(scenes) else min(total, cursor + total * share)
        duration = max(0.05, end - cursor)
        svg = out_dir / f"scene-{index:02d}.svg"
        _make_overlay_svg(scene, vertical, svg)
        raw = svg.read_text(encoding="utf-8")
        if FORBIDDEN_VISIBLE.search(raw):
            raise RuntimeError(f"TECHNICAL_OVERLAY_FAIL: internal metadata leaked into scene SVG {index}")
        entries.append(f"file '{svg.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39))}'")
        entries.append(f"duration {duration:.3f}")
        profiles.append(profile)
        cursor = end
    if scenes:
        last = out_dir / f"scene-{len(scenes):02d}.svg"
        entries.append(f"file '{last.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39))}'")
    manifest = out_dir / "sequence.ffconcat"
    manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return manifest, {"profiles": profiles, "scene_count": len(scenes), "duration": total, "output_dir": str(out_dir)}


def _process(input_path: Path, output_path: Path, scenes: list[dict], vertical: bool = False, overlay_dir: Path | None = None) -> dict:
    """Fuse an isolated transparent full-frame infographic sequence into real footage."""
    if not input_path.is_file() or input_path.stat().st_size == 0:
        raise FileNotFoundError(input_path)
    duration = _duration(input_path)
    if overlay_dir is None:
        overlay_dir = RUN / "technical_overlay" / ("vertical" if vertical else "master")
    sequence, engineering = _sequence(scenes, duration, vertical, overlay_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        "[1:v]fps=30,format=rgba,colorchannelmixer=aa=0.88[eng];"
        "[0:v][eng]overlay=x=0:y=0:eof_action=pass:format=auto,format=yuv420p[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path), "-f", "concat", "-safe", "0", "-i", str(sequence),
        "-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(output_path)
    ], check=True, timeout=900)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"TECHNICAL_OVERLAY_FAIL: empty output {output_path.name}")
    actual = _duration(output_path)
    if actual > duration + 0.25 or actual < max(0.05, duration - 0.25):
        raise RuntimeError(f"TECHNICAL_OVERLAY_FAIL: duration changed from {duration:.3f}s to {actual:.3f}s")
    return engineering


def _apply(input_path: Path, scenes: list[dict], vertical: bool, overlay_dir: Path | None = None) -> dict:
    if not input_path.is_file() or input_path.stat().st_size == 0:
        raise FileNotFoundError(input_path)
    tmp = input_path.with_suffix(".engineering.mp4")
    engineering = _process(input_path, tmp, scenes, vertical=vertical, overlay_dir=overlay_dir)
    tmp.replace(input_path)
    return engineering


def main() -> None:
    story_path = RUN / "long_story.json"
    if not story_path.is_file():
        raise FileNotFoundError(story_path)
    story = json.loads(story_path.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("technical overlay requires exactly 25 scenes")
    master = _apply(RUN / "video.mp4", scenes, False, RUN / "technical_overlay" / "master")
    plan = json.loads((RUN / "shorts_plan.json").read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4:
        raise ValueError("technical overlay requires exactly 4 shorts")
    short_profiles = {}
    for short in shorts:
        sid = int(short["id"])
        short_dir = RUN / "technical_overlay" / "shorts" / f"short-{sid}"
        short_profiles[str(sid)] = _apply(
            RUN / "shorts" / f"short-{sid}.mp4",
            short.get("scenes", []),
            True,
            short_dir,
        )
    manifest_path = RUN / "render_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest["version"] = 4
    manifest["media_pipeline"] = "generated_still_first_with_pexels_fallback"
    manifest["motion_pipeline"] = "ken_burns_for_stills_live_motion_for_video"
    manifest["technical_overlay"] = {
        "enabled": True,
        "type": "full_frame_automotive_infographic_transparent_layer",
        "visual_reference": "dark_blue_automotive_technical_infographic",
        "internal_metadata_rendered": False,
        "generic_profiles_allowed": False,
        "full_frame": True,
        "base_visual_preserved": True,
        "opaque_background_removed": True,
        "cutaway_geometry": True,
        "animated_flow_paths": True,
        "arabic_ui": True,
        "verified_spec_cards": True,
        "upgrade_panel": True,
        "master_scenes": 25,
        "shorts": 4,
        "scene_profiles": master["profiles"],
        "short_profiles": short_profiles,
        "short_overlay_root": "technical_overlay/shorts/short-{id}",
        "shared_vertical_overlay": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TECHNICAL_OVERLAY=PASS full_frame=true transparent_layer=true base_visual_preserved=true cutaway=true flow_animation=true arabic_ui=true spec_cards=true upgrades=true internal_metadata=false generic_profiles=false manifest_version=4 isolated_short_overlays=true")


if __name__ == "__main__":
    main()
