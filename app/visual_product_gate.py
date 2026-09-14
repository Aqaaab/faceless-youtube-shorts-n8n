from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .core import RUN, Story

MASTER_SIZE=(1920,1080)
SHORT_SIZE=(1080,1920)
FAMILIES={"front_3q","rear_3q","side_profile","low_angle","wide_scene","design_detail","technology","performance","safety","battery","charging","interior","wheel_detail","aero"}
FORBIDDEN=("MODE_FACT_SOURCE_REQUIRED","hud_only","STORY CALLOUT","VISUAL INTENT","WHY IT MATTERS")
CAR_PRIMARY_THRESHOLD=0.70


def _svg(path:Path)->str:
    return path.read_text(encoding="utf-8")


def car_first_ratio(scene_svgs: list[str]) -> float:
    if not scene_svgs:
        return 0.0
    primary=sum(1 for text in scene_svgs if re.search(r'data-car-layer=["\']primary["\']', text))
    return primary/len(scene_svgs)


def _metric(path:Path)->dict:
    with Image.open(path).convert("L") as im:
        im=im.resize((96,54)); stat=ImageStat.Stat(im)
        return {"mean":stat.mean[0],"std":math.sqrt(stat.var[0]),"image":im.copy()}


def _distance(a:Image.Image,b:Image.Image)->float:
    return ImageStat.Stat(ImageChops.difference(a,b)).mean[0]/255.0


def _roi_metrics(path:Path,vertical:bool=False)->dict:
    with Image.open(path).convert("L") as im:
        w,h=im.size; roi=im.crop((0,int(h*.62),w,int(h*.94))) if vertical else im.crop((0,int(h*.72),w,int(h*.96)))
        bg=im.crop((0,0,w,max(1,int(h*.10))))
        return {"bottom_mean":ImageStat.Stat(roi).mean[0],"bottom_std":math.sqrt(ImageStat.Stat(roi).var()[0]),"top_mean":ImageStat.Stat(bg).mean[0]}


def _subtitle_coverage(root:Path,video:Path,vertical:bool)->tuple[bool,str]:
    out=root/("_vqa_short.png" if vertical else "_vqa_master.png")
    cmd=["ffmpeg","-y","-ss","1","-i",str(video),"-frames:v","1","-vf","format=gray",str(out)]
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode or not out.is_file(): return False,"subtitle frame sample failed"
    m=_roi_metrics(out,vertical)
    if m["bottom_std"] < 7 and m["bottom_mean"] < 45 and m["top_mean"]-m["bottom_mean"] > 18:
        return False,"subtitle region appears as an oversized opaque black box"
    return True,"ok"


def run_visual_product_gate(story:Story,master:Path,shorts:list[Path],report:Path=RUN/"visual_product_gate_v3.json")->dict:
    errors=[]; scenes=[]; families=[]; cameras=[]; intents=[]; paths=[]; scene_svgs=[]
    for scene in story.scenes:
        svg_path=RUN/"scenes"/f"scene_{scene.id:02d}.svg"; png_path=RUN/"frames"/f"scene_{scene.id:02d}.png"
        if not svg_path.is_file() or not png_path.is_file(): errors.append(f"scene {scene.id}: missing rendered visual evidence"); continue
        text=_svg(svg_path); scene_svgs.append(text)
        if any(x in text for x in FORBIDDEN): errors.append(f"scene {scene.id}: forbidden debug/presentation marker")
        fm=re.search(r'data-visual-family="([^"]+)"',text); cm=re.search(r'data-camera-angle="([^"]+)"',text); im=re.search(r'data-visual-intent="([^"]*)"',text)
        family=fm.group(1) if fm else ""; camera=cm.group(1) if cm else ""; intent=im.group(1).strip() if im else ""
        if family not in FAMILIES: errors.append(f"scene {scene.id}: invalid visual family {family!r}")
        if not camera: errors.append(f"scene {scene.id}: missing camera family")
        if not intent or intent.casefold()!=scene.visual_intent.strip()[:240].casefold(): errors.append(f"scene {scene.id}: visual intent evidence mismatch")
        families.append(family); cameras.append(camera); intents.append(intent.casefold()); paths.append(png_path)
        m=_metric(png_path)
        scenes.append({"id":scene.id,"family":family,"camera":camera,"mean":round(m["mean"],2),"std":round(m["std"],2)})
    if len(scenes)!=25: errors.append(f"visual evidence incomplete: {len(scenes)}/25")
    ratio=car_first_ratio(scene_svgs)
    if ratio<CAR_PRIMARY_THRESHOLD: errors.append(f"car-first ratio {ratio:.2f} below {CAR_PRIMARY_THRESHOLD:.2f}")
    unique_families=len(set(families)); unique_cameras=len(set(cameras)); unique_intents=len(set(intents))
    if unique_families<8: errors.append(f"semantic visual diversity failed: {unique_families}/8 families")
    if unique_cameras<8: errors.append(f"camera/composition diversity failed: {unique_cameras}/8")
    if unique_intents<20: errors.append(f"visual intent diversity failed: {unique_intents}/20")
    if any(families.count(f)>4 for f in set(families)): errors.append("a single visual family is repeated more than 4 times")
    pair_distances=[]
    for i in range(len(paths)):
        for j in range(i+1,len(paths)):
            pair_distances.append(_distance(_metric(paths[i])["image"],_metric(paths[j])["image"]))
    if pair_distances:
        near=sum(1 for d in pair_distances if d<0.055); p95=sorted(pair_distances)[max(0,int(len(pair_distances)*.95)-1)]
        if near>35: errors.append(f"perceptual repetition too high: {near} near-identical scene pairs")
    else: near=0; p95=0
    if not master.is_file(): errors.append("master missing for visual product gate")
    else:
        ok,reason=_subtitle_coverage(RUN,master,False)
        if not ok: errors.append(f"master subtitle composition failed: {reason}")
    short_reports=[]
    for i,path in enumerate(shorts,1):
        if not path.is_file(): errors.append(f"Short {i} missing"); continue
        with Image.open(path) as im:
            if im.size!=SHORT_SIZE: errors.append(f"Short {i} is not native 1080x1920")
        ok,reason=_subtitle_coverage(RUN,path,True)
        if not ok: errors.append(f"Short {i} subtitle composition failed: {reason}")
        short_reports.append({"index":i,"resolution":list(Image.open(path).size)})
    result={"passed":not errors,"errors":errors,"gate_version":"v3","car_first_ratio":round(ratio,4),"car_first_threshold":CAR_PRIMARY_THRESHOLD,"requirements":{"min_unique_families":8,"min_unique_cameras":8,"min_unique_intents":20,"max_family_repetition":4,"max_near_identical_pairs":35},"metrics":{"unique_families":unique_families,"unique_cameras":unique_cameras,"unique_intents":unique_intents,"near_identical_pairs":near,"pairwise_p95_distance":round(p95,4),"car_first_scenes":sum(1 for s in scene_svgs if re.search(r'data-car-layer=["\']primary["\']',s)),"family_counts":{f:families.count(f) for f in sorted(set(families))}},"scenes":scenes,"shorts":short_reports}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors: raise RuntimeError("VISUAL PRODUCT GATE V3 FAILED: "+"; ".join(errors))
    return result
