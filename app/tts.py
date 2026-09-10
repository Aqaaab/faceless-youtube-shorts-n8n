from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
import edge_tts
from .core import RUN, Story

VOICE = "ar-SA-HamedNeural"

async def _make(text: str, mp3: Path):
    await edge_tts.Communicate(text, VOICE, rate="+0%", volume="+0%").save(str(mp3))

def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> dict[int, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: dict[int, float] = {}
    for s in story.scenes:
        target = out_dir / f"scene_{s.id:02d}.mp3"
        asyncio.run(_make(s.narration, target))
        durations[s.id] = media_duration(target)
    return durations

def media_duration(path: Path) -> float:
    p = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)], capture_output=True, text=True, check=True)
    return float(p.stdout.strip())

def validate_tts_timing(story: Story, durations: dict[int, float], tolerance: float = 1.0) -> None:
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
