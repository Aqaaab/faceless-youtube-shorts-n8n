import json
import subprocess
from pathlib import Path
from .core import RUN, Story
from .vertical_visuals import generate_vertical_visuals

def _run(c): subprocess.run(c, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def render_long(story: Story, out: Path = RUN/"master.mp4"):
    frames=RUN/"frames"; segs=RUN/"segments"; frames.mkdir(parents=True,exist_ok=True); segs.mkdir(parents=True,exist_ok=True)
    for s in story.scenes:
        frame=frames/f"scene_{s.id:02d}.png"; audio=RUN/"audio"/f"scene_{s.id:02d}.mp3"; seg=segs/f"scene_{s.id:02d}.mp4"
        _run(["ffmpeg","-y","-i",str(RUN/"scenes"/f"scene_{s.id:02d}.svg"),"-frames:v","1",str(frame)])
        _run(["ffmpeg","-y","-loop","1","-i",str(frame),"-i",str(audio),"-t",str(s.duration),"-vf","scale=1920:1080","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(seg)])
    concat=RUN/"concat.txt"; concat.write_text("".join(f"file '{(segs/f'scene_{s.id:02d}.mp4').resolve()}'\n" for s in story.scenes),encoding='utf-8')
    _run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(out)])

def write_srt(story: Story,path: Path=RUN/"arabic.srt"):
    def ts(x):
        ms=int(round((x-int(x))*1000)); sec=int(x); return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d},{ms:03d}"
    t=0; rows=[]
    for s in story.scenes:
        rows.append(f"{s.id}\n{ts(t)} --> {ts(t+s.duration)}\n{s.narration}\n"); t+=s.duration
    path.write_text('\n'.join(rows),encoding='utf-8')

def burn_subtitles(src,srt,out):
    _run(["ffmpeg","-y","-i",str(src),"-vf",f"subtitles={srt}:force_style='FontName=DejaVu Sans,FontSize=24,Alignment=2,MarginV=55'","-c:v","libx264","-crf","20","-pix_fmt","yuv420p","-c:a","copy",str(out)])
    (RUN/"subtitle_burn.json").write_text(json.dumps({"burned":True,"source":"master.mp4","output":str(out),"subtitle_file":str(srt)},ensure_ascii=False,indent=2),encoding='utf-8')

def render_shorts(story: Story,out_dir: Path=RUN/"shorts"):
    generate_vertical_visuals(story); out_dir.mkdir(parents=True,exist_ok=True)
    starts=[0,6,12,18]
    for idx,start in enumerate(starts,1):
        selected=story.scenes[start:start+2]
        segs=RUN/f"short_segments_{idx}"; segs.mkdir(exist_ok=True,parents=True); files=[]
        for s in selected:
            frame=segs/f"s{s.id}.png"; seg=segs/f"s{s.id}.mp4"; audio=RUN/"audio"/f"scene_{s.id:02d}.mp3"
            _run(["ffmpeg","-y","-i",str(RUN/"vertical_scenes"/f"scene_{s.id:02d}.svg"),"-frames:v","1",str(frame)])
            _run(["ffmpeg","-y","-loop","1","-i",str(frame),"-i",str(audio),"-t",str(s.duration),"-vf","scale=1080:1920","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(seg)])
            files.append(seg)
        cat=segs/"cat.txt"; cat.write_text(''.join(f"file '{p.resolve()}'\n" for p in files),encoding='utf-8'); raw=segs/"raw.mp4"
        _run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cat),"-c","copy",str(raw)])
        srt=segs/"short.srt"; t=0; rows=[]
        def ts(x):
            ms=int(round((x-int(x))*1000)); sec=int(x); return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d},{ms:03d}"
        for n,s in enumerate(selected,1): rows.append(f"{n}\n{ts(t)} --> {ts(t+s.duration)}\n{s.narration}\n"); t+=s.duration
        srt.write_text('\n'.join(rows),encoding='utf-8')
        out=out_dir/f"short_{idx}.mp4"
        vf=f"tpad=stop_mode=clone:stop_duration={max(0,45-t)},scale=1080:1920"
        _run(["ffmpeg","-y","-i",str(raw),"-t","45","-vf",f"subtitles={srt}:force_style='FontName=DejaVu Sans,FontSize=22,Alignment=2,MarginV=85',{vf}","-af","apad","-t","45","-c:v","libx264","-crf","20","-pix_fmt","yuv420p","-c:a","aac",str(out)])
