from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RUN.mkdir(parents=True, exist_ok=True)
VOICE = os.getenv("VOICE", "en-US-GuyNeural").strip() or "en-US-GuyNeural"
RETRIES = max(1, int(os.getenv("MEDIA_RETRIES", "3")))
CMD_TIMEOUT = max(30, int(os.getenv("MEDIA_COMMAND_TIMEOUT", "300")))
DOWNLOAD_TIMEOUT = max(15, int(os.getenv("MEDIA_DOWNLOAD_TIMEOUT", "90")))
PEXELS_TIMEOUT = max(10, int(os.getenv("PEXELS_TIMEOUT", "45")))
RENDER_TIMEOUT = max(60, int(os.getenv("MEDIA_RENDER_TIMEOUT", "240")))
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
LONG_MIN = float(CFG["production"]["long_duration_seconds"]["min"])


def shell(*cmd: str, timeout: int = CMD_TIMEOUT) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def shell_retry(*cmd: str, timeout: int = CMD_TIMEOUT, retries: int | None = None) -> None:
    attempts = max(1, retries if retries is not None else RETRIES)
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            shell(*cmd, timeout=timeout)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"command failed after {attempts} attempts: {' '.join(cmd)}") from last


def download(url: str, dst: Path) -> None:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "faceless-youtube-shorts-n8n/2.0"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
                data = response.read()
            if not data:
                raise RuntimeError("download returned an empty file")
            dst.write_bytes(data)
            return
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"media download failed: {url}") from last


def pexels(query: str) -> str:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is required for real rendering")
    q = urllib.parse.quote(query.strip())
    if not q:
        raise RuntimeError("Pexels query is empty")
    url = f"https://api.pexels.com/videos/search?query={q}&per_page=8&orientation=portrait"
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "faceless-youtube-shorts-n8n/2.0"})
            with urllib.request.urlopen(req, timeout=PEXELS_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            candidates = []
            for video in data.get("videos", []):
                for item in video.get("video_files", []):
                    link = item.get("link")
                    width = int(item.get("width") or 0)
                    height = int(item.get("height") or 0)
                    if link and width > 0 and height > 0:
                        portrait_bonus = 1 if height >= width else 0
                        candidates.append((portrait_bonus, width * height, link))
            if candidates:
                return max(candidates, key=lambda x: (x[0], x[1]))[2]
            raise RuntimeError(f"No Pexels video found for query: {query}")
        except urllib.error.HTTPError as exc:
            last = RuntimeError(f"Pexels HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}")
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
        if attempt + 1 < RETRIES:
            time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"Pexels lookup failed for query: {query}") from last


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
    words = normalized.split(" ")
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
    first = words[:split]
    second = words[split:]
    while len(" ".join(first)) > max_chars and len(first) > 1:
        second.insert(0, first.pop())
    while len(" ".join(second)) > max_chars and len(second) > 1:
        first.append(second.pop(0))
    return "\\N".join((" ".join(first), " ".join(second)))


def make_ass(sc: dict, duration_seconds: float, dst: Path) -> None:
    ar = ass_escape(wrap_arabic(sc["text_ar"].strip()))
    content = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Arabic,DejaVu Sans,56,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,4,1,2,240,240,125,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    content += f"Dialogue: 0,0:00:00.00,{ass_time(duration_seconds)},Arabic,,240,240,125,,{ar}\n"
    dst.write_text(content, encoding="utf-8")


def make_vertical_ass(short: dict, durations: list[float], dst: Path) -> None:
    content = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: ArabicVertical,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,4,1,2,120,120,230,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    cursor = 0.0
    scenes = short.get("scenes", [])
    if len(scenes) != len(durations):
        raise ValueError(f"Short {short.get('id')} caption timing mismatch")
    for scene, dur in zip(scenes, durations):
        end = cursor + max(0.05, dur)
        text = ass_escape(wrap_arabic(str(scene.get("text_ar", "")), max_chars=20, max_lines=2))
        content += f"Dialogue: 0,{ass_time(cursor)},{ass_time(end)},ArabicVertical,,120,120,230,,{text}\n"
        cursor = end
    dst.write_text(content, encoding="utf-8")


def make_segment(sc: dict, index: int, work: Path) -> tuple[Path, Path, float]:
    clip = work / f"{index:02d}.mp4"
    audio = work / f"{index:02d}.mp3"
    seg = work / f"{index:02d}-seg.mp4"
    ass = work / f"{index:02d}.ass"
    subtitled = work / f"{index:02d}-final.mp4"
    download(pexels(sc["pexels_query"]), clip)
    shell_retry("edge-tts", "--voice", VOICE, "--text", sc["text_en"], "--write-media", str(audio), timeout=120)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)], text=True)
    duration = float(probe.strip())
    if duration <= 0:
        raise RuntimeError(f"TTS produced invalid duration for scene {index}")
    make_ass(sc, duration, ass)
    shell(
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-r", "30", str(seg), timeout=RENDER_TIMEOUT,
    )
    shell(
        "ffmpeg", "-y", "-i", str(seg), "-vf", f"ass={ass.as_posix()}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "copy", "-pix_fmt", "yuv420p", "-r", "30", str(subtitled), timeout=RENDER_TIMEOUT,
    )
    if not subtitled.is_file() or subtitled.stat().st_size == 0 or not seg.is_file() or seg.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg produced an empty segment: {index}")
    return seg, subtitled, duration


