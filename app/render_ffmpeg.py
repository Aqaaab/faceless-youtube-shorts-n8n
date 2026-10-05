from __future__ import annotations
import subprocess
from pathlib import Path
from .production_contract import FFMPEG_CRF, FFMPEG_PRESET, RENDER_FPS

def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def mux_motion(video: Path, audio: Path, duration: float, out: Path) -> None:
    run(["ffmpeg","-y","-i",str(video),"-i",str(audio),"-t",f"{float(duration):.6f}","-c:v","copy","-c:a","aac","-ar","48000","-b:a","192k","-af",f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={float(duration):.6f}","-movflags","+faststart",str(out)])

def concat(paths: list[Path], out: Path) -> None:
    manifest=out.with_suffix(".concat.txt")
    manifest.write_text("".join(f"file '{p.resolve()}'\n" for p in paths),encoding="utf-8")
    try:
        run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(manifest),"-c","copy","-movflags","+faststart",str(out)])
    finally:
        manifest.unlink(missing_ok=True)

def render_segment(frame: Path, audio: Path, duration: float, out: Path, size: str, scene_id: int) -> None:
    frames=max(30,int(round(duration*30)))
    phase=scene_id%6
    x_expr={0:"iw/2-(iw/zoom/2)",1:"iw/2-(iw/zoom/2)+20*sin(on/105)",2:"iw/2-(iw/zoom/2)-20*sin(on/105)",3:"iw/2-(iw/zoom/2)+14*sin(on/80)",4:"iw/2-(iw/zoom/2)-14*sin(on/80)",5:"iw/2-(iw/zoom/2)+10*sin(on/60)"}[phase]
    y_expr={0:"ih/2-(ih/zoom/2)",1:"ih/2-(ih/zoom/2)+10*sin(on/120)",2:"ih/2-(ih/zoom/2)-10*sin(on/120)",3:"ih/2-(ih/zoom/2)+8*sin(on/90)",4:"ih/2-(ih/zoom/2)-8*sin(on/90)",5:"ih/2-(ih/zoom/2)+6*sin(on/70)"}[phase]
    vf=f"zoompan=z='min(1.0+on/{frames}*0.065,1.065)':x='{x_expr}':y='{y_expr}':d={frames}:s={size}:fps={RENDER_FPS}"
    run(["ffmpeg","-y","-loop","1","-i",str(frame),"-i",str(audio),"-t",str(duration),"-vf",vf,"-af",f"apad=pad_dur={duration},atrim=duration={duration},loudnorm=I=-16:TP=-1.5:LRA=11","-c:v","libx264","-preset",FFMPEG_PRESET,"-pix_fmt","yuv420p","-c:a","aac","-ar","48000","-b:a","192k","-shortest","-video_track_timescale","90000",str(out)])
