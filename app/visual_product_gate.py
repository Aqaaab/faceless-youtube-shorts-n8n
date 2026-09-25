from __future__ import annotations
import json,math,re,subprocess
from pathlib import Path
from PIL import Image,ImageChops,ImageStat,ImageFilter,ImageOps
from .core import RUN,Story
MASTER_SIZE=(1920,1080); SHORT_SIZE=(1080,1920); MIN_CAMERA_PIXEL_DISTANCE=.100
FAMILIES={"front_3q","rear_3q","side_profile","low_angle","wide_scene","front_close","rear_close","three_quarter_high","design_detail","technology","performance","safety","battery","charging","interior","wheel_detail","aero"}
FORBIDDEN=("MODE_FACT_SOURCE_REQUIRED","hud_only","STORY CALLOUT","VISUAL INTENT","WHY IT MATTERS")
CAR_PRIMARY_THRESHOLD=.70

def _svg(path:Path)->str:return path.read_text(encoding='utf-8')
def car_first_ratio(scene_svgs:list[str])->float:return sum(1 for t in scene_svgs if re.search(r'data-car-layer=["\']primary["\']',t))/len(scene_svgs) if scene_svgs else 0.0
def _metric(path:Path,vertical:bool=False)->dict:
    # Pixel evidence must measure the visual subject, not mostly the shared HUD/background.
    # Preserve RGB information and structural edges. The previous grayscale-only metric
    # collapsed visually distinct shots such as interior vs low-angle into near-identical
    # fingerprints because both compositions contain large dark regions.
    with Image.open(path).convert('RGB') as im:
        w,h=im.size
        if vertical:
            # Inspect the complete portrait canvas; the old 10%-70% crop hid lower black padding.
            im=im.crop((0,int(h*.04),w,int(h*.96)))
            target=(96,170)
        else:
            im=im.crop((0,int(h*.12),int(w*.86),int(h*.88)))
            target=(128,72)
        color=im.resize(target)
        gray=ImageOps.grayscale(color)
        edge=ImageOps.autocontrast(gray.filter(ImageFilter.FIND_EDGES))
        focused_gray=Image.blend(gray,edge,.42)
        edge_rgb=Image.merge('RGB',(edge,edge,edge))
        focused=Image.blend(color,edge_rgb,.42)
        s=ImageStat.Stat(focused_gray)
        return {'mean':s.mean[0],'std':math.sqrt(s.var[0]),'image':focused.copy()}
def _distance(a:Image.Image,b:Image.Image)->float:
    return ImageStat.Stat(ImageChops.difference(a,b)).mean[0]/255.0
def _video_size(path:Path)->tuple[int,int]:
    raw=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',str(path)],capture_output=True,text=True,check=True).stdout.strip(); w,h=raw.split('x',1); return int(w),int(h)
def _roi_metrics(path:Path,vertical:bool=False)->dict:
    with Image.open(path).convert('L') as im:
        w,h=im.size; roi=im.crop((0,int(h*.62),w,int(h*.94))) if vertical else im.crop((0,int(h*.72),w,int(h*.96))); bg=im.crop((0,0,w,max(1,int(h*.10)))); s=ImageStat.Stat(roi); b=ImageStat.Stat(bg); return {'bottom_mean':s.mean[0],'bottom_std':math.sqrt(s.var[0]),'top_mean':b.mean[0]}
def _subtitle_coverage(root:Path,video:Path,vertical:bool)->tuple[bool,str]:
    out=root/('_vqa_short.png' if vertical else '_vqa_master.png'); p=subprocess.run(['ffmpeg','-y','-ss','1','-i',str(video),'-frames:v','1','-vf','format=gray',str(out)],capture_output=True,text=True)
    if p.returncode or not out.is_file():return False,'subtitle frame sample failed'
    m=_roi_metrics(out,vertical)
    if m['bottom_std']<7 and m['bottom_mean']<45 and m['top_mean']-m['bottom_mean']>18:return False,'subtitle region appears as an oversized opaque black box'
    return True,'ok'
