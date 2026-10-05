from __future__ import annotations

import os
import re

import hashlib
import json
import subprocess
from pathlib import Path

from .core import RUN, Story
from .production_contract import FFMPEG_CRF, FFMPEG_PRESET, RENDER_FPS, SUBTITLE_FONT_SIZE, SHORT_SUBTITLE_FONT_SIZE


def _run(c):
    subprocess.run(c, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _ts(x: float) -> str:
    total_ms = max(0, int(round(float(x) * 1000)))
    sec, ms = divmod(total_ms, 1000)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _subtitle_text(text: str, max_chars: int = 42) -> str:
    """Wrap narration into real SRT lines, each bounded by max_chars."""
    words = str(text).strip().split()
    lines, current = [], []
    for word in words:
        if len(word) > max_chars:
            if current:
                lines.append(" ".join(current))
                current = []
            for start in range(0, len(word), max_chars):
                lines.append(word[start:start + max_chars])
            continue
        candidate = " ".join(current + [word])
        if current and len(candidate) > max_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)



def _render_segment(frame: Path, audio: Path, duration: float, out: Path, size: str, scene_id: int) -> None:
    frames = max(30, int(round(duration * 30)))
    phase = scene_id % 6
    x_expr = {
        0: "iw/2-(iw/zoom/2)", 1: "iw/2-(iw/zoom/2)+20*sin(on/105)",
        2: "iw/2-(iw/zoom/2)-20*sin(on/105)", 3: "iw/2-(iw/zoom/2)+14*sin(on/80)",
        4: "iw/2-(iw/zoom/2)-14*sin(on/80)", 5: "iw/2-(iw/zoom/2)+10*sin(on/60)",
    }[phase]
    y_expr = {
        0: "ih/2-(ih/zoom/2)", 1: "ih/2-(ih/zoom/2)+10*sin(on/120)",
        2: "ih/2-(ih/zoom/2)-10*sin(on/120)", 3: "ih/2-(ih/zoom/2)+8*sin(on/90)",
        4: "ih/2-(ih/zoom/2)-8*sin(on/90)", 5: "ih/2-(ih/zoom/2)+6*sin(on/70)",
    }[phase]
    vf = f"zoompan=z='min(1.0+on/{frames}*0.065,1.065)':x='{x_expr}':y='{y_expr}':d={frames}:s={size}:fps=RENDER_FPS"
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-i", str(audio), "-t", str(duration),
        "-vf", vf, "-af", f"apad=pad_dur={duration},atrim=duration={duration},loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-ar", "48000", "-b:a", "192k", "-shortest", "-video_track_timescale", "90000", str(out)
    ])




# Production render v5: use Blender's temporal scene clips in production.
from .arabic_font import ensure_ready
from .short_selector import load_selected
from .tts import load_word_timings


def _mux_motion(video: Path, audio: Path, duration: float, out: Path) -> None:
    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-t", f"{float(duration):.6f}",
        "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
        "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={float(duration):.6f}",
        "-movflags", "+faststart", str(out)
    ])


def _concat(paths: list[Path], out: Path) -> None:
    manifest = out.with_suffix(".concat.txt")
    manifest.write_text("".join(f"file '{p.resolve()}'\n" for p in paths), encoding="utf-8")
    try:
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(out)])
    finally:
        manifest.unlink(missing_ok=True)


