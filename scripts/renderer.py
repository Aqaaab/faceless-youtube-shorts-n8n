from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RUN.mkdir(parents=True, exist_ok=True)
VOICE = os.getenv("VOICE", "en-US-ChristopherNeural").strip() or "en-US-ChristopherNeural"
TTS_RATE = os.getenv("TTS_RATE", "+5%").strip() or "+5%"
RETRIES = max(1, int(os.getenv("MEDIA_RETRIES", "3")))
RENDER_TIMEOUT = max(60, int(os.getenv("MEDIA_RENDER_TIMEOUT", "240")))
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
LONG_MIN = float(CFG["production"]["long_duration_seconds"]["min"])
LONG_MAX = float(CFG["production"]["long_duration_seconds"]["max"])
SHORT_MIN = float(CFG["production"]["short_duration_seconds"]["min"])
SHORT_MAX = float(CFG["production"]["short_duration_seconds"]["max"])

# Duration contract: no artificial padding is allowed. Validate the real render duration only.


def shell(*cmd: str, timeout: int = RENDER_TIMEOUT) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def shell_retry(*cmd: str, timeout: int = RENDER_TIMEOUT) -> None:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            shell(*cmd, timeout=timeout)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(4, 0.5 * (2 ** attempt)))
    raise RuntimeError(f"command failed after {RETRIES} attempts: {' '.join(cmd)}") from last


def ass_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def wrap_arabic(text: str, max_chars: int = 28, max_lines: int = 2) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    if not normalized:
        return ""
    words = normalized.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return "\\N".join(lines)
    split = max(1, min(len(words) - 1, len(words) // 2))
    return "\\N".join((" ".join(words[:split]), " ".join(words[split:])))


def make_ass(scene: dict, duration: float, dst: Path) -> None:
    text = ass_escape(wrap_arabic(str(scene.get("text_ar", ""))))
    dst.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Arabic,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,180,180,100,1\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,{ass_time(duration)},Arabic,,0,0,100,,{text}\n",
        encoding="utf-8",
    )


def make_vertical_ass(short: dict, durations: list[float], dst: Path) -> None:
    if len(short.get("scenes", [])) != len(durations) or len(durations) < 2:
        raise ValueError(f"Short {short.get('id')} must contain at least two scenes")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: ArabicVertical,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,160,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    cursor = 0.0
    for scene, duration in zip(short["scenes"], durations):
        end = cursor + max(0.05, duration)
        text = ass_escape(wrap_arabic(str(scene.get("text_ar", "")), 20, 2))
        lines.append(f"Dialogue: 0,{ass_time(cursor)},{ass_time(end)},ArabicVertical,,0,0,160,,{text}")
        cursor = end
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


def media_duration(path: Path) -> float:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True, timeout=30).strip()
    value = float(raw)
    if value <= 0:
        raise ValueError(f"invalid duration for {path}")
    return value


def concat_segments(paths: list[Path], output: Path, work: Path) -> None:
    if not paths or any(not p.is_file() for p in paths):
        raise RuntimeError("concat received missing media")
    manifest = work / f"{output.stem}-concat.txt"
    manifest.write_text("".join(f"file '{p.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for p in paths), encoding="utf-8")
    shell_retry("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(output), timeout=300)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"concat produced empty output: {output}")


def _validate_duration(path: Path, minimum: float, maximum: float, label: str) -> float:
    duration = media_duration(path)
    if not minimum <= duration <= maximum:
        raise RuntimeError(f"{label} duration {duration:.2f}s outside {minimum:.2f}-{maximum:.2f}s")
    return duration


def _still_filter(duration: float, vertical: bool = False) -> str:
    frames = max(1, int(duration * 30))
    if vertical:
        return f"scale=1400:2488:force_original_aspect_ratio=increase,crop=1400:2488,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,setsar=1,format=yuv420p"
    return f"scale=2200:1238:force_original_aspect_ratio=increase,crop=2200:1238,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30,setsar=1,format=yuv420p"


def _render_visual(source: Path, kind: str, duration: float, output: Path, vertical: bool = False) -> None:
    vf = _still_filter(duration, vertical) if kind == "image" else ("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,format=yuv420p" if not vertical else "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p")
    if kind == "image":
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(source), "-t", f"{duration:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", str(output)]
    else:
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source), "-t", f"{duration:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", str(output)]
    shell_retry(*cmd, timeout=RENDER_TIMEOUT)


