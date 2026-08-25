#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/daily-production"))
PLAN = RUN_DIR / "viral_plan.json"
STORY = RUN_DIR / "long_story.json"
SOURCE = RUN_DIR / "video.mp4"
OUT_DIR = RUN_DIR / "shorts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", text))

def main() -> None:
    if not SOURCE.is_file(): raise SystemExit("LONG_SOURCE_MISSING")
    if not PLAN.is_file() or not STORY.is_file(): raise SystemExit("SHORT_FACTORY_INPUT_MISSING")
    plan = json.loads(PLAN.read_text(encoding="utf-8")); story = json.loads(STORY.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", []); scenes = story.get("scenes", [])
    if len(shorts) != 4: raise SystemExit(f"EXPECTED_4_SHORTS_GOT_{len(shorts)}")
    if not scenes: raise SystemExit("STORY_SCENES_MISSING")
    total_duration = duration(SOURCE)
    total_words = max(1, sum(words(s.get("text_en", "")) for s in scenes))
    cumulative = [0]
    for s in scenes: cumulative.append(cumulative[-1] + words(s.get("text_en", "")))
    starts = set(); manifest = []
    for n, item in enumerate(shorts, 1):
        ss = int(item.get("scene_start", 0)); ee = int(item.get("scene_end", ss))
        if not 1 <= ss <= len(scenes): raise SystemExit(f"SHORT_{n}_SCENE_START_INVALID")
        ee = max(ss, min(ee, len(scenes)))
        if ss in starts: raise SystemExit("DUPLICATE_SHORT_SOURCE_START")
        starts.add(ss)
        start = total_duration * cumulative[ss - 1] / total_words
        end = total_duration * cumulative[ee] / total_words
        if end - start < 3: end = min(total_duration, start + 12)
        if end <= start + 2: raise SystemExit(f"SHORT_{n}_WINDOW_INVALID")
        out = OUT_DIR / f"short-{n}.mp4"
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(SOURCE), "-t", f"{end-start:.3f}", "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
        if not out.is_file() or out.stat().st_size < 10000: raise SystemExit(f"SHORT_{n}_RENDER_FAILED")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(out)], capture_output=True, text=True, check=True)
        streams = json.loads(probe.stdout).get("streams", [])
        video = next((x for x in streams if x.get("codec_type") == "video"), None)
        if not video or video.get("width") != 1080 or video.get("height") != 1920: raise SystemExit(f"SHORT_{n}_FORMAT_INVALID")
        manifest.append({"short_number": n, "path": str(out), "source_start": round(start, 3), "source_end": round(end, 3), "scene_start": ss, "scene_end": ee, "title": item.get("title", ""), "description": item.get("description", ""), "score": item.get("score", 0), "status": "rendered"})
    if len({x["scene_start"] for x in manifest}) != 4: raise SystemExit("SHORT_DIVERSITY_GATE_FAILED")
    (RUN_DIR / "short_factory_manifest.json").write_text(json.dumps({"schema_version":"1.1","count":4,"source":str(SOURCE),"shorts":manifest}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("SHORT_FACTORY=PASS")

if __name__ == "__main__": main()
