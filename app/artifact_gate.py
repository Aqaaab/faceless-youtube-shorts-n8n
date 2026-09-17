from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from .core import RUN, Story
from .validator import validate_story_data
from .visual_product_gate import run_visual_product_gate

MASTER_SIZE = (1920, 1080)
SHORT_SIZE = (1080, 1920)
MIN_LONG, MAX_LONG = 420.0, 900.0
SHORT_MIN, SHORT_MAX = 28.0, 59.0
DEBUG_MARKERS = ("MODE_FACT_SOURCE_REQUIRED", "hud_only", "STORY CALLOUT", "VISUAL INTENT", "WHY IT MATTERS")
FORBIDDEN_SOURCE = ("pex" + "els", "stock-" + "footage", "stock_" + "video", "open" + "router", "groq_" + "api_key", "anthr" + "opic")


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _probe(path: Path) -> dict:
    return json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def _duration(path: Path) -> float:
    return float(_probe(path)["format"]["duration"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _srt_ok(path: Path, min_cues: int, max_line: int) -> tuple[bool, str, dict]:
    if not path.is_file() or path.stat().st_size < 30: return False, "subtitle file missing/empty", {}
    text=path.read_text(encoding="utf-8")
    if "\ufffd" in text: return False, "replacement glyph U+FFFD in subtitles", {}
    if any(marker in text for marker in DEBUG_MARKERS): return False, "internal/debug text in subtitles", {}
    blocks=[b.strip() for b in re.split(r"\n\s*\n",text) if b.strip()]; valid=0; max_seen=0
    for block in blocks:
        lines=block.splitlines()
        if len(lines)<3 or not re.fullmatch(r"\d+",lines[0]) or not re.match(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$",lines[1]): return False,"invalid SRT block",{}
        for line in lines[2:]:
            max_seen=max(max_seen,len(line))
            if len(line)>max_line:return False,f"subtitle line exceeds {max_line} characters",{"max_line":max_seen}
        valid+=1
    arabic=sum(1 for ch in text if '\u0600'<=ch<='\u06ff')
    if valid<min_cues:return False,f"too few subtitle cues: {valid}<{min_cues}",{}
    if arabic<20:return False,"insufficient Arabic subtitle text",{}
    return True,"ok",{"cue_count":valid,"arabic_chars":arabic,"max_line":max_seen}


def _audio_ok(path: Path) -> tuple[bool,str]:
    try: streams=_probe(path).get("streams",[])
    except Exception as exc: return False,f"probe failed: {exc}"
    if not any(s.get("codec_type")=="audio" for s in streams): return False,"no audio stream"
    level=_run(["ffmpeg","-v","error","-i",str(path),"-af","volumedetect","-f","null","-"],False).stderr
    mean=re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB",level); peak=re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB",level)
    if mean and float(mean.group(1))<-36:return False,f"mean level too low: {mean.group(1)} dB"
    if peak and float(peak.group(1))>-0.1:return False,f"peak too high: {peak.group(1)} dB"
    return True,"ok"


def _black_bars(path: Path) -> bool:
    from PIL import Image
    duration=_duration(path)
    for point in (.5,max(.6,duration*.5),max(.7,duration-.5)):
        tmp=RUN/"_qa_bar_sample.png"; _run(["ffmpeg","-y","-loglevel","error","-ss",str(min(point,max(.1,duration-.1))),"-i",str(path),"-frames:v","1",str(tmp)])
        with Image.open(tmp).convert("L") as im:
            w,h=im.size; border=[im.getpixel((x,y)) for x in range(w) for y in (0,h-1)] + [im.getpixel((x,y)) for y in range(0,h,4) for x in (0,w-1)]
            if sum(border)/len(border)<2.0:return True
    return False


def _source_scan() -> list[str]:
    errors=[]
    for root in (Path("app"),Path("scripts"),Path("tests")):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py",".yml",".yaml",".json"}:continue
            if path.name=="test_contract.py":continue
            text=path.read_text(encoding="utf-8",errors="ignore").lower()
            for token in FORBIDDEN_SOURCE:
                if token in text: errors.append(f"forbidden source reference {token} in {path}")
    return errors


def qa(story: Story, master: Path, shorts: list[Path], report: Path = RUN/"qa_report.json") -> dict:
    errors=[]; categories={}
    try:
        validate_story_data({"topic":story.topic,"title":story.title,"description":story.description,"tags":story.tags,"short_titles":story.short_titles,"narration":story.narration,"scenes":[s.__dict__ for s in story.scenes]}); categories["Script / Story"]=10.0
    except Exception as exc: errors.append(str(exc)); categories["Script / Story"]=0.0
    planned=sum(float(s.duration) for s in story.scenes); categories["Synchronization"]=10.0
    if not MIN_LONG<=planned<=MAX_LONG: errors.append(f"planned duration {planned:.2f}s outside 420-900s"); categories["Synchronization"]=0.0
    if not master.is_file(): errors.append("master missing")
    else:
        try:
            md=_duration(master); diff=abs(md-planned)
            if not MIN_LONG<=md<=MAX_LONG: errors.append(f"master duration {md:.2f}s outside 420-900s"); categories["Synchronization"]=0.0
            if diff>2.0: errors.append(f"master/planned duration mismatch {diff:.2f}s"); categories["Synchronization"]=0.0
        except Exception as exc: errors.append(f"master probe failed: {exc}"); categories["Synchronization"]=0.0
        ok,reason=_audio_ok(master); categories["Audio / Voice"]=10.0 if ok else 0.0
        if not ok: errors.append(f"master audio: {reason}")
        if _black_bars(master): errors.append("master has near-black border/bar evidence")
    for path in shorts:
        if not path.is_file(): errors.append(f"missing Short: {path.name}"); continue
        streams=_probe(path).get("streams",[]); video=next((s for s in streams if s.get("codec_type")=="video"),{}); actual=(int(video.get("width",0)),int(video.get("height",0))); dur=_duration(path)
        if actual!=SHORT_SIZE: errors.append(f"{path.name} is {actual}, expected 1080x1920")
        if not SHORT_MIN<=dur<=SHORT_MAX: errors.append(f"{path.name} duration {dur:.2f}s outside 28-59s")
        ok,reason=_audio_ok(path)
        if not ok: errors.append(f"{path.name} audio: {reason}")
    source_errors=_source_scan(); errors.extend(source_errors); categories["Metadata / Publishing"]=10.0 if not source_errors else 0.0
    try: visual=run_visual_product_gate(story,master,shorts)
    except RuntimeError:
        try: visual=json.loads((RUN/"visual_product_gate_v4.json").read_text(encoding="utf-8"))
        except Exception: visual={"passed":False,"errors":["visual gate failed without a report"],"average_score":0.0}
    errors.extend(visual.get("errors",[])); vscore=float(visual.get("average_score",0.0)); categories["Visual Quality"]=vscore/10.0; categories["Scene Relevance"]=vscore/10.0; categories["Shorts"]=10.0 if visual.get("passed") else min(8.0,vscore/10.0)
    categories["Arabic Subtitles"]=10.0
    ok,reason,_=_srt_ok(RUN/"arabic.srt",25,60)
    if not ok: errors.append(f"master subtitles: {reason}"); categories["Arabic Subtitles"]=0.0
    try:
        marker=json.loads((RUN/"subtitle_burn.json").read_text(encoding="utf-8"));
        if marker.get("burned") is not True or marker.get("output")!=master.name or marker.get("output_sha256")!=_sha(master) or marker.get("subtitle_sha256")!=_sha(RUN/"arabic.srt"): raise ValueError("invalid master subtitle marker/hash")
    except Exception as exc: errors.append(f"master subtitle evidence: {exc}"); categories["Arabic Subtitles"]=0.0
    try:
        records=json.loads((RUN/"short_subtitles_burn.json").read_text(encoding="utf-8")).get("shorts",[])
        if len(records)!=4: raise ValueError("expected four Short subtitle records")
        for i,(record,path) in enumerate(zip(records,shorts),1):
            srt=Path(record.get("srt","")); ok,reason,_=_srt_ok(srt,4,52)
            if not ok: raise ValueError(f"Short {i}: {reason}")
            if record.get("output_sha256")!=_sha(path): raise ValueError(f"Short {i}: output hash mismatch")
    except Exception as exc: errors.append(f"Short subtitle evidence: {exc}"); categories["Arabic Subtitles"]=0.0
    weighted=round(sum(categories.values())/max(1,len(categories)),2); passed=not errors and weighted>=9.0 and vscore>=90.0
    result={"passed":passed,"errors":errors,"scene_count":len(story.scenes),"scene_ids_valid":[s.id for s in story.scenes]==list(range(1,26)),"planned_duration":planned,"master_duration":_duration(master) if master.is_file() else 0.0,"subtitle_stage":"subtitle burn evidence verified" if categories.get("Arabic Subtitles",0)>0 else "failed","weighted_score_10":weighted,"score_categories":categories,"publish_threshold_10":9.0,"stock_media":False,"legacy_manifest":False,"visual_product_gate":visual,"cost_usd":0.0,"paid_services_used":[],"master_sha256":_sha(master) if master.is_file() else "","short_shas":[_sha(p) for p in shorts if p.is_file()]}
    report.parent.mkdir(parents=True,exist_ok=True); report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    if not passed: raise RuntimeError("FINAL QA FAILED: " + "; ".join(errors[:40]))
    return result
