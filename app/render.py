from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .core import RUN, Story
from .vertical_visuals import generate_vertical_visuals


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _ts(seconds: float) -> str:
    ms = max(0, int(round(float(seconds) * 1000))); sec, ms = divmod(ms, 1000); h, rem = divmod(sec, 3600); m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _caption_chunks(text: str, max_words: int = 11, max_chars: int = 48) -> list[str]:
    words = re.findall(r"\S+", str(text).strip()); chunks=[]; current=[]; chars=0
    for word in words:
        if len(word) > max_chars:
            if current: chunks.append(" ".join(current)); current=[]; chars=0
            for i in range(0, len(word), max_chars): chunks.append(word[i:i+max_chars])
            continue
        extra = len(word) + (1 if current else 0)
        if current and (len(current) >= max_words or chars + extra > max_chars):
            chunks.append(" ".join(current)); current=[word]; chars=len(word)
        else:
            current.append(word); chars += extra
    if current: chunks.append(" ".join(current))
    return chunks or [str(text).strip()]


def _wrap_caption(text: str, max_line: int = 26) -> str:
    words = str(text).split(); left=[]; right=[]; count=0
    for word in words:
        if count + len(word) + (1 if left else 0) <= max_line:
            left.append(word); count += len(word) + (1 if left[:-1] else 0)
        else: right.append(word)
    if not right:
        return " ".join(left)
    line2 = " ".join(right)
    if len(line2) > max_line:
        while len(line2) > max_line and left:
            right.insert(0, left.pop()); line2 = " ".join(right)
    return " ".join(left) + "\\n" + " ".join(right)


def _caption_style(vertical: bool) -> str:
    size = 31 if vertical else 28; margin = 235 if vertical else 56
    return f"FontName=Noto Sans Arabic,FontSize={size},Alignment=2,MarginV={margin},Outline=3,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2,PrimaryColour=&H00FFFFFF,OutlineColour=&H00151A20"


def _render_image(svg: Path, png: Path, size: str) -> None:
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(svg), "-frames:v", "1", "-vf", f"scale={size}:flags=lanczos", str(png)])


def _render_segment(frame: Path, audio: Path, duration: float, out: Path, size: str, scene_id: int) -> None:
    frames=max(30,int(round(duration*30))); phase=scene_id%7
    x={0:"iw/2-(iw/zoom/2)",1:"iw/2-(iw/zoom/2)+22*sin(on/95)",2:"iw/2-(iw/zoom/2)-22*sin(on/95)",3:"iw/2-(iw/zoom/2)+16*sin(on/70)",4:"iw/2-(iw/zoom/2)-16*sin(on/70)",5:"iw/2-(iw/zoom/2)+12*sin(on/55)",6:"iw/2-(iw/zoom/2)"}[phase]
    y={0:"ih/2-(ih/zoom/2)",1:"ih/2-(ih/zoom/2)+12*sin(on/110)",2:"ih/2-(ih/zoom/2)-12*sin(on/110)",3:"ih/2-(ih/zoom/2)+9*sin(on/80)",4:"ih/2-(ih/zoom/2)-9*sin(on/80)",5:"ih/2-(ih/zoom/2)+7*sin(on/65)",6:"ih/2-(ih/zoom/2)-7*sin(on/65)"}[phase]
    zoom = f"zoompan=z='min(1.0+on/{frames}*0.085,1.085)':x='{x}':y='{y}':d={frames}:s={size}:fps=30"
    _run(["ffmpeg","-y","-loglevel","error","-loop","1","-i",str(frame),"-i",str(audio),"-t",str(duration),"-vf",zoom,"-af",f"apad=pad_dur={duration},atrim=duration={duration},loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset","medium","-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-b:a","192k","-shortest","-video_track_timescale","90000",str(out)])


def render_long(story: Story, out: Path = RUN / "master.mp4") -> None:
    frames=RUN/"frames"; segs=RUN/"segments"; frames.mkdir(parents=True,exist_ok=True); segs.mkdir(parents=True,exist_ok=True)
    for s in story.scenes:
        frame=frames/f"scene_{s.id:02d}.png"; audio=RUN/"audio"/f"scene_{s.id:02d}.mp3"; seg=segs/f"scene_{s.id:02d}.mp4"
        if not audio.exists(): raise FileNotFoundError(audio)
        _render_image(RUN/"scenes"/f"scene_{s.id:02d}.svg",frame,"1920:1080"); _render_segment(frame,audio,float(s.duration),seg,"1920x1080",s.id)
    concat=RUN/"concat.txt"; concat.write_text("".join(f"file '{(segs/f'scene_{s.id:02d}.mp4').resolve()}'\n" for s in story.scenes),encoding="utf-8")
    _run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(concat),"-c","copy","-video_track_timescale","90000",str(out)])


