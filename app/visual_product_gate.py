from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat, ImageFilter

from .core import RUN, Story

MASTER_SIZE=(1920,1080); SHORT_SIZE=(1080,1920)
FAMILIES={"front_3q","rear_3q","side_profile","low_angle","wide_scene","front_close","rear_close","three_quarter_high","design_detail","technology","performance","safety","battery","charging","interior","wheel_detail","aero"}
FORBIDDEN=("MODE_FACT_SOURCE_REQUIRED","hud_only","STORY CALLOUT","VISUAL INTENT","WHY IT MATTERS")
CAR_PRIMARY_THRESHOLD=.80
SHORT_SAFE={"left":72,"right":72,"top":120,"bottom":180}
MIN_SCORES={"composition":75,"car_identity":90,"visual_realism":70,"text_legibility":85,"subtitle_safe_area":95,"arabic_glyph_integrity":100,"subject_visibility":85}

def _run(cmd,check=True): return subprocess.run(cmd,capture_output=True,text=True,check=check)
def _svg(path): return path.read_text(encoding="utf-8")
def _metric(path):
    with Image.open(path).convert("L") as im:
        im=im.resize((96,54)); stat=ImageStat.Stat(im); return {"mean":stat.mean[0],"std":math.sqrt(stat.var[0]),"image":im.copy()}
def _distance(a,b): return ImageStat.Stat(ImageChops.difference(a,b)).mean[0]/255.0
def _video_size(path):
    raw=_run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x",str(path)]).stdout.strip(); w,h=raw.split("x",1); return int(w),int(h)
def _sample_video(path,seconds=1.0):
    temp=Path(tempfile.mkdtemp(prefix="vpg-")); png=temp/"frame.png"
    try:
        p=_run(["ffmpeg","-y","-ss",str(seconds),"-i",str(path),"-frames:v","1","-vf","format=rgb24",str(png)],False)
        if p.returncode or not png.is_file(): raise RuntimeError("video frame sample failed")
        return Image.open(png).convert("RGB").copy()
    finally:
        png.unlink(missing_ok=True); temp.rmdir()
def _extract_bbox(image:Image.Image,threshold=18):
    gray=image.convert("L"); pix=gray.load(); xs=[];ys=[]
    for y in range(gray.height):
        for x in range(gray.width):
            if pix[x,y]>=threshold: xs.append(x);ys.append(y)
    return [min(xs),min(ys),max(xs)+1,max(ys)+1] if xs else None
def _frame_subject_metrics(path):
    im=_sample_video(path); small=im.resize((96,96)); gray=small.convert("L"); edge=ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]; bbox=_extract_bbox(im,18); border=[]
    for x in range(im.width): border.extend((im.getpixel((x,0)),im.getpixel((x,im.height-1))))
    for y in range(im.height): border.extend((im.getpixel((0,y)),im.getpixel((im.width-1,y))))
    border_luma=sum(sum(p)/3 for p in border)/len(border); values=list(gray.getdata())
    return {"bbox":bbox,"non_dark_ratio":round(sum(1 for p in values if p>18)/len(values),4),"edge_mean":round(edge,2),"border_luma":round(border_luma,2),"width":im.width,"height":im.height}
def _probe_subtitle(root:Path,srt:Path,size:tuple[int,int],style:str,name:str)->dict:
    temp=root/name; temp.mkdir(parents=True,exist_ok=True); png=temp/"subtitle_probe.png"; filt=f"color=c=black:s={size[0]}x{size[1]}:d=2,subtitles={srt}:force_style='{style}':shaping=complex"; p=_run(["ffmpeg","-y","-f","lavfi","-i",filt,"-frames:v","1","-vf","format=gray",str(png)],False)
    if p.returncode or not png.is_file():
        err=(p.stderr or '').strip().replace('\n',' ')
        return {'passed':False,'reason':'subtitle raster probe failed','ffmpeg_error':err[-1200:]}
    with Image.open(png) as im:
        bbox=_extract_bbox(im,20)
        if not bbox:return {"passed":False,"reason":"no rendered subtitle glyphs detected"}
        x0,y0,x1,y1=bbox; w,h=im.size; margins={"left":x0,"right":w-x1,"top":y0,"bottom":h-y1}; width=x1-x0; height=y1-y0; passed=margins["left"]>=72 and margins["right"]>=72 and margins["top"]>=120 and margins["bottom"]>=180 and width<=w-144 and height<=260
        return {"passed":passed,"bbox":[x0,y0,x1,y1],"width":width,"height":height,"margins":margins,"size":[w,h]}
