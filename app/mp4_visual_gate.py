from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageFilter, ImageStat

SHORT_SIZE=(1080,1920)
MASTER_SIZE=(1920,1080)

def _probe_size(path:Path):
    raw=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","csv=p=0:s=x",str(path)],capture_output=True,text=True,check=True).stdout.strip()
    w,h=raw.split("x"); return int(w),int(h)

def _sample(path:Path, second:float, out:Path):
    subprocess.run(["ffmpeg","-y","-ss",str(max(0,second)),"-i",str(path),"-frames:v","1","-vf","format=rgb24",str(out)],capture_output=True,check=True)

def _band_stats(im, y0, y1):
    crop=im.crop((0,y0,im.width,y1)).convert("L")
    s=ImageStat.Stat(crop)
    edge=ImageStat.Stat(crop.filter(ImageFilter.FIND_EDGES))
    return float(s.mean[0]), float(s.stddev[0]), float(edge.mean[0])

def _portrait_frame_ok(sample:Path):
    with Image.open(sample).convert("RGB") as im:
        h=im.height
        top,mid,bottom=(_band_stats(im,0,int(h*.12)),_band_stats(im,int(h*.44),int(h*.56)),_band_stats(im,int(h*.88),h))
        if mid[0]-bottom[0] > 16 and bottom[1] < 5.5 and bottom[2] < 3.0:
            return False, f"black/empty bottom padding detected (middle mean={mid[0]:.1f}, bottom mean={bottom[0]:.1f})"
        if top[0]-bottom[0] > 24 and bottom[1] < 4.0 and bottom[2] < 2.0:
            return False, "near-black bottom letterbox detected"
        if bottom[1] < 2.0 and bottom[2] < 1.2:
            return False, "bottom delivery band is effectively blank"
        return True, "full-frame portrait signal present"

def _portrait_fill_ok(path:Path, samples:list[Path]):
    size=_probe_size(path)
    if size != SHORT_SIZE:
        return False, f"resolution {size[0]}x{size[1]} is not 1080x1920"
    for sample in samples:
        ok,reason=_portrait_frame_ok(sample)
        if not ok:
            return False, reason
    return True, "full-frame portrait signal present across samples"

def _raster_texture_ok(path:Path, sample:Path):
    with Image.open(sample).convert("RGB") as im:
        # Central subject ROI. A purely flat/vector-like plate has very little
        # high-frequency residual after removing broad lighting gradients.
        roi=im.crop((int(im.width*.08),int(im.height*.16),int(im.width*.92),int(im.height*.82)))
        gray=roi.convert("L")
        # Use FIND_EDGES on the native ROI plus local contrast as delivery evidence.
        edge=ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES))
        stat=ImageStat.Stat(gray)
        if edge.mean[0] < 2.6 or stat.stddev[0] < 16:
            return False, f"insufficient photographic surface detail (edge={edge.mean[0]:.2f}, std={stat.stddev[0]:.2f})"
        return True, "surface-detail signal present"

def run_mp4_visual_product_gate(master:Path,shorts:list[Path],report:Path):
    errors=[]; shorts_report=[]
    tmp=report.parent/"_mp4_visual_samples"; tmp.mkdir(parents=True,exist_ok=True)
    try:
        for i,path in enumerate([master]+list(shorts)):
            if not path.is_file() or path.stat().st_size==0:
                errors.append(f"missing video: {path}"); continue
            size=_probe_size(path)
            sample=tmp/f"sample_{i}.png"; _sample(path,1.0,sample)
            with Image.open(sample).convert("RGB") as im:
                mean,std,edge=_band_stats(im,0,im.height)
            item={"file":str(path),"resolution":[size[0],size[1]],"mean_luma":round(mean,2),"std_luma":round(std,2),"edge_mean":round(edge,2)}
            if path in shorts:
                duration=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(path)],capture_output=True,text=True,check=True).stdout.strip())
                samples=[]
                for j,point in enumerate((0.5,max(0.5,duration*0.33),max(0.5,duration*0.66),max(0.5,duration-0.5))):
                    sp=tmp/f"sample_{i}_{j}.png"; _sample(path,min(point,max(0.1,duration-0.05)),sp); samples.append(sp)
                ok,reason=_portrait_fill_ok(path,samples)
                if not ok: errors.append(f"Short {shorts.index(path)+1}: {reason}")
                texture_ok,texture_reason=_raster_texture_ok(path,samples[1])
                if not texture_ok: errors.append(f"Short {shorts.index(path)+1} raster realism gate: {texture_reason}")
                item["portrait_fill"]=reason
                item["raster_texture"]=texture_reason
            else:
                if size != MASTER_SIZE: errors.append("master is not 1920x1080")
                ok,reason=_raster_texture_ok(path,sample)
                if not ok: errors.append(f"master raster realism gate: {reason}")
                item["raster_texture"]=reason
            shorts_report.append(item)
        result={"passed":not errors,"gate_version":"mp4-v1","errors":errors,"master_checked":master.is_file(),"shorts_checked":len(shorts),"videos":shorts_report}
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        if errors: raise RuntimeError("MP4 VISUAL PRODUCT GATE FAILED: "+"; ".join(errors))
        return result
    finally:
        for p in tmp.glob("sample_*.png"):
            p.unlink(missing_ok=True)
        try: tmp.rmdir()
        except OSError: pass
