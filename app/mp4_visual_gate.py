from __future__ import annotations
import json, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from .production_contract import LANDSCAPE_DELIVERY, PORTRAIT_DELIVERY, SHORT_MIN_SECONDS, SHORT_MAX_SECONDS

def _run(cmd): return subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def _probe(path): return json.loads(_run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]).stdout)
def _sample_frames(path,count=5):
    with tempfile.TemporaryDirectory(prefix="mp4gate-") as td:
        pattern=str(Path(td)/"frame-%02d.png")
        _run(["ffmpeg","-v","error","-y","-i",str(path),"-vf","fps=1/2,scale=320:-1:flags=lanczos","-frames:v",str(count),pattern])
        return [Image.open(p).convert("RGB").copy() for p in sorted(Path(td).glob("frame-*.png"))]
def _check(path,target,min_duration,max_duration):
    errors=[]
    if not path.is_file() or path.stat().st_size==0: return {"passed":False,"errors":["missing file"]}
    data=_probe(path); streams=data.get("streams",[]); video=next((s for s in streams if s.get("codec_type")=="video"),None); audio=next((s for s in streams if s.get("codec_type")=="audio"),None)
    if video is None: errors.append("video stream missing")
    else:
        w,h=int(video.get("width",0)),int(video.get("height",0))
        if (w,h)!=target: errors.append(f"resolution {w}x{h} != {target[0]}x{target[1]}")
        if video.get("codec_name")!="h264": errors.append("video codec must be h264")
        try: a,b=str(video.get("avg_frame_rate","0/1")).split("/"); fps=float(a)/float(b)
        except (ValueError,ZeroDivisionError): fps=0
        if fps<12: errors.append(f"fps {fps:.2f} < 12")
    if audio is None or audio.get("codec_name")!="aac": errors.append("aac audio stream missing")
    duration=float(data.get("format",{}).get("duration",0) or 0)
    if not min_duration<=duration<=max_duration: errors.append(f"duration {duration:.2f}s outside requested range")
    frames=_sample_frames(path); motion=0.0
    if len(frames)>=2:
        diffs=[ImageStat.Stat(ImageChops.difference(a,b)).mean[0]/255.0 for a,b in zip(frames,frames[1:])]
        motion=sum(diffs)/len(diffs)
        if motion<0.0015: errors.append(f"motion signal {motion:.5f} is too low")
    return {"passed":not errors,"errors":errors,"duration":duration,"resolution":[int(video.get("width",0)) if video else 0,int(video.get("height",0)) if video else 0],"motion_signal":round(motion,5)}
def run_mp4_visual_product_gate(master,shorts,out):
    errors=[]; master_result=_check(master,LANDSCAPE_DELIVERY,420,900); errors += ["master: "+e for e in master_result["errors"]]; short_results=[]
    for i,path in enumerate(shorts,1):
        r=_check(path,PORTRAIT_DELIVERY,SHORT_MIN_SECONDS,SHORT_MAX_SECONDS); short_results.append(r); errors += [f"short {i}: "+e for e in r["errors"]]
    result={"passed":not errors,"errors":errors,"gate_version":"mp4-wangp-v1","master":master_result,"shorts":short_results}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors: raise RuntimeError("MP4 WAN-GP VISUAL GATE FAILED: "+"; ".join(errors))
    return result
