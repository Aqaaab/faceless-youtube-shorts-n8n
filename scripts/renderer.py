from __future__ import annotations
import json, os, shutil, subprocess, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RUN.mkdir(parents=True, exist_ok=True)
VOICE = os.getenv("VOICE", "en-US-GuyNeural")


def shell(*cmd: str) -> None:
    subprocess.run(cmd, check=True)


def download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "faceless-youtube-shorts-n8n/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        dst.write_bytes(response.read())


def pexels(query: str) -> str:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is required for real rendering")
    q = urllib.parse.quote(query)
    url = f"https://api.pexels.com/videos/search?query={q}&per_page=5&orientation=landscape"
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "faceless-youtube-shorts-n8n/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    candidates = []
    for video in data.get("videos", []):
        for item in video.get("video_files", []):
            link = item.get("link")
            width, height = int(item.get("width") or 0), int(item.get("height") or 0)
            if link:
                candidates.append((width * height, link))
    if not candidates:
        raise RuntimeError(f"No Pexels video found for query: {query}")
    return max(candidates, key=lambda x: x[0])[1]


def make_segment(sc: dict, index: int, work: Path) -> Path:
    clip = work / f"{index:02d}.mp4"
    audio = work / f"{index:02d}.mp3"
    seg = work / f"{index:02d}-seg.mp4"
    download(pexels(sc["pexels_query"]), clip)
    shell("edge-tts", "--voice", VOICE, "--text", sc["text_en"], "--write-media", str(audio))
    shell(
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip), "-i", str(audio), "-shortest",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-r", "30", str(seg),
    )
    return seg


def concat_segments(paths: list[Path], output: Path, work: Path) -> None:
    manifest = work / f"{output.stem}-concat.txt"
    manifest.write_text("".join(f"file '{p.as_posix()}'\n" for p in paths), encoding="utf-8")
    shell("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(output))


def main() -> None:
    source = RUN / "long_story.json"
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
            selected = segments[start - 1:end]
            if not selected:
                raise ValueError(f"short {sid} has no scenes")
            source_short = work / f"short-{sid}-source.mp4"
            concat_segments(selected, source_short, work)
            out = shorts_dir / f"short-{sid}.mp4"
            # Keep every short in the Shorts duration contract while preserving its
            # multi-scene excerpt. 45s gives a stable target inside 28-59s.
            shell(
                "ffmpeg", "-y", "-i", str(source_short), "-t", "45",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-r", "30", str(out),
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("REAL_RENDER=PASS")


if __name__ == "__main__":
    main()
