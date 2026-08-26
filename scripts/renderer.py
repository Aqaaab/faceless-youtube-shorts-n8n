from __future__ import annotations
import shutil, subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required")


def render_placeholder(path: Path, seconds: int, vertical: bool = False) -> None:
    require_ffmpeg()
    size = "1080x1920" if vertical else "1920x1080"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={size}:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
