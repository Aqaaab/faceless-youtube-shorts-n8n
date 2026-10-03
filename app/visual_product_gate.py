from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from .core import RUN, Story
from .production_contract import LANDSCAPE_ASPECT, PIPELINE_CONTRACT_VERSION, SCENE_COUNT, SHORT_DELIVERY_COUNT

def run_visual_product_gate(story: Story, final: Path, shorts: list[Path], out: Path=RUN/"visual_product_gate.json", check_subtitles: bool=False)->dict:
    errors=[]; metas=[]; previews=[]
    by_id={s.id:s for s in story.scenes}
    for sid in range(1,SCENE_COUNT+1):
        video=RUN/"scenes"/f"scene_{sid:02d}.mp4"; meta=RUN/"scenes"/f"scene_{sid:02d}.json"; preview=RUN/"scenes"/f"scene_{sid:02d}.png"
        if not video.is_file() or video.stat().st_size==0: errors.append(f"scene {sid}: missing WanGP video")
        if not meta.is_file(): errors.append(f"scene {sid}: missing WanGP metadata")
        if not preview.is_file(): errors.append(f"scene {sid}: missing WanGP preview")
        if not meta.is_file(): continue
        try: data=json.loads(meta.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc: errors.append(f"scene {sid}: invalid metadata: {exc}"); continue
        if data.get("renderer")!="wangp": errors.append(f"scene {sid}: renderer must be wangp")
        if data.get("contract_version")!=PIPELINE_CONTRACT_VERSION: errors.append(f"scene {sid}: stale renderer contract")
        if int(data.get("scene_id",0))!=sid: errors.append(f"scene {sid}: scene_id mismatch")
        if data.get("aspect_ratio")!=LANDSCAPE_ASPECT: errors.append(f"scene {sid}: aspect ratio mismatch")
        if data.get("subject_priority")!="vehicle_primary": errors.append(f"scene {sid}: vehicle is not primary")
        if not str(data.get("reference_media_id","")).strip(): errors.append(f"scene {sid}: missing master reference")
        expected=float(by_id[sid].duration); actual=float(data.get("duration_actual",data.get("duration_requested",0)) or 0)
        if actual<=0 or abs(actual-expected)>1.0: errors.append(f"scene {sid}: duration mismatch {actual:.2f}s vs {expected:.2f}s")
        if preview.is_file():
            with Image.open(preview).convert("L") as im:
                stat=ImageStat.Stat(im)
                if stat.mean[0]<4 or stat.stddev[0]<2: errors.append(f"scene {sid}: preview is degenerate")
                previews.append((sid,im.resize((96,96)).convert("RGB").copy()))
        metas.append(data)
    refs={str(x.get("reference_media_id")) for x in metas if x.get("reference_media_id")}
    cameras={str(x.get("camera")) for x in metas if x.get("camera")}
    families={str(x.get("visual_family")) for x in metas if x.get("visual_family")}
    prompts={str(x.get("prompt_sha256")) for x in metas if x.get("prompt_sha256")}
    if len(refs)!=1: errors.append(f"reference continuity failed: {len(refs)} master references")
    if len(cameras)<8: errors.append(f"camera diversity failed: {len(cameras)}/8")
    if len(families)<8: errors.append(f"visual family diversity failed: {len(families)}/8")
    if len(prompts)<20: errors.append(f"prompt diversity failed: {len(prompts)}/20")
    if len(previews)>1:
        diffs=[ImageStat.Stat(ImageChops.difference(a,b)).mean[0]/255 for (_,a),(_,b) in zip(previews,previews[1:])]
        if sum(d>0.015 for d in diffs)/len(diffs)<0.70: errors.append("adjacent scene visual diversity is too low")
    if not final.is_file() or final.stat().st_size==0: errors.append("master_final.mp4 missing")
    if len(shorts)!=SHORT_DELIVERY_COUNT or any(not p.is_file() or p.stat().st_size==0 for p in shorts): errors.append("four Shorts are not complete")
    if check_subtitles and not all(p.is_file() for p in (RUN/"subtitle_burn.json",RUN/"short_subtitles_burn.json")): errors.append("subtitle evidence missing")
    diversity=min(100.0,(len(cameras)/8)*35+(len(families)/8)*30+(len(prompts)/20)*20+(15 if len(refs)==1 else 0))
    result={"passed":not errors,"errors":errors,"gate_version":"wangp-v1","average_score":round(diversity,2),"vehicle_primary_ratio":round(sum(x.get("subject_priority")=="vehicle_primary" for x in metas)/SCENE_COUNT,4),"car_first_ratio":round(sum(x.get("subject_priority")=="vehicle_primary" for x in metas)/SCENE_COUNT,4),"metrics":{"scene_count":len(metas),"unique_cameras":len(cameras),"unique_families":len(families),"unique_prompts":len(prompts),"reference_count":len(refs),"preview_count":len(previews),"short_count":len(shorts)},"requirements":{"renderer":"wangp","aspect_ratio":LANDSCAPE_ASPECT}}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors: raise RuntimeError("WAN-GP VISUAL PRODUCT GATE FAILED: "+"; ".join(errors))
    return result
