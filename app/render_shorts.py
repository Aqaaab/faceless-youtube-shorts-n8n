from __future__ import annotations
import os,copy,hashlib,json
from pathlib import Path
from .core import RUN, Story
from .arabic_font import ensure_ready
from .short_selector import load_selected
from .vertical_visuals import generate_vertical_visuals
from .tts import load_word_timings
from .render_ffmpeg import mux_motion,concat,render_segment
from .render_subtitles import candidate_srt,subtitle_filter_path
from .production_contract import SHORT_SUBTITLE_FONT_SIZE

def render_shorts(story:Story,out_dir:Path=RUN/"shorts"):
    out_dir.mkdir(parents=True,exist_ok=True); candidates=load_selected()
    selected_scene_ids=sorted({sid for c in candidates for sid in c["scene_ids"]})
    vertical_story=copy.copy(story); vertical_story.scenes=[s for s in story.scenes if s.id in selected_scene_ids]; generate_vertical_visuals(vertical_story)
    motion_required=os.getenv("AUTOMOTIVE_RENDER_MOTION","0").strip().lower() in {"1","true","yes"}; evidence=[]
    for idx,candidate in enumerate(candidates,1):
        seg_dir=RUN/f"short_segments_{idx}"; seg_dir.mkdir(exist_ok=True,parents=True); segments=[]
        for sid in candidate["scene_ids"]:
            video=RUN/"vertical_scenes"/f"scene_{sid:02d}.motion.mp4"; audio=RUN/"audio"/f"scene_{sid:02d}.mp3"
            if not audio.is_file(): raise FileNotFoundError(audio)
            if motion_required:
                if not video.is_file(): raise RuntimeError(f"TRUE MOTION REQUIRED: missing portrait temporal clip {video}")
                segment=seg_dir/f"scene_{sid:02d}.mp4"; mux_motion(video,audio,float(next(s.duration for s in story.scenes if s.id==sid)),segment)
            else:
                frame=RUN/"vertical_scenes"/f"scene_{sid:02d}.png"
                if not frame.is_file(): raise FileNotFoundError(frame)
                segment=seg_dir/f"scene_{sid:02d}.mp4"; render_segment(frame,audio,float(next(s.duration for s in story.scenes if s.id==sid)) ,segment,"1080x1920",sid)
            segments.append(segment)
        raw=seg_dir/"raw.mp4"; concat(segments,raw); candidate_srt_path=seg_dir/"short.srt"; subtitle_info=candidate_srt(story,candidate,candidate_srt_path)
        out=out_dir/f"short_{idx}.mp4"; start_offset=float(candidate.get("start_offset",0.0)); duration=float(candidate["duration"]); gate=ensure_ready(RUN/"arabic_font_gate.json",strict=True); family=gate["family"]; fontsdir=Path(gate["font_file"]).parent.resolve()
        style=f"FontName={family},FontSize={SHORT_SUBTITLE_FONT_SIZE},Alignment=2,MarginV=92,Outline=2,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
        vf=f"subtitles={subtitle_filter_path(candidate_srt_path)}:fontsdir={subtitle_filter_path(fontsdir)}:force_style='{style}'"
        from .render_ffmpeg import run
        run(["ffmpeg","-y","-ss",f"{start_offset:.3f}","-i",str(raw),"-t",f"{duration:.3f}","-vf",vf,"-af","loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-b:a","192k","-movflags","+faststart",str(out)])
        evidence.append({"file":str(out),"burned":True,"output_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"output_size":out.stat().st_size,"duration":duration,"candidate_id":candidate["candidate_id"],"source_scene_ids":candidate["scene_ids"],"selection_score":candidate.get("score"),"subtitle_sha256":hashlib.sha256(candidate_srt_path.read_bytes()).hexdigest(),"cue_count":subtitle_info["cue_count"],"word_timed":subtitle_info["word_timed"],"font_family":family})
    (RUN/"short_subtitles_burn.json").write_text(json.dumps({"shorts":evidence},ensure_ascii=False,indent=2),encoding="utf-8")
