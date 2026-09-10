import asyncio, subprocess
from pathlib import Path
import edge_tts
from .core import RUN, Story

VOICE = "ar-SA-HamedNeural"

async def _make(text: str, mp3: Path):
    await edge_tts.Communicate(text, VOICE, rate="+0%", volume="+0%").save(str(mp3))

def generate_tts(story: Story, out_dir: Path = RUN / "audio") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for s in story.scenes:
        asyncio.run(_make(s.narration, out_dir / f"scene_{s.id:02d}.mp3"))

def media_duration(path: Path) -> float:
    p = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)], capture_output=True, text=True, check=True)
    return float(p.stdout.strip())