def make_segment(scene: dict, index: int, work: Path, visual_work: Path) -> tuple[Path, float, dict]:
    from visual_generation import prepare_scene_visual
    audio = work / f"{index:02d}.mp3"
    visual, kind = prepare_scene_visual(scene, index, visual_work)
    shell_retry("edge-tts", "--voice", VOICE, "--rate", TTS_RATE, "--text", str(scene["text_en"]), "--write-media", str(audio), timeout=120)
    duration = media_duration(audio)
    ass = work / f"{index:02d}.ass"
    silent = work / f"{index:02d}-visual.mp4"
    segment = work / f"{index:02d}-final.mp4"
    make_ass(scene, duration, ass)
    _render_visual(visual, kind, duration, silent, vertical=False)
    shell_retry("ffmpeg", "-y", "-i", str(silent), "-i", str(audio), "-vf", f"ass={ass.as_posix()}", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-pix_fmt", "yuv420p", "-r", "30", "-shortest", str(segment), timeout=RENDER_TIMEOUT)
    if not segment.is_file() or segment.stat().st_size == 0:
        raise RuntimeError(f"empty segment {index}")
    return segment, duration, {"scene": index, "provider": "generated" if kind == "image" else "pexels", "motion": "ken_burns" if kind == "image" else "live_clip", "path": str(visual)}


def main() -> None:
    source = RUN / "long_story.json"
    plan_path = RUN / "shorts_plan.json"
    if not source.is_file() or not plan_path.is_file():
        raise FileNotFoundError("long_story.json and shorts_plan.json are required")
    story = json.loads(source.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(scenes) != 25 or len(shorts) != 4:
        raise ValueError("renderer requires exactly 25 scenes and 4 shorts")
    work = RUN / "render"
    visual_work = RUN / "media"
    work.mkdir(parents=True, exist_ok=True)
    visual_work.mkdir(parents=True, exist_ok=True)
    segments: list[tuple[Path, float, dict]] = []
    try:
        for index, scene in enumerate(scenes, 1):
            segments.append(make_segment(scene, index, work, visual_work))
        concat_segments([item[0] for item in segments], RUN / "video.mp4", work)
        long_duration = _validate_duration(RUN / "video.mp4", LONG_MIN, LONG_MAX, "Master")
        shorts_dir = RUN / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)
        short_durations: dict[str, float] = {}
        for short in shorts:
            sid = int(short["id"])
            start, end = int(short["scene_start"]), int(short["scene_end"])
            if not (1 <= start <= end <= len(segments)) or end - start + 1 < 2:
                raise ValueError(f"short {sid} scene range invalid")
            selected = segments[start - 1:end]
            source_short = work / f"short-{sid}-source.mp4"
            concat_segments([item[0] for item in selected], source_short, work)
            source_duration = media_duration(source_short)
            if not SHORT_MIN <= source_duration <= SHORT_MAX:
                raise RuntimeError(f"Short {sid} source duration {source_duration:.2f}s outside {SHORT_MIN:.2f}-{SHORT_MAX:.2f}s")
            ass = work / f"short-{sid}.ass"
            make_vertical_ass(short, [item[1] for item in selected], ass)
            output = shorts_dir / f"short-{sid}.mp4"
            shell_retry("ffmpeg", "-y", "-i", str(source_short), "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p,ass={ass.as_posix()}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", "-pix_fmt", "yuv420p", "-r", "30", str(output), timeout=RENDER_TIMEOUT)
            short_durations[str(sid)] = _validate_duration(output, SHORT_MIN, SHORT_MAX, f"Short {sid}")
        manifest = {
            "version": 4,
            "media_pipeline": "generated_still_first_with_pexels_fallback",
            "motion_pipeline": "ken_burns_for_stills_live_motion_for_video",
            "master": {"path": str(RUN / "video.mp4"), "duration": long_duration, "scene_count": 25},
            "shorts": [{"id": int(s["id"]), "path": str(shorts_dir / f"short-{int(s['id'])}.mp4"), "duration": short_durations[str(s["id"])], "scene_start": int(s["scene_start"]), "scene_end": int(s["scene_end"])} for s in shorts],
            "scene_visuals": [record for _, _, record in segments],
        }
        (RUN / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"RENDER=PASS master={long_duration:.2f}s shorts=" + ",".join(f"{k}:{v:.2f}s" for k, v in short_durations.items()))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