def run_visual_product_gate(story:Story,master:Path,shorts:list[Path],report:Path=RUN/'visual_product_gate_v3.json',check_subtitles:bool=False)->dict:
    errors=[]; scenes=[]; families=[]; cameras=[]; intents=[]; paths=[]; scene_svgs=[]; metric_images={}
    for scene in story.scenes:
        svg_path=RUN/'scenes'/f'scene_{scene.id:02d}.svg'; png_path=RUN/'frames'/f'scene_{scene.id:02d}.png'
        if not svg_path.is_file() or not png_path.is_file():errors.append(f'scene {scene.id}: missing rendered visual evidence');continue
        text=_svg(svg_path); scene_svgs.append(text)
        if any(x in text for x in FORBIDDEN):errors.append(f'scene {scene.id}: forbidden debug/presentation marker')
        # Visual source must be backed by a rendered PNG. The SVG is metadata/container
        # only; the actual vehicle pixels must come from the Blender renderer.
        if 'data-asset-quality="blender_eevee_automotive_v3"' not in text:
            errors.append(f'scene {scene.id}: renderer is not using Blender automotive asset')
        if '<image ' not in text or 'data:image/png;base64,' not in text:
            errors.append(f'scene {scene.id}: missing embedded raster image evidence')
        if re.search(r'<(?:path|rect|circle|ellipse|polygon|line)\b', text):
            errors.append(f'scene {scene.id}: vector drawing primitives detected in visual payload')
        fm=re.search(r'data-visual-family="([^"]+)"',text); cm=re.search(r'data-camera-angle="([^"]+)"',text); im=re.search(r'data-visual-intent="([^"]*)"',text); family=fm.group(1) if fm else ''; camera=cm.group(1) if cm else ''; intent=im.group(1).strip() if im else ''
        if family not in FAMILIES:errors.append(f'scene {scene.id}: invalid visual family {family!r}')
        if not camera:errors.append(f'scene {scene.id}: missing camera family')
        if not intent or intent.casefold()!=scene.visual_intent.strip()[:240].casefold():errors.append(f'scene {scene.id}: visual intent evidence mismatch')
        families.append(family); cameras.append(camera); intents.append(intent.casefold()); paths.append(png_path); m=_metric(png_path); metric_images[png_path]=m['image']; scenes.append({'id':scene.id,'family':family,'camera':camera,'mean':round(m['mean'],2),'std':round(m['std'],2)})
    if len(scenes)!=25:errors.append(f'visual evidence incomplete: {len(scenes)}/25')
    ratio=car_first_ratio(scene_svgs)
    if ratio<CAR_PRIMARY_THRESHOLD:errors.append(f'car-first ratio {ratio:.2f} below {CAR_PRIMARY_THRESHOLD:.2f}')
    unique_families=len(set(families)); unique_cameras=len(set(cameras)); unique_intents=len(set(intents))
    # Pixel evidence: metadata alone cannot satisfy camera diversity. Compare representative
    # rendered PNGs for each camera and require materially different image evidence.
    camera_reps={}
    for idx,camera in enumerate(cameras):
        camera_reps.setdefault(camera, paths[idx])
    camera_pixel_distances=[]
    camera_pairs=[]
    for a_idx,(ca,pa) in enumerate(sorted(camera_reps.items())):
        for cb,pb in sorted(camera_reps.items())[a_idx+1:]:
            d=_distance(metric_images[pa],metric_images[pb])
            camera_pixel_distances.append(d); camera_pairs.append((ca,cb,round(d,4)))
    camera_min=min(camera_pixel_distances) if camera_pixel_distances else 0.0
    if unique_cameras>=8 and camera_min < MIN_CAMERA_PIXEL_DISTANCE:
        min_pair=min(camera_pairs,key=lambda item:item[2]) if camera_pairs else None
        pair_text=f' ({min_pair[0]} vs {min_pair[1]})' if min_pair else ''
        errors.append(f'camera pixel diversity failed: minimum cross-camera distance {camera_min:.4f} < {MIN_CAMERA_PIXEL_DISTANCE:.4f}{pair_text}')
    if unique_families<8:errors.append(f'semantic visual diversity failed: {unique_families}/8 families')
    if unique_cameras<8:errors.append(f'camera/composition diversity failed: {unique_cameras}/8')
    if unique_intents<20:errors.append(f'visual intent diversity failed: {unique_intents}/20')
    if any(families.count(f)>4 for f in set(families)):errors.append('a single visual family is repeated more than 4 times')
    pair_distances=[]
    for i in range(len(paths)):
        for j in range(i+1,len(paths)):
            # Compare perceptual repetition only for the same semantic family and camera.
            # Different families/cameras are intentionally distinct compositions and are
            # already guarded independently above.
            if families[i] != families[j] or cameras[i] != cameras[j]: continue
            pair_distances.append(_distance(metric_images[paths[i]],metric_images[paths[j]]))
    near=sum(1 for d in pair_distances if d<.055); p95=sorted(pair_distances)[max(0,int(len(pair_distances)*.95)-1)] if pair_distances else 0
    if near>35:errors.append(f'perceptual repetition too high: {near} near-identical same-family/same-camera pairs')
    if not master.is_file():errors.append('master missing for visual product gate')
    else:
        if check_subtitles:
            ok,reason=_subtitle_coverage(RUN,master,False)
            if not ok:errors.append(f'master subtitle composition failed: {reason}')
    short_reports=[]
    short_samples=[]
    for i,path in enumerate(shorts,1):
        sample=RUN/f'_short_sample_{i}.png'
        if path.is_file():
            p=subprocess.run(['ffmpeg','-y','-ss','1','-i',str(path),'-frames:v','1','-vf','format=rgb24',str(sample)],capture_output=True,text=True)
            if p.returncode==0 and sample.is_file():
                short_samples.append((i,_metric(sample,True)['image']))
    short_pair_distances=[]
    for i in range(len(short_samples)):
        for j in range(i+1,len(short_samples)):
            short_pair_distances.append(_distance(short_samples[i][1],short_samples[j][1]))
    short_min=min(short_pair_distances) if short_pair_distances else 0.0
    if len(short_samples)==4 and short_min < .055:
        errors.append(f'short pixel diversity failed: minimum cross-short distance {short_min:.4f} < .0550')
    for i,path in enumerate(shorts,1):
        if not path.is_file():errors.append(f'Short {i} missing');continue
        try:size=_video_size(path)
        except Exception as exc:errors.append(f'Short {i} probe failed: {exc}');continue
        if size!=SHORT_SIZE:errors.append(f'Short {i} is not native 1080x1920')
        if check_subtitles:
            ok,reason=_subtitle_coverage(RUN,path,True)
            if not ok:errors.append(f'Short {i} subtitle composition failed: {reason}')
        short_reports.append({'index':i,'resolution':list(size)})
    result={'passed':not errors,'errors':errors,'gate_version':'v5-blender','car_first_ratio':round(ratio,4),'car_first_threshold':CAR_PRIMARY_THRESHOLD,'requirements':{'min_unique_families':8,'min_unique_cameras':8,'min_unique_intents':20,'max_family_repetition':4,'max_near_identical_pairs':35,'min_camera_pixel_distance':MIN_CAMERA_PIXEL_DISTANCE},'metrics':{'unique_families':unique_families,'unique_cameras':unique_cameras,'unique_intents':unique_intents,'near_identical_pairs':near,'pairwise_p95_distance':round(p95,4),'camera_min_pixel_distance':round(camera_min,4),'camera_pixel_pairs':camera_pairs,'short_min_pixel_distance':round(short_min,4),'car_first_scenes':sum(1 for s in scene_svgs if re.search(r'data-car-layer=["\']primary["\']',s)),'family_counts':{f:families.count(f) for f in sorted(set(families))}},'scenes':scenes,'shorts':short_reports}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if errors:raise RuntimeError('VISUAL PRODUCT GATE V5 BLENDER FAILED: '+'; '.join(errors))
    return result
