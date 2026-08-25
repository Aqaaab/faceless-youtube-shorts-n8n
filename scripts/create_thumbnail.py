#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))
video=RUN_DIR/'video.mp4'; out=RUN_DIR/'thumbnail.jpg'; job=json.loads((RUN_DIR/'job.json').read_text(encoding='utf-8'))
if not video.is_file() or video.stat().st_size==0: raise SystemExit(f'Missing rendered video: {video}')
title=str(job.get('title','')).strip(); topic=str(job.get('topic','Science')).strip()
# Short explanatory overlay: remove platform suffix and keep the strongest phrase.
text=re.sub(r'\s*#Shorts\s*$','',title,flags=re.I).strip()
text=re.sub(r'\s*[—–-]\s*What You Need To Know\s*$','',text,flags=re.I).strip()
if len(text)>42: text=text[:42].rsplit(' ',1)[0]
if not text: text=topic[:42]
# Escape FFmpeg drawtext characters.
def esc(s): return s.replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace('%','\\%').replace('[','\\[').replace(']','\\]')
font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
if not Path(font).is_file(): font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
# Use a clean 16:9 frame with a readable explanatory text block; no fabricated imagery.
subprocess.run(['ffmpeg','-y','-ss','2','-i',str(video),'-frames:v','1','-vf',f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,drawbox=x=35:y=35:w=1210:h=190:color=black@0.62:t=fill,drawtext=fontfile={font}:text='{esc(text)}':fontcolor=white:fontsize=58:line_spacing=8:x=(w-text_w)/2:y=75:box=0",'-q:v','2',str(out)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
if not out.is_file() or out.stat().st_size<1000: raise SystemExit('Thumbnail generation failed')
print(f'THUMBNAIL={out}')
print(f'THUMBNAIL_TEXT={text}')
