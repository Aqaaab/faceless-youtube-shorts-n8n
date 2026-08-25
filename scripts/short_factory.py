#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/daily-production"))
PLAN = RUN_DIR / "viral_plan.json"
SOURCE = RUN_DIR / "video.mp4"
OUT_DIR = RUN_DIR / "shorts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def main() -> None:
    if not SOURCE.is_file(): raise SystemExit("LONG_SOURCE_MISSING")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4: raise SystemExit(f"EXPECTED_4_SHORTS_GOT_{len(shorts)}")
    duration = probe_duration(SOURCE)
    manifest = []
    starts = set()
    for n, item in enumerate(shorts, 1):
        start_scene = int(item.get("scene_start", 0))
        end_scene = int(item.get("scene_end", start_scene))
        if start_scene in starts: raise SystemExit("DUPLICATE_SHORT_SOURCE_START")
        starts.add(start_scene)
        # Scene duration is supplied by the story contract when available; use a conservative
        # fallback window so the factory remains deterministic and never requests beyond EOF.
        start = max(0.0, float(item.get("source_start_seconds", max(0, (start_scene - 1) * 8))))
        end = float(item.get("source_end_seconds", min(duration, max(start + 12, end_scene * 8))))
        end = min(duration, end)
        if end <= start + 2: raise SystemExit(f"SHORT_{n}_WINDOW_INVALID")
        out = OUT_DIR / f"short-{n}.mp4"
        cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(SOURCE), "-t", f"{end-start:.3f}", "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
        if not out.is_file() or out.stat().st_size < 10000: raise SystemExit(f"SHORT_{n}_RENDER_FAILED")
        manifest.append({"short_number": n, "path": str(out), "source_start": start, "source_end": end, "scene_start": start_scene, "scene_end": end_scene, "title": item.get("title", ""), "description": item.get("description", ""), "score": item.get("score", 0), "status": "rendered"})
    (RUN_DIR / "short_factory_manifest.json").write_text(json.dumps({"schema_version":"1.0","count":4,"source":str(SOURCE),"shorts":manifest}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("SHORT_FACTORY=PASS")

if __name__ == "__main__": main()
