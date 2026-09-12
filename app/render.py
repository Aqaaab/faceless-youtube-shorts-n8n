from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .core import RUN, Story
from .vertical_visuals import generate_vertical_visuals


def _run(c):
    subprocess.run(c, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _ts(x: float) -> str:
    total_ms = max(0, int(round(float(x) * 1000)))
    sec, ms = divmod(total_ms, 1000)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _subtitle_text(text: str, max_chars: int = 42) -> str:
    """Wrap subtitles without creating an oversized rebalance line.

    The previous implementation collapsed any narration producing >2 wrapped
    lines into two word-balanced lines. That could create a second line much
    longer than the artifact gate's 68-character limit. Keep every generated
    line bounded by max_chars instead; ASS/ffmpeg can render 3+ compact lines
    when the narration is long.
    """
    words = str(text).strip().split()
    lines, current = [], []
    for word in words:
        # A single pathological token must not make the gate fail forever.
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
    return "\\N".join(lines)


def _render_image(svg: Path, png: Path, size: str) -> None:
    _run(["ffmpeg", "-y", "-i", str(svg), "-frames:v", "1", "-vf", f"scale={size}:flags=lanczos", str(png)])


def _render_segment(frame: Path, audio: Path, duration: float, out: Path, size: str, scene_id: int) -> None:
    frames = max(30, int(round(duration * 30)))
    # Purposeful editorial camera movement: slow push with a scene-dependent lateral drift.
    phase = scene_id % 6
    x_expr = {
        0: "iw/2-(iw/zoom/2)",
        1: "iw/2-(iw/zoom/2)+20*sin(on/105)",
        2: "iw/2-(iw/zoom/2)-20*sin(on/105)",
        3: "iw/2-(iw/zoom/2)+14*sin(on/80)",
        4: "iw/2-(iw/zoom/2)-14*sin(on/80)",
        5: "iw/2-(iw/zoom/2)+10*sin(on/60)",
    }[phase]
    y_expr = {
        0: "ih/2-(ih/zoom/2)",
        1: "ih/2-(ih/zoom/2)+10*sin(on/120)",
        2: "ih/2-(ih/zoom/2)-10*sin(on/120)",
        3: "ih/2-(ih/zoom/2)+8*sin(on/90)",
        4: "ih/2-(ih/zoom/2)-8*sin(on/90)",
        5: "ih/2-(ih/zoom/2)+6*sin(on/70)",
    }[phase]
    vf = f"zoompan=z='min(1.0+on/{frames}*0.065,1.065)':x='{x_expr}':y='{y_expr}':d={frames}:s={size}:fps=30"
    _run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-i", str(audio),
        "-t", str(duration), "-vf", vf,
        "-af", f"apad=pad_dur={duration},atrim=duration={duration},loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-shortest",
        "-video_track_timescale", "90000", str(out)
    ])


def render_long(story: Story, out: Path = RUN / "master.mp4"):
    frames = RUN / "frames"; segs = RUN / "segments"
    frames.mkdir(parents=True, exist_ok=True); segs.mkdir(parents=True, exist_ok=True)
    for s in story.scenes:
        frame = frames / f"scene_{s.id:02d}.png"; audio = RUN / "audio" / f"scene_{s.id:02d}.mp3"; seg = segs / f"scene_{s.id:02d}.mp4"
        if not audio.exists():
            raise FileNotFoundError(audio)
        _render_image(RUN / "scenes" / f"scene_{s.id:02d}.svg", frame, "1920:1080")
        _render_segment(frame, audio, float(s.duration), seg, "1920x1080", s.id)
    concat = RUN / "concat.txt"
    concat.write_text("".join(f"file '{(segs / f'scene_{s.id:02d}.mp4').resolve()}'\n" for s in story.scenes), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-video_track_timescale", "90000", str(out)])


def write_srt(story: Story, path: Path = RUN / "arabic.srt"):
    t = 0.0
    rows = []
    for s in story.scenes:
        end = t + float(s.duration)
        rows.append(f"{s.id}\n{_ts(t)} --> {_ts(end)}\n{_subtitle_text(s.narration)}\n")
        t = end
    path.write_text("\n".join(rows), encoding="utf-8")


def burn_subtitles(src: Path, srt: Path, out: Path):
    style = "FontName=Noto Sans Arabic,FontSize=24,Alignment=2,MarginV=76,Outline=2,Shadow=0,BorderStyle=3,Spacing=0,WrapStyle=2"
    _run([
        "ffmpeg", "-y", "-i", str(src), "-vf", f"subtitles={srt}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", str(out)
    ])
    marker = {
        "burned": True, "source": src.name, "output": out.name,
        "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "subtitle_file": str(srt), "subtitle_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
        "style": style,
    }
    (RUN / "subtitle_burn.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")


def render_shorts(story: Story, out_dir: Path = RUN / "shorts"):
    generate_vertical_visuals(story)
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = [(1, 2), (7, 8), (13, 14), (19, 20)]
    evidence = []
    for idx, scene_ids in enumerate(groups, 1):
        selected = [story.scenes[i - 1] for i in scene_ids]
        segs = RUN / f"short_segments_{idx}"
        segs.mkdir(exist_ok=True, parents=True)
        files = []
        for s in selected:
            frame = segs / f"s{s.id}.png"; seg = segs / f"s{s.id}.mp4"; audio = RUN / "audio" / f"scene_{s.id:02d}.mp3"
            _render_image(RUN / "vertical_scenes" / f"scene_{s.id:02d}.svg", frame, "1080:1920")
            _render_segment(frame, audio, float(s.duration), seg, "1080x1920", s.id)
            files.append(seg)
        cat = segs / "cat.txt"
        cat.write_text("".join(f"file '{p.resolve()}'\n" for p in files), encoding="utf-8")
        raw = segs / "raw.mp4"
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cat), "-c", "copy", "-video_track_timescale", "90000", str(raw)])
        srt = segs / "short.srt"; t = 0.0; rows = []
        for n, s in enumerate(selected, 1):
            end = t + float(s.duration)
            rows.append(f"{n}\n{_ts(t)} --> {_ts(end)}\n{_subtitle_text(s.narration, 32)}\n")
            t = end
        srt.write_text("\n".join(rows), encoding="utf-8")
        out = out_dir / f"short_{idx}.mp4"
        style = "FontName=Noto Sans Arabic,FontSize=21,Alignment=2,MarginV=92,Outline=2,Shadow=0,BorderStyle=3,Spacing=0,WrapStyle=2"
        vf = f"subtitles={srt}:force_style='{style}',scale=1080:1920:flags=lanczos"
        _run([
            "ffmpeg", "-y", "-i", str(raw), "-t", str(t), "-vf", vf,
            "-af", f"apad=pad_dur={t},atrim=duration={t},loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-b:a", "192k", str(out)
        ])
        evidence.append({
            "file": str(out), "burned": True, "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "output_size": out.stat().st_size, "duration": t, "srt": str(srt),
            "subtitle_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(), "cue_count": len(rows),
            "arabic_chars": sum(1 for ch in srt.read_text(encoding="utf-8") if "\u0600" <= ch <= "\u06ff"),
            "source_scene_ids": list(scene_ids), "subtitle_style": style,
        })
    (RUN / "short_subtitles_burn.json").write_text(json.dumps({"shorts": evidence}, ensure_ascii=False, indent=2), encoding="utf-8")
