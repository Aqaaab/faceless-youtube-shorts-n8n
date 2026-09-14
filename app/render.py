from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
from .core import RUN,Story
from .vertical_visuals import generate_vertical_visuals

def _run(cmd): subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def _ts(x):
    ms=max(0,int(round(float(x)*1000))); sec,ms=divmod(ms,1000); h,rem=divmod(sec,3600); m,s=divmod(rem,60); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
def _wrap(text,width=30):
    words=str(text).strip().split(); lines=[]; cur=[]
    for w in words:
        if cur and len(' '.join(cur+[w]))>width: lines.append(' '.join(cur)); cur=[w]
        else: cur.append(w)
    if cur: lines.append(' '.join(cur))
    return '\n'.join(lines[:2])
def _chunks(text,words=10):
    ws=str(text).strip().split(); return [_wrap(' '.join(ws[i:i+words])) for i in range(0,len(ws),words) if ws[i:i+words]]
def _render_image(svg,png,size): _run(['ffmpeg','-y','-i',str(svg),'-frames:v','1','-vf',f'scale={size}:flags=lanczos',str(png)])
def _render_segment(frame,audio,duration,out,size,scene_id):
    frames=max(30,int(round(duration*30))); phase=scene_id%6
    x={0:'iw/2-(iw/zoom/2)',1:'iw/2-(iw/zoom/2)+20*sin(on/105)',2:'iw/2-(iw/zoom/2)-20*sin(on/105)',3:'iw/2-(iw/zoom/2)+14*sin(on/80)',4:'iw/2-(iw/zoom/2)-14*sin(on/80)',5:'iw/2-(iw/zoom/2)+10*sin(on/60)'}[phase]
    y={0:'ih/2-(ih/zoom/2)',1:'ih/2-(ih/zoom/2)+10*sin(on/120)',2:'ih/2-(ih/zoom/2)-10*sin(on/120)',3:'ih/2-(ih/zoom/2)+8*sin(on/90)',4:'ih/2-(ih/zoom/2)-8*sin(on/90)',5:'ih/2-(ih/zoom/2)+6*sin(on/70)'}[phase]
    vf=f"zoompan=z='min(1.0+on/{frames}*0.065,1.065)':x='{x}':y='{y}':d={frames}:s={size}:fps=30"
    _run(['ffmpeg','-y','-loop','1','-i',str(frame),'-i',str(audio),'-t',str(duration),'-vf',vf,'-af',f'apad=pad_dur={duration},atrim=duration={duration},loudnorm=I=-16:TP=-1.5:LRA=11','-c:v','libx264','-preset','medium','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-b:a','192k','-shortest','-video_track_timescale','90000',str(out)])
def render_long(story:Story,out:Path=RUN/'master.mp4'):
    frames=RUN/'frames'; segs=RUN/'segments'; frames.mkdir(parents=True,exist_ok=True); segs.mkdir(parents=True,exist_ok=True)
    for s in story.scenes:
        frame=frames/f'scene_{s.id:02d}.png'; audio=RUN/'audio'/f'scene_{s.id:02d}.mp3'; seg=segs/f'scene_{s.id:02d}.mp4'
        if not audio.exists(): raise FileNotFoundError(audio)
        _render_image(RUN/'scenes'/f'scene_{s.id:02d}.svg',frame,'1920:1080'); _render_segment(frame,audio,float(s.duration),seg,'1920x1080',s.id)
    cat=RUN/'concat.txt'; cat.write_text(''.join(f"file '{(segs/f'scene_{s.id:02d}.mp4').resolve()}'\n" for s in story.scenes),encoding='utf-8')
    _run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(cat),'-c','copy','-video_track_timescale','90000',str(out)])
def _srt_rows(scenes,short=False):
    rows=[]; t=0.; cue=1
    for s in scenes:
        end=t+float(s.duration); parts=_chunks(s.narration,9 if short else 10); span=(end-t)/max(1,len(parts)); start=t
        for part in parts:
            stop=min(end,start+span); rows.append(f'{cue}\n{_ts(start)} --> {_ts(stop)}\n{part}\n'); cue+=1; start=stop
        t=end
    return '\n'.join(rows),t
def write_srt(story:Story,path:Path=RUN/'arabic.srt'):
    text,_=_srt_rows(story.scenes); path.write_text(text,encoding='utf-8')
def _burn(src,srt,out,vertical=False):
    style=('FontName=Noto Sans Arabic,FontSize=20,Alignment=2,MarginV=62,Outline=2,Shadow=1,BorderStyle=1,Spacing=0,WrapStyle=2' if not vertical else 'FontName=Noto Sans Arabic,FontSize=18,Alignment=2,MarginV=150,Outline=2,Shadow=1,BorderStyle=1,Spacing=0,WrapStyle=2')
    _run(['ffmpeg','-y','-i',str(src),'-vf',f"subtitles={srt}:force_style='{style}'",'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','copy',str(out)]); return style
def burn_subtitles(src:Path,srt:Path,out:Path):
    style=_burn(src,srt,out,False); marker={'burned':True,'source':src.name,'output':out.name,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'subtitle_file':str(srt),'subtitle_sha256':hashlib.sha256(srt.read_bytes()).hexdigest(),'style':style,'opaque_box':False,'max_lines':2,'safe_zone':'bottom'}; (RUN/'subtitle_burn.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding='utf-8')
def render_shorts(story:Story,out_dir:Path=RUN/'shorts'):
    generate_vertical_visuals(story); out_dir.mkdir(parents=True,exist_ok=True); groups=((1,2),(7,8),(13,14),(19,20)); evidence=[]
    for idx,ids in enumerate(groups,1):
        selected=[story.scenes[i-1] for i in ids]; segs=RUN/f'short_segments_{idx}'; segs.mkdir(exist_ok=True,parents=True); files=[]
        for s in selected:
            frame=segs/f's{s.id}.png'; seg=segs/f's{s.id}.mp4'; audio=RUN/'audio'/f'scene_{s.id:02d}.mp3'; _render_image(RUN/'vertical_scenes'/f'scene_{s.id:02d}.svg',frame,'1080:1920'); _render_segment(frame,audio,float(s.duration),seg,'1080x1920',s.id); files.append(seg)
        cat=segs/'cat.txt'; cat.write_text(''.join(f"file '{p.resolve()}'\n" for p in files),encoding='utf-8'); raw=segs/'raw.mp4'; _run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(cat),'-c','copy','-video_track_timescale','90000',str(raw)])
        srt=segs/'short.srt'; text,duration=_srt_rows(selected,True); srt.write_text(text,encoding='utf-8'); out=out_dir/f'short_{idx}.mp4'; style=_burn(raw,srt,out,True)
        evidence.append({'file':str(out),'burned':True,'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'output_size':out.stat().st_size,'duration':duration,'srt':str(srt),'subtitle_sha256':hashlib.sha256(srt.read_bytes()).hexdigest(),'cue_count':len([x for x in text.splitlines() if x.strip().isdigit()]),'arabic_chars':sum(1 for ch in text if '\u0600'<=ch<='\u06ff'),'source_scene_ids':list(ids),'subtitle_style':style,'opaque_box':False,'max_lines':2,'safe_zone':'bottom'})
    (RUN/'short_subtitles_burn.json').write_text(json.dumps({'shorts':evidence},ensure_ascii=False,indent=2),encoding='utf-8')
