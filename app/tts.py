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
MAX_SLOWDOWN = -20
MAX_SPEEDUP = 45
TIMING_TOLERANCE = 0.75
DURATION_PADDING = 0.35
SHORT_SCENE_TARGET = 14.0
SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


async def _make(text: str, mp3: Path, rate_percent: int = BASE_RATE) -> None:
    await edge_tts.Communicate(text, VOICE, rate=f"{rate_percent:+d}%", volume="+0%").save(str(mp3))


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _rate_for_pacing(actual: float, words: int, target_duration: float | None = None) -> int:
    if actual <= 0 or words <= 0:
        return BASE_RATE
    desired = target_duration if target_duration and target_duration > 0 else words / TARGET_WPS
    wps = words / actual
    if target_duration is None and MIN_WPS <= wps <= MAX_WPS:
        return BASE_RATE
    rate = int(round((actual / desired - 1.0) * 100.0))
    return max(MAX_SLOWDOWN, min(MAX_SPEEDUP, rate))


def _regenerate_scene(story: Story, scene_id: int, out_dir: Path, rate: int) -> float:
    scene = next(scene for scene in story.scenes if scene.id == scene_id)
    target = out_dir / f"scene_{scene.id:02d}.mp3"
    asyncio.run(_make(scene.narration, target, rate))
    return media_duration(target)


def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}
    short_ids = {scene_id for group in SHORT_GROUPS for scene_id in group}

    for scene in story.scenes:
        target = out_dir / f"scene_{scene.id:02d}.mp3"
        words = _words(scene.narration)
        asyncio.run(_make(scene.narration, target, BASE_RATE))
        actual = media_duration(target)

        for _ in range(4):
            wps = words / actual if actual > 0 else 0.0
            target_duration = SHORT_SCENE_TARGET if scene.id in short_ids else None
            needs_pacing = not MIN_WPS <= wps <= MAX_WPS
            needs_short_floor = target_duration is not None and actual < target_duration
            if not needs_pacing and not needs_short_floor:
                break
            rate = _rate_for_pacing(actual, words, target_duration if needs_short_floor else None)
            if rate == BASE_RATE and not needs_pacing:
                break
            new_actual = _regenerate_scene(story, scene.id, out_dir, rate)
            if abs(new_actual - actual) < 0.05:
                break
            actual = new_actual

        final_wps = words / actual if actual > 0 else 0.0
        if not MIN_WPS <= final_wps <= MAX_WPS:
            raise RuntimeError(f"TTS PACING FAILED: scene {scene.id} measured {final_wps:.2f} words/s; required {MIN_WPS:.2f}-{MAX_WPS:.2f}")
        if scene.id in short_ids and actual < SHORT_SCENE_TARGET:
            raise RuntimeError(f"SHORT TIMING FAILED: scene {scene.id} TTS duration {actual:.2f}s is below {SHORT_SCENE_TARGET:.2f}s; narration must be regenerated, not padded")
        durations[scene.id] = actual

    return durations


def synchronize_scene_durations(story: Story, durations: dict[int, float]) -> None:
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0.0))
        if actual <= 0:
            raise RuntimeError(f"TTS TIMING FAILED: scene {scene.id} has no usable audio duration")
        scene.duration = actual + DURATION_PADDING


def validate_tts_timing(story: Story, durations: dict[int, float], tolerance: float = TIMING_TOLERANCE) -> None:
    errors: list[str] = []
    for scene in story.scenes:
        actual = float(durations.get(scene.id, 0.0))
        planned = float(scene.duration)
        words = _words(scene.narration)
        if actual <= 0:
            errors.append(f"scene {scene.id} TTS duration missing")
            continue
        wps = words / actual if words else 0.0
        if not MIN_WPS <= wps <= MAX_WPS:
            errors.append(f"scene {scene.id} TTS pacing {wps:.2f} words/s outside {MIN_WPS:.2f}-{MAX_WPS:.2f}")
        if actual > planned + tolerance:
            errors.append(f"scene {scene.id} TTS duration {actual:.2f}s exceeds planned {planned:.2f}s")
        if actual < planned - (DURATION_PADDING + tolerance):
            errors.append(f"scene {scene.id} has unexplained timing slack of {planned - actual:.2f}s")
    if errors:
        raise RuntimeError("TTS TIMING FAILED: " + "; ".join(errors))