def concat_segments(paths: list[Path], output: Path, work: Path) -> None:
    if not paths or any(not p.is_file() for p in paths):
        raise RuntimeError("concat received missing media segments")
    manifest = work / f"{output.stem}-concat.txt"
    manifest.write_text("".join(f"file '{p.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for p in paths), encoding="utf-8")
    shell_retry("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(output), timeout=300, retries=2)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg concat produced an empty file: {output.name}")


def media_duration(path: Path) -> float:
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True)
    return float(raw.strip())


def ensure_long_min_duration(path: Path, work: Path) -> None:
    current = media_duration(path)
    if current >= LONG_MIN:
        return
    padded = work / "video-padded.mp4"
    target = LONG_MIN + 0.5
    shell(
        "ffmpeg", "-y", "-i", str(path), "-vf", f"tpad=stop_mode=clone:stop_duration={max(0.0, target-current):.3f}",
        "-af", "apad", "-t", f"{target:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-r", "30", str(padded), timeout=RENDER_TIMEOUT,
    )
    if not padded.is_file() or padded.stat().st_size == 0:
        raise RuntimeError("long-video duration padding produced an empty file")
    padded.replace(path)
    final = media_duration(path)
    if final < LONG_MIN:
        raise RuntimeError(f"unable to satisfy long video minimum duration: {final:.2f}s < {LONG_MIN:.2f}s")


def main() -> None:
    source = RUN / "long_story.json"
    if not source.is_file():
        raise FileNotFoundError(f"missing story: {source}")
    story = json.loads(source.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("renderer requires exactly 25 scenes")
    plan_path = RUN / "shorts_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError("shorts_plan.json is required before rendering")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4:
        raise ValueError("shorts plan must contain exactly 4 shorts")

    work = RUN / "render"
    work.mkdir(parents=True, exist_ok=True)
    segments: list[tuple[Path, Path, float]] = []
    try:
        for index, scene in enumerate(scenes, 1):
            segments.append(make_segment(scene, index, work))
        final_segments = [item[1] for item in segments]
        raw_segments = [item[0] for item in segments]
        concat_segments(final_segments, RUN / "video.mp4", work)
        ensure_long_min_duration(RUN / "video.mp4", work)

        shorts_dir = RUN / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)
        for short in shorts:
            sid = int(short["id"])
            start = int(short["scene_start"])
            end = int(short["scene_end"])
            if not (1 <= start <= end <= len(raw_segments)):
                raise ValueError(f"short {sid} scene range is invalid: {start}-{end}")
            selected = raw_segments[start - 1 : end]
            selected_durations = [item[2] for item in segments[start - 1 : end]]
            source_short = work / f"short-{sid}-source.mp4"
            concat_segments(selected, source_short, work)
            vertical_ass = work / f"short-{sid}-vertical.ass"
            make_vertical_ass(short, selected_durations, vertical_ass)
            cropped = work / f"short-{sid}-cropped.mp4"
            out = shorts_dir / f"short-{sid}.mp4"
            source_duration = media_duration(source_short)
            pad = max(0.0, 45.0 - source_duration)
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)/2:(ih-1920)/2,setsar=1,format=yuv420p"
            if pad > 0.01:
                vf = f"tpad=stop_mode=clone:stop_duration={pad:.3f},{vf}"
            shell(
                "ffmpeg", "-y", "-i", str(source_short), "-t", "45", "-vf", vf,
                "-af", "apad", "-t", "45", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-r", "30", str(cropped), timeout=RENDER_TIMEOUT,
            )
            shell(
                "ffmpeg", "-y", "-i", str(cropped), "-vf", f"ass={vertical_ass.as_posix()}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy",
                "-pix_fmt", "yuv420p", "-r", "30", str(out), timeout=RENDER_TIMEOUT,
            )
            if not out.is_file() or out.stat().st_size == 0:
                raise RuntimeError(f"Short {sid} render is empty")
            final_duration = media_duration(out)
            if not 44.5 <= final_duration <= 45.1:
                raise RuntimeError(f"Short {sid} final duration is {final_duration:.2f}s, expected about 45s")

        manifest = {
            "version": 2,
            "long_subtitles": "baked_before_concat",
            "short_subtitles": "baked_after_9x16_crop",
            "short_safe_zone": {"margin_left": 120, "margin_right": 120, "margin_bottom": 230, "max_chars_per_line": 20, "max_lines": 2},
            "short_duration_target": 45.0,
            "short_count": len(shorts),
            "long_duration_min": LONG_MIN,
        }
        (RUN / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("REAL_RENDER=PASS subtitles=vertical-safe-zone strict_duration=checked")


if __name__ == "__main__":
    main()
