from __future__ import annotations

import html
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

from .core import RUN, Story

FAMILIES={"front_3q","rear_3q","side_profile","low_angle","wide_scene","front_close","rear_close","three_quarter_high","design_detail","technology","performance","safety","battery","charging","interior","wheel_detail","aero","comparison"}
MOTIONS={"push_in","pull_out","orbit_left","orbit_right","rack_focus","tracking","rise"}
DEBUG_MARKERS=("MODE_FACT_SOURCE_REQUIRED","hud_only","STORY CALLOUT","VISUAL INTENT","WHY IT MATTERS")
SHORT_SIZE=(1080,1920)


def _run(cmd): return subprocess.run(cmd,check=True,capture_output=True,text=True)
def _sample(video:Path,seconds:float,out:Path): _run(["ffmpeg","-y","-loglevel","error","-ss",str(max(0.0,seconds)),"-i",str(video),"-frames:v","1",str(out)])
def _probe_size(path:Path):
    out=_run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x",str(path)]).stdout.strip();w,h=out.split("x",1);return int(w),int(h)
def _duration(path:Path)->float:return float(_run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(path)]).stdout.strip())
def _metric(path:Path)->dict:
    with Image.open(path).convert("RGB") as image:
        small=image.resize((96,54));stat=ImageStat.Stat(small);edge=small.filter(ImageFilter.FIND_EDGES);px=list(small.getdata());corner=px[0]
        non_bg=sum(1 for p in px if sum(abs(p[i]-corner[i]) for i in range(3))>24)/len(px)
        return {"width":image.width,"height":image.height,"mean_luma":round(sum(stat.mean)/3,2),"variance":round(sum(stat.var)/3,2),"edge_mean":round(sum(ImageStat.Stat(edge).mean)/3,2),"non_background_ratio":round(non_bg,4),"pixel_hash":hashlib.sha256(image.resize((32,32)).tobytes()).hexdigest()}


