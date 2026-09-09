from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    output_dir: str = "data/runs"
    pexels_api_key: str | None = os.getenv("PEXELS_API_KEY")
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or os.getenv("YOUTUBE_LLM_BASE_URL")
    tts_provider: str = os.getenv("TTS_PROVIDER", "edge")
    media_provider: str = os.getenv("MEDIA_PROVIDER", "pexels")
    visual_provider: str = os.getenv("VISUAL_PROVIDER", "svg")

    def require(self, *names: str) -> None:
        missing = [name for name in names if not getattr(self, name, None)]
        if missing:
            raise RuntimeError("Missing required configuration: " + ", ".join(missing))
