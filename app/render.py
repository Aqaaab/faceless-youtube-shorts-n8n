from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .arabic_font import ensure_ready
from .core import RUN, Story
from .tts import load_word_timings
from .production_contract import LANDSCAPE_DELIVERY, PORTRAIT_DELIVERY
from .vertical_visuals import generate_vertical_visuals
from .short_selector import load_selected


def _run(cmd):
    subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


def _ts(x:float)->str:
    total=max(0,int(round(float(x)*1000))); sec,ms=divmod(total,1000); h,rem=divmod(sec,3600); m,s=divmod(rem,60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _subtitle_text(value:str,max_chars:int=42)->str:
    words=str(value).strip().split(); lines=[]; current=[]
    for word in words:
        if len(word)>max_chars:
            if current: lines.append(" ".join(current)); current=[]
            lines.extend(word[i:i+max_chars] for i in range(0,len(word),max_chars)); continue
        candidate=" ".join(current+[word])
        if current and len(candidate)>max_chars: lines.append(" ".join(current)); current=[word]
        else: current.append(word)
    if current: lines.append(" ".join(current))
    return "\n".join(lines)


def _font_filter(srt:Path,size:int,margin:int)->str:
    gate=ensure_ready(RUN/"arabic_font_gate.json",strict=True); family=gate["family"]; fontsdir=Path(gate["font_file"]).parent.resolve()
    path=str(srt.resolve()).replace("\\","/").replace(":","\\:"); fd=str(fontsdir).replace("\\","/").replace(":","\\:")
    style=f"FontName={family},FontSize={size},Alignment=2,MarginV={margin},Outline=2,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
    return f"subtitles={path}:fontsdir={fd}:force_style='{style}'"


def _callout_srt(scene, path:Path):
    rows=[]
    callouts=[str(x).strip() for x in scene.callouts if str(x).strip()]
    if callouts:
        text="  •  ".join(callouts[:3])
        rows.append(f"1\n{_ts(0)} --> {_ts(float(scene.duration))}\n{_subtitle_text(text,36)}\n")
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(rows),encoding="utf-8")
    return bool(rows)


def _mux_scene(video:Path,audio:Path,scene,output:Path,size:tuple[int,int]):
    callout=RUN/"callouts"/f"scene_{scene.id:02d}.srt"; has_callout=_callout_srt(scene,callout)
    filters=[f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease:flags=lanczos",f"pad={size[0]}:{size[1]}:(ow-iw)/2:(oh-ih)/2", "setsar=1"]
    if has_callout: filters.append(_font_filter(callout,22 if size[1]>size[0] else 24,120 if size[1]>size[0] else 78))
    output.parent.mkdir(parents=True,exist_ok=True)
    _run(["ffmpeg","-y","-i",str(video),"-i",str(audio),"-t",f"{float(scene.duration):.3f}","-vf",",".join(filters),"-af","loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur="+f"{float(scene.duration):.3f}","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30","-c:a","aac","-ar","48000","-b:a","192k","-shortest","-movflags","+faststart",str(output)])


def _concat(paths:list[Path],out:Path):
    manifest=out.with_suffix(".concat.txt"); manifest.write_text("".join(f"file '{p.resolve()}'\n" for p in paths),encoding="utf-8")
    try: _run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(out)])
    finally: manifest.unlink(missing_ok=True)


def render_long(story:Story,out:Path=RUN/"master.mp4"):
    seg_dir=RUN/"segments"; seg_dir.mkdir(parents=True,exist_ok=True); segments=[]
    for scene in story.scenes:
        video=RUN/"scenes"/f"scene_{scene.id:02d}.mp4"; audio=RUN/"audio"/f"scene_{scene.id:02d}.mp3"; seg=seg_dir/f"scene_{scene.id:02d}.mp4"
        if not video.is_file(): raise RuntimeError(f"WanGP scene video missing: {video}")
        if not audio.is_file(): raise FileNotFoundError(audio)
        _mux_scene(video,audio,scene,seg,LANDSCAPE_DELIVERY); segments.append(seg)
    _concat(segments,out)