def render_long(story: Story, out: Path = RUN / "master.mp4"):
    frames = RUN / "frames"
    segs = RUN / "segments"
    frames.mkdir(parents=True, exist_ok=True)
    segs.mkdir(parents=True, exist_ok=True)
    motion_required = os.getenv("AUTOMOTIVE_RENDER_MOTION", "0").strip().lower() in {"1", "true", "yes"}
    segments: list[Path] = []
    for s in story.scenes:
        audio = RUN / "audio" / f"scene_{s.id:02d}.mp3"
        if not audio.is_file():
            raise FileNotFoundError(audio)
        seg = segs / f"scene_{s.id:02d}.mp4"
        motion = RUN / "scenes" / f"scene_{s.id:02d}.motion.mp4"
        raster_source = RUN / "scenes" / f"scene_{s.id:02d}.png"
        if motion_required:
            if not motion.is_file():
                raise RuntimeError(f"TRUE MOTION REQUIRED: missing Blender temporal clip {motion}")
            _mux_motion(motion, audio, float(s.duration), seg)
        else:
            if not raster_source.is_file():
                raise FileNotFoundError(raster_source)
            framesource = frames / f"scene_{s.id:02d}.png"
            framesource.write_bytes(raster_source.read_bytes())
            _render_segment(framesource, audio, float(s.duration), seg, "1920x1080", s.id)
        segments.append(seg)
    _concat(segments, out)


def _format_srt_time(seconds: float) -> str:
    return _ts(max(0.0, seconds))


def _write_word_srt(rows_source, path: Path, max_words: int = 4) -> dict:
    rows = []
    buffer: list[tuple[float, float, str]] = []
    sequence = 1
    for start, end, word in rows_source:
        if end <= start:
            continue
        buffer.append((start, end, word))
        if len(buffer) >= max_words or re.search(r"[.!؟،]$", word):
            rows.append(
                f"{sequence}\n{_format_srt_time(buffer[0][0])} --> {_format_srt_time(buffer[-1][1])}\n"
                + " ".join(item[2] for item in buffer)
                + "\n"
            )
            sequence += 1
            buffer = []
    if buffer:
        rows.append(
            f"{sequence}\n{_format_srt_time(buffer[0][0])} --> {_format_srt_time(buffer[-1][1])}\n"
            + " ".join(item[2] for item in buffer)
            + "\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")
    return {"cue_count": len(rows), "word_timed": bool(rows)}


def write_srt(story: Story, path: Path = RUN / "arabic.srt"):
    rows = []
    clock = 0.0
    for scene in story.scenes:
        for word in load_word_timings(scene.id):
            rows.append((clock + float(word["start"]), clock + float(word["end"]), str(word.get("text", ""))))
        clock += float(scene.duration)
    report = _write_word_srt(rows, path, max_words=4)
    if not report["word_timed"]:
        raise RuntimeError("SUBTITLE TIMING FAILED: no word-level subtitle cues were produced")
    return report


def _subtitle_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:")


def burn_subtitles(src: Path, srt: Path, out: Path):
    font_gate = ensure_ready(RUN / "arabic_font_gate.json", strict=True)
    family = font_gate["family"]
    fontsdir = Path(font_gate["font_file"]).parent.resolve()
    style = (
        f"FontName={family},FontSize={SUBTITLE_FONT_SIZE},Alignment=2,MarginV=76,Outline=2,"
        "Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
    )
    # Noto Sans Arabic remains one of the supported discovered families; no renderer path is hardcoded to it.
    filter_expr = (
        f"subtitles={_subtitle_filter_path(srt)}:fontsdir={_subtitle_filter_path(fontsdir)}:"
        f"force_style='{style}'"
    )
    _run([
        "ffmpeg", "-y", "-i", str(src), "-vf", filter_expr,
        "-c:v", "libx264", "-preset", FFMPEG_PRESET, "-crf", str(FFMPEG_CRF),
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)
    ])
    marker = {
        "burned": True,
        "source": src.name,
        "output": out.name,
        "font_family": family,
        "font_file": font_gate["font_file"],
        "font_gate_pass": True,
        "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "subtitle_file": str(srt),
        "subtitle_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
        "style": style,
    }
    (RUN / "subtitle_burn.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")


