from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path

import edge_tts

from .cache import restore_file, stable_key, store_file
from .core import RUN, Story
from .retry import retry_async

VOICE = "ar-SA-HamedNeural"
BASE_RATE = 0
MIN_WPS = 1.60
TARGET_WPS = 1.85
MAX_WPS = 2.10
MAX_SLOWDOWN = -20
MAX_SPEEDUP = 45
TIMING_TOLERANCE = 0.75
DURATION_PADDING = 0.35


def _words(text: str) -> int:
    return len(re.findall(r"\S+", str(text).strip()))


async def _make(text: str, mp3: Path, words_path: Path, rate_percent: int = BASE_RATE) -> None:
    communicate = edge_tts.Communicate(
        text,
        VOICE,
        rate=f"{rate_percent:+d}%",
        volume="+0%",
        boundary="WordBoundary",
    )
    boundaries: list[dict] = []
    with mp3.open("wb") as handle:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                handle.write(chunk["data"])
            elif kind == "WordBoundary":
                try:
                    boundaries.append(
                        {
                            "offset": int(chunk["offset"]),
                            "duration": int(chunk["duration"]),
                            "text": str(chunk.get("text", "")),
                            "start": float(chunk["offset"]) / 10_000_000.0,
                            "end": float(chunk["offset"] + chunk["duration"]) / 10_000_000.0,
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    continue
    if not boundaries:
        raise RuntimeError("TTS WORD TIMING FAILED: Edge TTS returned no WordBoundary events")
    words_path.write_text(json.dumps({"voice": VOICE, "rate": rate_percent, "words": boundaries}, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _cache_key(text: str, rate: int) -> str:
    return stable_key("tts-v2-word-boundary", VOICE, rate, text)


def _materialize_cached(text: str, mp3: Path, words_path: Path, rate: int) -> bool:
    key = _cache_key(text, rate)
    return restore_file("tts", key, ".mp3", mp3) and restore_file("tts", key, ".json", words_path)


def _store_cached(text: str, mp3: Path, words_path: Path, rate: int) -> None:
    key = _cache_key(text, rate)
    store_file("tts", key, ".mp3", mp3)
    store_file("tts", key, ".json", words_path)


def _make_sync(text: str, mp3: Path, words_path: Path, rate: int) -> None:
    if _materialize_cached(text, mp3, words_path, rate):
        return
    mp3.parent.mkdir(parents=True, exist_ok=True)
    async def generate():
        await _make(text, mp3, words_path, rate)
    retry_count = int(os.getenv("TTS_RETRY_ATTEMPTS", "3"))
    retry_async_call = retry_async(
        generate,
        attempts=max(1, retry_count),
        base_delay=1.5,
        label=f"TTS generation ({mp3.name})",
    )
    try:
        asyncio.run(retry_async_call)
    except Exception:
        mp3.unlink(missing_ok=True)
        words_path.unlink(missing_ok=True)
        raise
    _store_cached(text, mp3, words_path, rate)


def _regenerate_scene(story: Story, scene_id: int, out_dir: Path, rate: int) -> float:
    scene = next(scene for scene in story.scenes if scene.id == scene_id)
    target = out_dir / f"scene_{scene.id:02d}.mp3"
    words_path = out_dir / f"scene_{scene.id:02d}.words.json"
    _make_sync(scene.narration, target, words_path, rate)
    return media_duration(target)


def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}
    for scene in story.scenes:
        target = out_dir / f"scene_{scene.id:02d}.mp3"
        words_path = out_dir / f"scene_{scene.id:02d}.words.json"
        words = _words(scene.narration)
        _make_sync(scene.narration, target, words_path, BASE_RATE)
        actual = media_duration(target)
        for _ in range(4):
            wps = words / actual if actual > 0 else 0.0
            needs_pacing = not MIN_WPS <= wps <= MAX_WPS
            if not needs_pacing:
                break
            rate = _rate_for_pacing(actual, words)
            new_actual = _regenerate_scene(story, scene.id, out_dir, rate)
            if abs(new_actual - actual) < 0.05:
                break
            actual = new_actual
        final_wps = words / actual if actual > 0 else 0.0
        if not MIN_WPS <= final_wps <= MAX_WPS:
            raise RuntimeError(
                f"TTS PACING FAILED: scene {scene.id} measured {final_wps:.2f} words/s; required {MIN_WPS:.2f}-{MAX_WPS:.2f}"
            )
        data = json.loads(words_path.read_text(encoding="utf-8"))
        if not data.get("words"):
            raise RuntimeError(f"TTS WORD TIMING FAILED: scene {scene.id} has no word timings")
        durations[scene.id] = actual
    return durations


def load_word_timings(scene_id: int, out_dir: Path = RUN / "audio") -> list[dict]:
    path = out_dir / f"scene_{scene_id:02d}.words.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    words = data.get("words")
    if not isinstance(words, list) or not words:
        raise RuntimeError(f"TTS WORD TIMING FAILED: invalid timing file {path}")
    return words


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
        try:
            word_timings = load_word_timings(scene.id)
            if word_timings[-1]["end"] > actual + 0.50:
                errors.append(f"scene {scene.id} word timing exceeds audio duration")
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            errors.append(f"scene {scene.id} word timing missing: {exc}")
    if errors:
        raise RuntimeError("TTS TIMING FAILED: " + "; ".join(errors))