def _write_word_srt(rows_source,path:Path,max_words:int=4):
    rows=[]; buffer=[]; seq=1
    for start,end,word in rows_source:
        if end<=start: continue
        buffer.append((start,end,word))
        if len(buffer)>=max_words or re.search(r"[.!؟،]$",word):
            rows.append(f"{seq}\n{_ts(buffer[0][0])} --> {_ts(buffer[-1][1])}\n"+" ".join(x[2] for x in buffer)+"\n"); seq+=1; buffer=[]
    if buffer: rows.append(f"{seq}\n{_ts(buffer[0][0])} --> {_ts(buffer[-1][1])}\n"+" ".join(x[2] for x in buffer)+"\n")
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(rows),encoding="utf-8"); return {"cue_count":len(rows),"word_timed":bool(rows)}


def write_srt(story:Story,path:Path=RUN/"arabic.srt"):
    rows=[]; clock=0.0
    for scene in story.scenes:
        for word in load_word_timings(scene.id): rows.append((clock+float(word["start"]),clock+float(word["end"]),str(word.get("text", ""))))
        clock+=float(scene.duration)
    result=_write_word_srt(rows,path,4)
    if not result["word_timed"]: raise RuntimeError("SUBTITLE TIMING FAILED: no word-level cues")
    return result


def burn_subtitles(src:Path,srt:Path,out:Path):
    filter_expr=_font_filter(srt,24,76)
    _run(["ffmpeg","-y","-i",str(src),"-vf",filter_expr,"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",str(out)])
    marker={"burned":True,"source":src.name,"output":out.name,"source_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"subtitle_sha256":hashlib.sha256(srt.read_bytes()).hexdigest()}
    (RUN/"subtitle_burn.json").write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding="utf-8")


def _candidate_srt(story,candidate,path:Path):
    rows=[]; local=0.0; start_offset=float(candidate.get("start_offset",0.0)); duration=float(candidate["duration"])
    for sid in candidate["scene_ids"]:
        scene=next(s for s in story.scenes if s.id==sid)
        for word in load_word_timings(sid):
            start=local+float(word["start"])-start_offset; end=local+float(word["end"])-start_offset
            if end>0 and start<duration: rows.append((max(0,start),min(duration,end),str(word.get("text",""))))
        local+=float(scene.duration)
    return _write_word_srt(rows,path,3)


def render_shorts(story:Story,out_dir:Path=RUN/"shorts"):
    candidates=load_selected(); selected_ids=sorted({int(sid) for item in candidates for sid in item["scene_ids"]})
    generate_vertical_visuals(story,RUN/"vertical_scenes",selected_ids); out_dir.mkdir(parents=True,exist_ok=True); evidence=[]
    scene_map={s.id:s for s in story.scenes}
    for idx,candidate in enumerate(candidates,1):
        raw_dir=RUN/f"short_segments_{idx}"; raw_dir.mkdir(parents=True,exist_ok=True); segments=[]
        for sid in candidate["scene_ids"]:
            scene=scene_map[int(sid)]; video=RUN/"vertical_scenes"/f"scene_{scene.id:02d}.mp4"; audio=RUN/"audio"/f"scene_{scene.id:02d}.mp3"; seg=raw_dir/f"scene_{scene.id:02d}.mp4"
            if not video.is_file(): raise RuntimeError(f"WanGP portrait scene video missing: {video}")
            _mux_scene(video,audio,scene,seg,PORTRAIT_DELIVERY); segments.append(seg)
        raw=raw_dir/"raw.mp4"; _concat(segments,raw); srt=raw_dir/"short.srt"; sub=_candidate_srt(story,candidate,srt); out=out_dir/f"short_{idx}.mp4"; start=float(candidate.get("start_offset",0.0)); duration=float(candidate["duration"])
        _run(["ffmpeg","-y","-ss",f"{start:.3f}","-i",str(raw),"-t",f"{duration:.3f}","-vf",_font_filter(srt,21,92),"-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r","30","-c:a","aac","-ar","48000","-b:a","192k","-movflags","+faststart",str(out)])
        evidence.append({"file":str(out),"burned":True,"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"output_size":out.stat().st_size,"duration":duration,"candidate_id":candidate["candidate_id"],"source_scene_ids":[int(x) for x in candidate["scene_ids"]],"subtitle_sha256":hashlib.sha256(srt.read_bytes()).hexdigest(),"cue_count":sub["cue_count"],"word_timed":sub["word_timed"]})
    (RUN/"short_subtitles_burn.json").write_text(json.dumps({"shorts":evidence},ensure_ascii=False,indent=2),encoding="utf-8")