def _subtitle_roi(video:Path,seconds:float,vertical:bool)->dict:
    with tempfile.TemporaryDirectory(prefix="subtitle-vqa-") as td:
        frame=Path(td)/"frame.png";_sample(video,seconds,frame)
        with Image.open(frame).convert("RGB") as image:
            w,h=image.size; y0=int(h*(0.78 if vertical else 0.83)); y1=int(h*(0.96 if vertical else 0.97)); roi=image.crop((int(w*.06),y0,int(w*.94),y1)).resize((300,120))
            px=list(roi.getdata()); bright=[(r>195 and g>195 and b>195) for r,g,b in px]; ratio=sum(bright)/len(bright)
            xs=[];ys=[]
            for idx,flag in enumerate(bright):
                if flag: xs.append(idx%roi.width);ys.append(idx//roi.width)
            bbox=[min(xs),min(ys),max(xs)+1,max(ys)+1] if xs else None
            touches=bool(bbox and (bbox[0]<=4 or bbox[2]>=roi.width-4 or bbox[1]<=2 or bbox[3]>=roi.height-2))
            area=((bbox[2]-bbox[0])*(bbox[3]-bbox[1])/(roi.width*roi.height)) if bbox else 0.0
            return {"bbox":bbox,"bright_ratio":round(ratio,4),"touches_edge":touches,"area_ratio":round(area,4)}


def _srt_metrics(path:Path,min_cues:int,max_line:int)->tuple[bool,str,dict]:
    if not path.is_file() or path.stat().st_size<30:return False,"subtitle file missing/empty",{}
    text=path.read_text(encoding="utf-8")
    if "\ufffd" in text:return False,"replacement glyph U+FFFD present in subtitles",{}
    if any(marker in text for marker in DEBUG_MARKERS):return False,"debug/internal text present in subtitles",{}
    blocks=[b.strip() for b in re.split(r"\n\s*\n",text) if b.strip()];valid=0;max_seen=0
    for block in blocks:
        lines=block.splitlines()
        if len(lines)<3 or not re.fullmatch(r"\d+",lines[0]) or not re.match(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$",lines[1]):return False,"invalid SRT block",{}
        for line in lines[2:]:
            max_seen=max(max_seen,len(line))
            if len(line)>max_line:return False,f"subtitle line exceeds {max_line} characters",{"max_line":max_seen}
        valid+=1
    arabic=sum(1 for ch in text if '\u0600'<=ch<='\u06ff')
    if valid<min_cues:return False,f"too few subtitle cues: {valid}<{min_cues}",{}
    if arabic<20:return False,"insufficient Arabic subtitle text",{}
    return True,"ok",{"cue_count":valid,"arabic_chars":arabic,"max_line":max_seen}


def run_visual_product_gate(story:Story,master:Path,shorts:list[Path],report:Path=RUN/"visual_product_gate_v4.json")->dict:
    errors=[];families=[];cameras=[];modes=[];motions=[];scene_hashes=set();intents=set();family_counts={};scenes=[];car_first=0
    if len(story.scenes)!=25:errors.append(f"story scene count {len(story.scenes)}/25")
    for scene in story.scenes:
        svg_path=RUN/"scenes"/f"scene_{scene.id:02d}.svg";png_path=RUN/"frames"/f"scene_{scene.id:02d}.png"
        if not svg_path.is_file() or not png_path.is_file():errors.append(f"scene {scene.id}: missing visual evidence");continue
        svg=svg_path.read_text(encoding="utf-8")
        if any(marker in svg for marker in DEBUG_MARKERS):errors.append(f"scene {scene.id}: forbidden debug marker")
        def attr(name):
            m=re.search(rf'data-{name}="([^"]*)"',svg);return html.unescape(m.group(1)).strip() if m else ""
        family=attr("visual-family");camera=attr("camera-angle");mode=attr("visual-mode");motion=attr("motion");intent=attr("visual-intent")
        if family not in FAMILIES:errors.append(f"scene {scene.id}: invalid visual family {family!r}")
        if not camera:errors.append(f"scene {scene.id}: missing camera")
        if not mode:errors.append(f"scene {scene.id}: missing visual mode")
        if motion not in MOTIONS:errors.append(f"scene {scene.id}: invalid motion {motion!r}")
        expected=scene.visual_intent.strip()[:240]
        if intent!=expected:errors.append(f"scene {scene.id}: visual intent evidence mismatch")
        if 'data-car-layer="primary"' not in svg:errors.append(f"scene {scene.id}: car is not primary")
        else:car_first+=1
        families.append(family);cameras.append(camera);modes.append(mode);motions.append(motion);intents.add(expected.casefold())
        family_counts[family]=family_counts.get(family,0)+1
        metric=_metric(png_path);scene_hashes.add(metric["pixel_hash"]);metric.update({"scene_id":scene.id,"family":family,"camera":camera,"mode":mode,"motion":motion});scenes.append(metric)
    if car_first!=25:errors.append(f"car-first coverage failed: {car_first}/25")
    if len(scene_hashes)<20:errors.append(f"rendered asset uniqueness too low: {len(scene_hashes)}/25")
    if len(set(families))<10:errors.append(f"visual family diversity too low: {len(set(families))}/10")
    if len(set(cameras))<10:errors.append(f"camera diversity too low: {len(set(cameras))}/10")
    if len(set(modes))<5:errors.append(f"semantic mode diversity too low: {len(set(modes))}/5")
    if len(set(motions))<5:errors.append(f"motion diversity too low: {len(set(motions))}/5")
    if len(intents)<20:errors.append(f"visual intent diversity too low: {len(intents)}/20")
    if any(v>4 for v in family_counts.values()):errors.append(f"family repeated more than 4 times: {family_counts}")
    shorts_report=[]
    for i,path in enumerate(shorts,1):
        if not path.is_file():errors.append(f"Short {i} missing");continue
        try:size=_probe_size(path);dur=_duration(path)
        except Exception as exc:errors.append(f"Short {i} probe failed: {exc}");continue
        if size!=SHORT_SIZE:errors.append(f"Short {i} is {size}, expected 1080x1920")
        if not 28<=dur<=59:errors.append(f"Short {i} duration {dur:.2f}s outside 28-59s")
        srt=RUN/f"short_segments_{i}"/"short.srt";ok,reason,sm=_srt_metrics(srt,4,52)
        if not ok:errors.append(f"Short {i}: {reason}")
        rois=[_subtitle_roi(path,max(.5,dur*.25),True),_subtitle_roi(path,max(.6,dur*.75),True)]
        # Ignore sub-1% bright-pixel noise at the ROI boundary; only meaningful
        # subtitle occupancy can fail the safe-margin gate.
        if any((r["touches_edge"] and r["bright_ratio"]>0.01) or r["bright_ratio"]>0.18 or r["area_ratio"]>0.30 for r in rois):errors.append(f"Short {i}: subtitle visual occupancy/edge safety failed: {rois}")
        shorts_report.append({"index":i,"duration":round(dur,3),"resolution":list(size),"subtitle":sm,"subtitle_roi":rois})
    if not master.is_file():errors.append("master missing")
    else:
        srt=RUN/"arabic.srt";ok,reason,mm=_srt_metrics(srt,25,60)
        if not ok:errors.append(f"master subtitles: {reason}")
        md=_duration(master);rois=[_subtitle_roi(master,max(.5,md*.25),False),_subtitle_roi(master,max(.6,md*.75),False)]
        if any((r["touches_edge"] and r["bright_ratio"]>0.01) or r["bright_ratio"]>0.20 or r["area_ratio"]>0.34 for r in rois):errors.append(f"master subtitle visual occupancy/edge safety failed: {rois}")
    score=max(0.0,100.0-max(0,25-car_first)*3-max(0,20-len(scene_hashes))*2-max(0,10-len(set(families)))-max(0,10-len(set(cameras)))-max(0,5-len(set(motions)))*2)
    if errors:score=min(score,84.0)
    result={"passed":not errors,"gate_version":"v4","errors":errors,"average_score":round(score,1),"car_first_scenes":car_first,"unique_pixel_assets":len(scene_hashes),"unique_visual_families":len(set(families)),"unique_camera_angles":len(set(cameras)),"unique_modes":len(set(modes)),"unique_motions":len(set(motions)),"visual_intents_verified":len(intents),"family_counts":family_counts,"scenes":scenes,"shorts":shorts_report}
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors:raise RuntimeError("VISUAL PRODUCT GATE V4 FAILED: "+"; ".join(errors))
    return result
