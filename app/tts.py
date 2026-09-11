from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

import edge_tts

from .core import RUN, Story

VOICE = "ar-SA-HamedNeural"
BASE_RATE = 0
MIN_WPS = 1.60
TARGET_WPS = 1.85
MAX_WPS = 2.10
MAX_SLOWDOWN = -12
MAX_SPEEDUP = 45
TIMING_TOLERANCE = 0.75
DURATION_PADDING = 0.35
SHORT_TARGET = 58.0
SHORT_MIN = 28.0
SHORT_SCENE_MIN = 13.75
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


async def _make(text: str, mp3: Path, rate_percent: int = BASE_RATE):
    rate = f"{rate_percent:+d}%"
    await edge_tts.Communicate(text, VOICE, rate=rate, volume="+0%").save(str(mp3))


def _rate_for_pacing(actual: float, words: int) -> int:
    if actual <= 0 or words <= 0:
        return BASE_RATE
    wps = words / actual
    if MIN_WPS <= wps <= MAX_WPS:
        return BASE_RATE
    desired_duration = words / TARGET_WPS
    rate = int(round((actual / desired_duration - 1.0) * 100.0))
    return max(MAX_SLOWDOWN, min(MAX_SPEEDUP, rate))


def _regenerate_scene(story: Story, scene_id: int, out_dir: Path, rate: int) -> float:
    scene = next(s for s in story.scenes if s.id == scene_id)
    target = out_dir / f"scene_{scene.id:02d}.mp3"
    asyncio.run(_make(scene.narration, target, rate))
    return media_duration(target)


def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    """Generate TTS and actively enforce automotive-YouTube narration pacing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}

    for scene in story.scenes:
        target = out_dir / f"scene_{scene.id:02d}.mp3"
        words = _words(scene.narration)
        asyncio.run(_make(scene.narration, target, BASE_RATE))
        actual = media_duration(target)
        rate = _rate_for_pacing(actual, words)
        if rate != BASE_RATE:
            actual = _regenerate_scene(story, scene.id, out_dir, rate)
            # One bounded correction pass handles provider rate quantization.
            wps = words / actual if actual > 0 else 0
            if wps < MIN_WPS or wps > MAX_WPS:
                correction = _rate_for_pacing(actual, words)
                if correction != rate:
                    actual = _regenerate_scene(story, scene.id, out_dir, correction)

        final_wps = words / actual if actual > 0 else 0
        if final_wps < MIN_WPS or final_wps > MAX_WPS:
            raise RuntimeError(
                f"TTS PACING FAILED: scene {scene.id} measured {final_wps:.2f} words/s; "
                f"required {MIN_WPS:.2f}-{MAX_WPS:.2f}"
            )
        durations[scene.id] = actual

    return durations


def synchronize_scene_durations(story: Story, durations: dict[int, float]) -> None:
    """Make measured TTS authoritative instead of preserving slow provisional scene durations."""
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0.0))
        if actual <= 0:
            raise RuntimeError(f"TTS TIMING FAILED: scene {scene.id} has no usable audio duration")
        floor = SHORT_SCENE_MIN if scene.id in {i for g in SHORT_GROUPS for i in g} else 0.0
        scene.duration = max(actual + DURATION_PADDING, floor)


def media_duration(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(p.stdout.strip())


def validate_tts_timing(story: Story, durations: dict[int, float], tolerance: float = TIMING_TOLERANCE) -> None:
    errors = []
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0))
        planned = float(scene.duration)
        words = _words(scene.narration)
        if actual <= 0:
            errors.append(f"scene {scene.id} TTS duration missing")
            continue
        wps = words / actual
        if wps < MIN_WPS or wps > MAX_WPS:
            errors.append(f"scene {scene.id} TTS pacing {wps:.2f} words/s outside {MIN_WPS:.2f}-{MAX_WPS:.2f}")
        if actual > planned + tolerance:
            errors.append(f"scene {scene.id} TTS {actual:.2f}s exceeds planned {planned:.2f}s")
    if errors:
        raise RuntimeError("TTS TIMING/PACING FAILED: " + "; ".join(errors))