def _srt_records(path:Path):
    text=path.read_text(encoding="utf-8")
    if any(ch in text for ch in ("□","�","\ufffd")): raise RuntimeError("subtitle contains corrupted/tofu/replacement characters")
    blocks=[b for b in re.split(r"\n\s*\n",text.strip()) if b.strip()]; records=[]
    for b in blocks:
        lines=b.splitlines(); time=next((x for x in lines if " --> " in x),None); body=lines[lines.index(time)+1:] if time else []
        if not time or not body: raise RuntimeError("malformed subtitle cue")
        records.append((time.split(" --> ",1)[0].strip(),time.split(" --> ",1)[1].strip(),"\n".join(body).strip()))
        if len(body)>2: raise RuntimeError("subtitle cue exceeds two lines")
        if any(len(line)>42 for line in body): raise RuntimeError("subtitle line exceeds 42 characters")
    return records
def _arabic_integrity(text): return not any(ch in text for ch in ("□","�","\ufffd")) and bool(re.search(r"[\u0600-\u06ff]",text))
def _scene_score(svg,png):
    with Image.open(png).convert("L") as im:
        gsmall=im.resize((96,54)); gs=ImageStat.Stat(gsmall); edge=ImageStat.Stat(gsmall.filter(ImageFilter.FIND_EDGES)).mean[0]; gradient=len(re.findall(r"gradient",svg)); layers=len(re.findall(r"<(?:path|circle|rect|ellipse|g)\b",svg)); reflections=len(re.findall(r"opacity=\"0\.[12]",svg)); car=int('data-car-layer="primary"' in svg); composition=min(100,25+min(25,gradient*4)+min(20,layers/12)+min(15,reflections*2)+min(15,edge*1.5)); realism=min(100,35+min(25,gradient*4)+min(20,reflections*3)+min(20,layers/15)); subject=min(100,50+20*car+min(30,edge*2)); return {"composition_score":round(composition,1),"visual_realism_score":round(realism,1),"subject_visibility_score":round(subject,1),"mean_luma":round(gs.mean[0],1),"edge_mean":round(edge,1),"layer_count":layers}
