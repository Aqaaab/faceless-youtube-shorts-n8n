from __future__ import annotations
import json, os, shutil, subprocess, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=Path(os.getenv('RUN_DIR',str(ROOT/'data/run'))); RUN.mkdir(parents=True,exist_ok=True)
VOICE=os.getenv('VOICE','en-US-GuyNeural')

def shell(*cmd:str): subprocess.run(cmd,check=True)

def download(url:str,dst:Path):
    urllib.request.urlretrieve(url,dst)

def pexels(query:str)->str:
    key=os.getenv('PEXELS_API_KEY','').strip()
    if not key: raise RuntimeError('PEXELS_API_KEY is required for real rendering')
    q=urllib.parse.quote(query)
    req=urllib.request.Request(f'https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=landscape',headers={'Authorization':key})
    with urllib.request.urlopen(req,timeout=30) as r: data=json.loads(r.read().decode())
    for v in data.get('videos',[]):
        files=sorted(v.get('video_files',[]),key=lambda x:(x.get('width',0)*x.get('height',0)),reverse=True)
        for f in files:
            if f.get('link'): return f['link']
    raise RuntimeError(f'No Pexels video found for query: {query}')

def main():
    story=json.loads((RUN/'long_story.json').read_text())
    work=RUN/'render'; work.mkdir(exist_ok=True)
    segments=[]
    try:
        for i,sc in enumerate(story['scenes'],1):
            clip=work/f'{i:02d}.mp4'; audio=work/f'{i:02d}.mp3'; seg=work/f'{i:02d}-seg.mp4'
            download(pexels(sc['pexels_query']),clip)
            shell('edge-tts','--voice',VOICE,'--text',sc['text_en'],'--write-media',str(audio))
            shell('ffmpeg','-y','-stream_loop','-1','-i',str(clip),'-i',str(audio),'-shortest','-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-r','30',str(seg))
            segments.append(seg)
        concat=work/'concat.txt'; concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in segments))
        video=RUN/'video.mp4'; shell('ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(video))
        for idx,start in enumerate((1,7,13,19),1):
            ss=segments[start-1]; out=RUN/'shorts'/f'short-{idx}.mp4'; out.parent.mkdir(parents=True,exist_ok=True)
            shell('ffmpeg','-y','-i',str(ss),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2','-t','30','-c:v','libx264','-c:a','aac','-r','30',str(out))
    finally:
        shutil.rmtree(work,ignore_errors=True)
    print('REAL_RENDER=PASS')

if __name__=='__main__': main()
