from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RUN.mkdir(parents=True, exist_ok=True)
VOICE = os.getenv("VOICE", "en-US-GuyNeural").strip() or "en-US-GuyNeural"
RETRIES = max(1, int(os.getenv("MEDIA_RETRIES", "3")))
CMD_TIMEOUT = max(30, int(os.getenv("MEDIA_COMMAND_TIMEOUT", "300")))
DOWNLOAD_TIMEOUT = max(15, int(os.getenv("MEDIA_DOWNLOAD_TIMEOUT", "90")))
PEXELS_TIMEOUT = max(10, int(os.getenv("PEXELS_TIMEOUT", "45")))


def shell(*cmd: str, timeout: int = CMD_TIMEOUT) -> None:
    subprocess.run(cmd, check=True, timeout=timeout)


def shell_retry(*cmd: str, timeout: int = CMD_TIMEOUT) -> None:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            shell(*cmd, timeout=timeout)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"command failed after {RETRIES} attempts: {' '.join(cmd)}") from last


def download(url: str, dst: Path) -> None:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "faceless-youtube-shorts-n8n/1.0"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
                data = response.read()
            if not data:
                raise RuntimeError("download returned an empty file")
            dst.write_bytes(data)
            return
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"media download failed: {url}") from last


def pexels(query: str) -> str:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is required for real rendering")
    q = urllib.parse.quote(query.strip())
    if not q:
        raise RuntimeError("Pexels query is empty")
    url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=landscape"
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "faceless-youtube-shorts-n8n/1.0"})
            with urllib.request.urlopen(req, timeout=PEXELS_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            candidates = []
            for video in data.get("videos", []):
                for item in video.get("video_files", []):
                    link = item.get("link")
                    width = int(item.get("width") or 0)
                    height = int(item.get("height") or 0)
                    if link and width > 0 and height > 0:
                        candidates.append((width * height, link))
            if candidates:
                return max(candidates, key=lambda x: x[0])[1]
            raise RuntimeError(f"No Pexels video found for query: {query}")
        except urllib.error.HTTPError as exc:
            last = RuntimeError(f"Pexels HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}")
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
        if attempt + 1 < RETRIES:
            time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"Pexels lookup failed for query: {query}") from last


def make_segment(sc: dict, index: int, work: Path) -> Path:
    clip = work / f"{index:02d}.mp4"
    audio = work / f"{index:02d}.mp3"
    seg = work / f"{index:02d}-seg.mp4"
    download(pexels(sc["pexels_query"]), clip)
    shell_retry("edge-tts", "--voice", VOICE, "--text", sc["text_en"], "--write-media", str(audio), timeout=120)
    shell_retry(
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip), "-i", str(audio), "-shortest",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-r", "30", str(seg),
        timeout=180,
    )
    if not seg.is_file() or seg.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg produced an empty segment: {index}")
    return seg


def concat_segments(paths: list[Path], output: Path, work: Path) -> None:
    if not paths or any(not p.is_file() for p in paths):
        raise RuntimeError("concat received missing media segments")
    manifest = work / f"{output.stem}-concat.txt"
    manifest.write_text("".join(f"file '{p.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for p in paths), encoding="utf-8")
    shell_retry("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(output), timeout=300)
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg concat produced an empty file: {output.name}")


def main() -> None:
    source = RUN / "long_story.json"
    if not source.is_file():
        raise FileNotFoundError(f"missing story: {source}")
    story = json.loads(source.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("renderer requires exactly 25 scenes")

    plan_path = RUN / "shorts_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError("shorts_plan.json is required before rendering")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    shorts = plan.get("shorts", [])
    if len(shorts) != 4:
        raise ValueError("shorts plan must contain exactly 4 shorts")

    work = RUN / "render"
    work.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    try:
        for index, scene in enumerate(scenes, 1):
            segments.append(make_segment(scene, index, work))
        concat_segments(segments, RUN / "video.mp4", work)
        shorts_dir = RUN / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)
        for short in shorts:
            sid = int(short["id"])
            start = int(short["scene_start"])
            end = int(short["scene_end"])
            if not (1 <= start <= end <= len(segments)):
                raise ValueError(f"short {sid} scene range is invalid: {start}-{end}")
            selected = segments[start - 1 : end]
            source_short = work / f"short-{sid}-source.mp4"
            concat_segments(selected, source_short, work)
            out = shorts_dir / f"short-{sid}.mp4"
            shell_retry(
                "ffmpeg", "-y", "-i", str(source_short), "-t", "45",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-r", "30", str(out),
                timeout=300,
            )
            if not out.is_file() or out.stat().st_size == 0:
                raise RuntimeError(f"Short {sid} render is empty")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("REAL_RENDER=PASS")


if __name__ == "__main__":
    main()
