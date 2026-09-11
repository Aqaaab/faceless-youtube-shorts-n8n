from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import edge_tts

from .core import RUN, Story

VOICE = "ar-SA-HamedNeural"
BASE_RATE = 0
MAX_SLOWDOWN = -20
TIMING_TOLERANCE = 1.0


async def _make(text: str, mp3: Path, rate_percent: int = BASE_RATE):
    rate = f"{rate_percent:+d}%"
    await edge_tts.Communicate(text, VOICE, rate=rate, volume="+0%").save(str(mp3))


def _rate_for_target(actual: float, planned: float) -> int:
    """Return a bounded negative speech rate that should fit the planned scene."""
    if actual <= 0 or planned <= 0:
        return BASE_RATE
    target = max(planned + TIMING_TOLERANCE - 0.05, 0.05)
    slowdown = (target / actual - 1.0) * 100.0
    return max(MAX_SLOWDOWN, min(BASE_RATE, int(round(slowdown))))


def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}
    for s in story.scenes:
        target = out_dir / f"scene_{s.id:02d}.mp3"
        asyncio.run(_make(s.narration, target, BASE_RATE))
        actual = media_duration(target)

        # Regenerate only an overlong scene at an adaptive bounded rate so
        # render.py never has to truncate narration.
        if actual > float(s.duration) + TIMING_TOLERANCE:
            rate = _rate_for_target(actual, float(s.duration))
            if rate < BASE_RATE:
                asyncio.run(_make(s.narration, target, rate))
                actual = media_duration(target)
            if actual > float(s.duration) + TIMING_TOLERANCE and rate > MAX_SLOWDOWN:
                asyncio.run(_make(s.narration, target, MAX_SLOWDOWN))
                actual = media_duration(target)

        durations[s.id] = actual
    return durations


def media_duration(path: Path) -> float:
    p = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(p.stdout.strip())


def validate_tts_timing(story: Story, durations: dict[int, float], tolerance: float = TIMING_TOLERANCE) -> None:
    errors = []
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0))
        planned = float(scene.duration)
        if actual <= 0:
            errors.append(f"scene {scene.id} TTS duration missing")
        elif actual > planned + tolerance:
            errors.append(f"scene {scene.id} TTS {actual:.2f}s exceeds planned {planned:.2f}s by more than {tolerance:.1f}s")
        elif actual < planned - 12.0:
            errors.append(f"scene {scene.id} planned duration {planned:.2f}s is more than 12s longer than TTS {actual:.2f}s")
    if errors:
        raise RuntimeError("TTS TIMING FAILED: " + "; ".join(errors))