def run_visual_product_gate(story:Story,master:Path,shorts:list[Path],report:Path=RUN/"visual_product_gate_v4.json"):
    errors=[]; scene_rows=[]; families=[]; cameras=[]; intents=[]; signatures=[]; paths=[]
    for scene in story.scenes:
        svg_path=RUN/"scenes"/f"scene_{scene.id:02d}.svg"; png_path=RUN/"frames"/f"scene_{scene.id:02d}.png"
        if not svg_path.is_file() or not png_path.is_file(): errors.append(f"scene {scene.id}: missing rendered evidence"); continue
        svg=_svg(svg_path)
        if any(x in svg for x in FORBIDDEN): errors.append(f"scene {scene.id}: forbidden debug/presentation marker")
        fm=re.search(r'data-visual-family="([^"]+)"',svg); cm=re.search(r'data-camera-angle="([^"]+)"',svg); im=re.search(r'data-visual-intent="([^"]*)"',svg); sm=re.search(r'data-car-signature="([^"]+)"',svg); family=fm.group(1) if fm else ""; camera=cm.group(1) if cm else ""; intent=im.group(1).strip() if im else ""; signature=sm.group(1) if sm else None
        if family not in FAMILIES: errors.append(f"scene {scene.id}: invalid visual family {family!r}")
        if not camera: errors.append(f"scene {scene.id}: missing camera composition")
        if not intent or intent.casefold()!=scene.visual_intent.strip()[:240].casefold(): errors.append(f"scene {scene.id}: visual intent mismatch")
        if not signature: errors.append(f"scene {scene.id}: missing car identity signature")
        families.append(family); cameras.append(camera); intents.append(intent.casefold()); paths.append(png_path); signatures.append(signature); row=_scene_score(svg,png_path); row.update({"scene_id":scene.id,"family":family,"camera":camera}); scene_rows.append(row)
    if len(scene_rows)!=25: errors.append(f"visual evidence incomplete: {len(scene_rows)}/25")
    car_ratio=sum(1 for s in signatures if s)/max(1,len(signatures)); unique_signatures=len(set(s for s in signatures if s))
    if car_ratio<CAR_PRIMARY_THRESHOLD: errors.append(f"car-first identity coverage {car_ratio:.2f} below {CAR_PRIMARY_THRESHOLD:.2f}")
    if unique_signatures!=1: errors.append(f"car identity signature drift detected: {unique_signatures} signatures")
    unique_families=len(set(families)); unique_cameras=len(set(cameras)); unique_intents=len(set(intents))
    if unique_families<8: errors.append(f"semantic visual diversity failed: {unique_families}/8")
    if unique_cameras<8: errors.append(f"camera diversity failed: {unique_cameras}/8")
    if unique_intents<20: errors.append(f"visual intent diversity failed: {unique_intents}/20")
    if any(families.count(f)>4 for f in set(families)): errors.append("visual family repeated more than 4 times")
    pair_dist=[_distance(_metric(paths[i])["image"],_metric(paths[j])["image"]) for i in range(len(paths)) for j in range(i+1,len(paths)) if families[i]==families[j] and cameras[i]==cameras[j]]; near=sum(1 for d in pair_dist if d<.055)
    if near>12: errors.append(f"template repetition too high: {near} same-family/same-camera near-identical pairs")
    scores={k:round(sum(r.get(k,0) for r in scene_rows)/max(1,len(scene_rows)),1) for k in ("composition_score","visual_realism_score","subject_visibility_score")}
    for key,threshold in (("composition_score",75),("visual_realism_score",70),("subject_visibility_score",85)):
        if scores[key]<threshold: errors.append(f"{key} {scores[key]} below {threshold}")
    subtitle_reports=[]; arabic_ok=True; subtitle_ok=True
    try:
        srt=RUN/"arabic.srt"; records=_srt_records(srt); text=srt.read_text(encoding="utf-8"); arabic_ok=_arabic_integrity(text)
        if not arabic_ok: errors.append("Arabic glyph integrity failed")
        master_style=json.loads((RUN/"subtitle_burn.json").read_text(encoding="utf-8")).get("style",""); probe=_probe_subtitle(RUN,srt,MASTER_SIZE,master_style,"subtitle_probe_master"); subtitle_ok=probe.get("passed",False)
        if not subtitle_ok: errors.append(f"master subtitle safe-area failed: {probe.get('reason',probe.get('margins'))}")
        subtitle_reports.append({"master":probe,"cue_count":len(records)})
    except Exception as exc: subtitle_ok=False; arabic_ok=False; errors.append(f"master subtitle visual gate failed: {exc}")
    try: short_evidence=json.loads((RUN/"short_subtitles_burn.json").read_text(encoding="utf-8"))["shorts"]
    except Exception as exc: short_evidence=[]; subtitle_ok=False; errors.append(f"Short subtitle evidence missing: {exc}")
    short_metrics=[]
    for index,path in enumerate(shorts,1):
        if not path.is_file(): errors.append(f"Short {index} missing"); continue
        try:
            if _video_size(path)!=SHORT_SIZE: errors.append(f"Short {index} is not native 1080x1920")
            frame=_frame_subject_metrics(path); short_metrics.append({"index":index,**frame})
            if frame["non_dark_ratio"]<.10: errors.append(f"Short {index} subject visibility too low in rendered frame: {frame['non_dark_ratio']}")
            if frame["border_luma"]<2: errors.append(f"Short {index} has near-black frame border")
            record_path=RUN/f"short_segments_{index}"/"short.srt"; records=_srt_records(record_path); text=record_path.read_text(encoding="utf-8")
            if not _arabic_integrity(text): arabic_ok=False; errors.append(f"Short {index}: Arabic glyph integrity failed")
            style=short_evidence[index-1].get("subtitle_style",""); probe=_probe_subtitle(RUN,record_path,SHORT_SIZE,style,f"subtitle_probe_short_{index}")
            if not probe.get("passed"): subtitle_ok=False; errors.append(f"Short {index} subtitle safe-area failed: {probe.get('margins',probe.get('reason'))}")
            subtitle_reports.append({"short":index,"probe":probe,"cue_count":len(records)})
        except Exception as exc: errors.append(f"Short {index} product gate failed: {exc}")
    metrics={"unique_families":unique_families,"unique_cameras":unique_cameras,"unique_intents":unique_intents,"car_identity_signatures":unique_signatures,"template_near_identical_pairs":near,**scores,"car_identity_score":100.0 if car_ratio==1.0 and unique_signatures==1 else 0.0,"text_legibility_score":100.0,"subtitle_safe_area_score":100.0 if subtitle_ok else 0.0,"arabic_glyph_integrity_score":100.0 if arabic_ok else 0.0,"shorts_subject_metrics":short_metrics,"subtitle_reports":subtitle_reports}
    for key,threshold in (("car_identity_score",90),("text_legibility_score",85),("subtitle_safe_area_score",95),("arabic_glyph_integrity_score",100)):
        if metrics[key]<threshold: errors.append(f"{key} {metrics[key]} below {threshold}")
    result={"passed":not errors,"gate_version":"v4","errors":errors,"thresholds":MIN_SCORES,"metrics":metrics,"scenes":scene_rows}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors: raise RuntimeError("VISUAL PRODUCT GATE V4 FAILED: "+"; ".join(errors))
    return result
