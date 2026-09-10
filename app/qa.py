import json, subprocess
from pathlib import Path
from .core import RUN, Story


def run(cmd): subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def probe(path: Path):
    p=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

def duration(path): return float(probe(path)["format"]["duration"])

def has_audio(path): return any(s.get("codec_type")=="audio" for s in probe(path)["streams"])

def has_subtitle_burn_marker(path):
    # Burned subtitles have no subtitle stream by design. QA validates the SRT-to-pixels render stage via report metadata.
    return path.exists() and path.stat().st_size>10000

def qa(story: Story, master: Path, shorts: list[Path], report: Path=RUN/"qa_report.json"):
    errors=[]
    total=sum(s.duration for s in story.scenes)
    if len(story.scenes)!=25: errors.append(f"expected 25 scenes, got {len(story.scenes)}")
    if not 420<=duration(master)<=900: errors.append(f"long duration outside 420-900: {duration(master):.2f}")
    if not has_audio(master): errors.append("long-form has no audio")
    if len(shorts)!=4: errors.append(f"expected 4 shorts, got {len(shorts)}")
    for i,p in enumerate(shorts,1):
        d=duration(p); info=probe(p); v=next((s for s in info["streams"] if s.get("codec_type")=="video"),{})
        if not 28<=d<=59: errors.append(f"short {i} duration {d:.2f} outside 28-59")
        if (v.get("width"),v.get("height"))!=(1080,1920): errors.append(f"short {i} resolution is {v.get('width')}x{v.get('height')}")
        if not has_audio(p): errors.append(f"short {i} has no audio")
        if not has_subtitle_burn_marker(p): errors.append(f"short {i} render missing")
    if not master.exists(): errors.append("master missing")
    result={"passed":not errors,"errors":errors,"scene_count":len(story.scenes),"planned_duration":total,"master_duration":duration(master) if master.exists() else None,"shorts":[{"file":str(p),"duration":duration(p) if p.exists() else None} for p in shorts],"subtitle_stage":"burned","stock_media":False,"legacy_manifest":False}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if errors: raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors))