def _write_cues(story: Story, path: Path, short: bool = False, scenes=None) -> None:
    selected=list(scenes if scenes is not None else story.scenes); rows=[]; t=0.0; max_words=8 if short else 10; max_chars=44 if short else 52; line=24 if short else 30
    for cue_id, scene in enumerate(selected,1):
        duration=float(scene.duration); chunks=_caption_chunks(scene.narration,max_words,max_chars); weights=[max(1,len(c)) for c in chunks]; total=sum(weights); cursor=t
        for n,chunk in enumerate(chunks):
            cue_dur = duration*weights[n]/total; end = t+duration if n==len(chunks)-1 else cursor+cue_dur
            rows.append(f"{cue_id+n if False else len(rows)+1}\n{_ts(cursor)} --> {_ts(end)}\n{_wrap_caption(chunk,line)}\n"); cursor=end
        t += duration
    path.write_text("\n".join(rows),encoding="utf-8")


def write_srt(story: Story, path: Path = RUN/"arabic.srt") -> None:
    _write_cues(story,path,False)


def burn_subtitles(src: Path, srt: Path, out: Path) -> None:
    style=_caption_style(False); _run(["ffmpeg","-y","-loglevel","error","-i",str(src),"-vf",f"subtitles={srt}:force_style='{style}'","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","copy",str(out)])
    marker={"burned":True,"source":src.name,"output":out.name,"source_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"subtitle_file":str(srt),"subtitle_sha256":hashlib.sha256(srt.read_bytes()).hexdigest(),"style":style}
    (RUN/"subtitle_burn.json").write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding="utf-8")


def render_shorts(story: Story, out_dir: Path = RUN/"shorts") -> None:
    generate_vertical_visuals(story); out_dir.mkdir(parents=True,exist_ok=True); groups=((1,2),(7,8),(13,14),(19,20)); evidence=[]
    for index,scene_ids in enumerate(groups,1):
        selected=[story.scenes[i-1] for i in scene_ids]; segs=RUN/f"short_segments_{index}"; segs.mkdir(parents=True,exist_ok=True); files=[]
        for s in selected:
            frame=segs/f"s{s.id}.png"; seg=segs/f"s{s.id}.mp4"; audio=RUN/"audio"/f"scene_{s.id:02d}.mp3"
            _render_image(RUN/"vertical_scenes"/f"scene_{s.id:02d}.svg",frame,"1080:1920"); _render_segment(frame,audio,float(s.duration),seg,"1080x1920",s.id); files.append(seg)
        cat=segs/"cat.txt"; cat.write_text("".join(f"file '{p.resolve()}'\n" for p in files),encoding="utf-8"); raw=segs/"raw.mp4"
        _run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(cat),"-c","copy","-video_track_timescale","90000",str(raw)])
        srt=segs/"short.srt"; _write_cues(story,srt,True,selected)
        out=out_dir/f"short_{index}.mp4"; style=_caption_style(True); duration=sum(float(s.duration) for s in selected)
        _run(["ffmpeg","-y","-loglevel","error","-i",str(raw),"-t",str(duration),"-vf",f"subtitles={srt}:force_style='{style}'","-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-b:a","192k",str(out)])
        evidence.append({"file":str(out),"burned":True,"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"output_size":out.stat().st_size,"duration":duration,"srt":str(srt),"subtitle_sha256":hashlib.sha256(srt.read_bytes()).hexdigest(),"cue_count":len(re.findall(r'^\\d+$',srt.read_text(encoding='utf-8'),re.M)),"arabic_chars":sum(1 for ch in srt.read_text(encoding='utf-8') if '\u0600'<=ch<='\u06ff'),"source_scene_ids":list(scene_ids),"subtitle_style":style})
    (RUN/"short_subtitles_burn.json").write_text(json.dumps({"shorts":evidence},ensure_ascii=False,indent=2),encoding="utf-8")
