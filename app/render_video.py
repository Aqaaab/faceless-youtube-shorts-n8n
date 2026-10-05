from __future__ import annotations
import os
from pathlib import Path
from .core import RUN, Story
from .render_ffmpeg import mux_motion, concat, render_segment
from .production_contract import LONG_SIZE

def render_long(story:Story,out:Path=RUN/"master.mp4"):
    frames=RUN/"frames"; segs=RUN/"segments"; frames.mkdir(parents=True,exist_ok=True); segs.mkdir(parents=True,exist_ok=True)
    motion_required=os.getenv("AUTOMOTIVE_RENDER_MOTION","0").strip().lower() in {"1","true","yes"}; segments=[]
    for s in story.scenes:
        audio=RUN/"audio"/f"scene_{s.id:02d}.mp3"; seg=segs/f"scene_{s.id:02d}.mp4"; motion=RUN/"scenes"/f"scene_{s.id:02d}.motion.mp4"; raster=RUN/"scenes"/f"scene_{s.id:02d}.png"
        if not audio.is_file(): raise FileNotFoundError(audio)
        if motion_required:
            if not motion.is_file(): raise RuntimeError(f"TRUE MOTION REQUIRED: missing Blender temporal clip {motion}")
            mux_motion(motion,audio,float(s.duration),seg)
        else:
            if not raster.is_file(): raise FileNotFoundError(raster)
            frame=frames/f"scene_{s.id:02d}.png"; frame.write_bytes(raster.read_bytes()); render_segment(frame,audio,float(s.duration),seg,f"{LONG_SIZE[0]}x{LONG_SIZE[1]}",s.id)
        segments.append(seg)
    concat(segments,out)