def _candidate_srt(story: Story, candidate: dict, path: Path) -> dict:
    rows = []
    local_clock = 0.0
    for sid in candidate["scene_ids"]:
        scene = next(s for s in story.scenes if s.id == sid)
        trim_start = float(candidate.get("start_offset", 0.0)) if sid == candidate["start_scene"] else 0.0
        for word in load_word_timings(sid):
            start = local_clock + float(word["start"]) - float(candidate.get("start_offset", 0.0))
            end = local_clock + float(word["end"]) - float(candidate.get("start_offset", 0.0))
            if end <= 0 or start >= float(candidate["duration"]):
                continue
            rows.append((max(0.0, start), min(float(candidate["duration"]), end), str(word.get("text", ""))))
        local_clock += float(scene.duration)
    return _write_word_srt(rows, path, max_words=3)


def render_shorts(story: Story, out_dir: Path = RUN / "shorts"):
    import copy
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = load_selected()
    selected_scene_ids = sorted({sid for c in candidates for sid in c["scene_ids"]})
    vertical_story = copy.copy(story)
    vertical_story.scenes = [s for s in story.scenes if s.id in selected_scene_ids]
    generate_vertical_visuals(vertical_story)

    motion_required = os.getenv("AUTOMOTIVE_RENDER_MOTION", "0").strip().lower() in {"1", "true", "yes"}
    evidence = []
    for idx, candidate in enumerate(candidates, 1):
        seg_dir = RUN / f"short_segments_{idx}"
        seg_dir.mkdir(exist_ok=True, parents=True)
        segments = []
        for sid in candidate["scene_ids"]:
            video = RUN / "vertical_scenes" / f"scene_{sid:02d}.motion.mp4"
            audio = RUN / "audio" / f"scene_{sid:02d}.mp3"
            if not audio.is_file():
                raise FileNotFoundError(audio)
            if motion_required:
                if not video.is_file():
                    raise RuntimeError(f"TRUE MOTION REQUIRED: missing portrait temporal clip {video}")
                segment = seg_dir / f"scene_{sid:02d}.mp4"
                _mux_motion(video, audio, float(next(s.duration for s in story.scenes if s.id == sid)), segment)
            else:
                frame = RUN / "vertical_scenes" / f"scene_{sid:02d}.png"
                if not frame.is_file():
                    raise FileNotFoundError(frame)
                segment = seg_dir / f"scene_{sid:02d}.mp4"
                _render_segment(frame, audio, float(next(s.duration for s in story.scenes if s.id == sid)), segment, "1080x1920", sid)
            segments.append(segment)

        raw = seg_dir / "raw.mp4"
        _concat(segments, raw)
        candidate_srt = seg_dir / "short.srt"
        subtitle_info = _candidate_srt(story, candidate, candidate_srt)
        out = out_dir / f"short_{idx}.mp4"
        start_offset = float(candidate.get("start_offset", 0.0))
        duration = float(candidate["duration"])
        font_gate = ensure_ready(RUN / "arabic_font_gate.json", strict=True)
        family = font_gate["family"]
        fontsdir = Path(font_gate["font_file"]).parent.resolve()
        style = f"FontName={family},FontSize={SHORT_SUBTITLE_FONT_SIZE},Alignment=2,MarginV=92,Outline=2,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
        vf = (
            f"subtitles={_subtitle_filter_path(candidate_srt)}:fontsdir={_subtitle_filter_path(fontsdir)}:"
            f"force_style='{style}'"
        )
        _run([
            "ffmpeg", "-y", "-ss", f"{start_offset:.3f}", "-i", str(raw),
            "-t", f"{duration:.3f}", "-vf", vf,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
            "-movflags", "+faststart", str(out)
        ])
        evidence.append(
            {
                "file": str(out),
                "burned": True,
                "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                "output_size": out.stat().st_size,
                "duration": duration,
                "candidate_id": candidate["candidate_id"],
                "source_scene_ids": candidate["scene_ids"],
                "selection_score": candidate.get("score"),
                "subtitle_sha256": hashlib.sha256(candidate_srt.read_bytes()).hexdigest(),
                "cue_count": subtitle_info["cue_count"],
                "word_timed": subtitle_info["word_timed"],
                "font_family": family,
            }
        )
    (RUN / "short_subtitles_burn.json").write_text(json.dumps({"shorts": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
