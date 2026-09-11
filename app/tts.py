from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import edge_tts

from .core import RUN, Story

VOICE = "ar-SA-HamedNeural"
BASE_RATE = 0
MAX_SLOWDOWN = -20
MAX_SPEEDUP = 20
TIMING_TOLERANCE = 1.0
DURATION_PADDING = 0.5
SHORT_TARGET = 58.0
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))


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


def _speed_for_target(actual: float, target: float) -> int:
    """Return a bounded positive speech rate for a hard Shorts duration ceiling."""
    if actual <= 0 or target <= 0 or actual <= target:
        return BASE_RATE
    speedup = (actual / target - 1.0) * 100.0
    return max(BASE_RATE, min(MAX_SPEEDUP, int(round(speedup))))


def _regenerate_scene(story: Story, scene_id: int, out_dir: Path, rate: int) -> float:
    scene = next(s for s in story.scenes if s.id == scene_id)
    target = out_dir / f"scene_{scene.id:02d}.mp3"
    asyncio.run(_make(scene.narration, target, rate))
    return media_duration(target)


def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    """Generate audio, adapt individual scenes, and enforce Shorts ceilings."""
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}

    for s in story.scenes:
        target = out_dir / f"scene_{s.id:02d}.mp3"
        asyncio.run(_make(s.narration, target, BASE_RATE))
        actual = media_duration(target)

        if actual > float(s.duration) + TIMING_TOLERANCE:
            rate = _rate_for_target(actual, float(s.duration))
            if rate < BASE_RATE:
                actual = _regenerate_scene(story, s.id, out_dir, rate)
            if actual > float(s.duration) + TIMING_TOLERANCE and rate > MAX_SLOWDOWN:
                actual = _regenerate_scene(story, s.id, out_dir, MAX_SLOWDOWN)

        durations[s.id] = actual

    # Shorts are rendered from fixed scene pairs. If a pair is too long,
    # accelerate only those source scenes before the final timing contract.
    for group in SHORT_GROUPS:
        pair_total = sum(durations.get(i, 0.0) for i in group)
        if pair_total > SHORT_TARGET:
            speed = _speed_for_target(pair_total, SHORT_TARGET)
            if speed > BASE_RATE:
                for scene_id in group:
                    durations[scene_id] = _regenerate_scene(story, scene_id, out_dir, speed)
            pair_total = sum(durations.get(i, 0.0) for i in group)
            if pair_total > SHORT_TARGET + TIMING_TOLERANCE:
                raise RuntimeError(
                    f"TTS SHORT TIMING FAILED: source scenes {group} total {pair_total:.2f}s "
                    f"after maximum {MAX_SPEEDUP}% speedup"
                )

    return durations


def synchronize_scene_durations(story: Story, durations: dict[int, float]) -> None:
    """Make the generated audio the timing authority without shrinking planned scenes."""
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0.0))
        if actual <= 0:
            raise RuntimeError(f"TTS TIMING FAILED: scene {scene.id} has no usable audio duration")
        scene.duration = max(float(scene.duration), actual + DURATION_PADDING)


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
