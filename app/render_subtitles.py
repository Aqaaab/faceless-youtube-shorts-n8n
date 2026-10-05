from __future__ import annotations
import hashlib,re
from pathlib import Path
from .core import RUN, Story
from .arabic_font import ensure_ready
from .production_contract import SUBTITLE_FONT_SIZE, SHORT_SUBTITLE_FONT_SIZE, FFMPEG_CRF, FFMPEG_PRESET
from .render_ffmpeg import run
from .tts import load_word_timings

def ts(x: float) -> str:
    total_ms=max(0,int(round(float(x)*1000))); sec,ms=divmod(total_ms,1000); h,rem=divmod(sec,3600); m,s=divmod(rem,60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def subtitle_text(text: str,max_chars:int=42)->str:
    words=str(text).strip().split(); lines=[]; current=[]
    for word in words:
        if len(word)>max_chars:
            if current: lines.append(" ".join(current)); current=[]
            for start in range(0,len(word),max_chars): lines.append(word[start:start+max_chars])
            continue
        candidate=" ".join(current+[word])
        if current and len(candidate)>max_chars: lines.append(" ".join(current)); current=[word]
        else: current.append(word)
    if current: lines.append(" ".join(current))
    return "\n".join(lines)

def _write_word_srt(rows_source,path:Path,max_words:int=4)->dict:
    rows=[]; buffer=[]; sequence=1
    for start,end,word in rows_source:
        if end<=start: continue
        buffer.append((start,end,word))
        if len(buffer)>=max_words or re.search(r"[.!؟،]$",word):
            rows.append(f"{sequence}\n{ts(buffer[0][0])} --> {ts(buffer[-1][1])}\n"+" ".join(x[2] for x in buffer)+"\n"); sequence+=1; buffer=[]
    if buffer: rows.append(f"{sequence}\n{ts(buffer[0][0])} --> {ts(buffer[-1][1])}\n"+" ".join(x[2] for x in buffer)+"\n")
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text("\n".join(rows),encoding="utf-8")
    return {"cue_count":len(rows),"word_timed":bool(rows)}

def write_srt(story:Story,path:Path=RUN/"arabic.srt"):
    rows=[]; clock=0.0
    for scene in story.scenes:
        for word in load_word_timings(scene.id): rows.append((clock+float(word["start"]),clock+float(word["end"]),str(word.get("text",""))))
        clock+=float(scene.duration)
    report=_write_word_srt(rows,path,max_words=4)
    if not report["word_timed"]: raise RuntimeError("SUBTITLE TIMING FAILED: no word-level subtitle cues were produced")
    return report

def subtitle_filter_path(path:Path)->str:
    return str(path.resolve()).replace("\\","/").replace(":","\\:")

def burn_subtitles(src:Path,srt:Path,out:Path):
    gate=ensure_ready(RUN/"arabic_font_gate.json",strict=True); family=gate["family"]; fontsdir=Path(gate["font_file"]).parent.resolve()
    style=f"FontName={family},FontSize={SUBTITLE_FONT_SIZE},Alignment=2,MarginV=76,Outline=2,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
    filt=f"subtitles={subtitle_filter_path(srt)}:fontsdir={subtitle_filter_path(fontsdir)}:force_style='{style}'"
    run(["ffmpeg","-y","-i",str(src),"-vf",filt,"-c:v","libx264","-preset",FFMPEG_PRESET,"-crf",str(FFMPEG_CRF),"-pix_fmt","yuv420p","-c:a","copy",str(out)])
    marker={"burned":True,"source":src.name,"output":out.name,"font_family":family,"font_file":gate["font_file"],"font_gate_pass":True,"source_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"subtitle_file":str(srt),"subtitle_sha256":hashlib.sha256(srt.read_bytes()).hexdigest(),"style":style}
    (RUN/"subtitle_burn.json").write_text(__import__("json").dumps(marker,ensure_ascii=False,indent=2),encoding="utf-8")

def candidate_srt(story:Story,candidate:dict,path:Path)->dict:
    rows=[]; local_clock=0.0
    for sid in candidate["scene_ids"]:
        scene=next(s for s in story.scenes if s.id==sid); offset=float(candidate.get("start_offset",0.0)) if sid==candidate["start_scene"] else 0.0
        for word in load_word_timings(sid):
            start=local_clock+float(word["start"])-float(candidate.get("start_offset",0.0)); end=local_clock+float(word["end"])-float(candidate.get("start_offset",0.0))
            if end<=0 or start>=float(candidate["duration"]): continue
            rows.append((max(0.0,start),min(float(candidate["duration"]),end),str(word.get("text",""))))
        local_clock+=float(scene.duration)
    return _write_word_srt(rows,path,max_words=3)

def short_subtitle_style()->tuple[str,Path]:
    gate=ensure_ready(RUN/"arabic_font_gate.json",strict=True)
    return gate["family"],Path(gate["font_file"]).parent.resolve()
