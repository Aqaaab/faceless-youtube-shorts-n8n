#!/usr/bin/env python3
"""Generate a validated job.json for the Shorts renderer."""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API_KEY = os.environ["GEMINI_API_KEY"].strip()
RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

configured = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
MODELS = []
for model in [configured, "gemini-3.6-flash"]:
    if model and model not in MODELS:
        MODELS.append(model)

PROMPT = """
Create one accurate and surprising YouTube Shorts 'Did You Know?' story.
Return ONLY valid JSON matching the supplied schema.
The story must contain exactly 5 scenes and the complete English narration must be 85-95 words.
Each scene must contain 14-22 English words and a complete Modern Standard Arabic translation.
Use one verifiable fact only. Do not invent statistics, dates, scientific claims, or quotations.
The first scene must be a strong curiosity hook. The last scene must end with a short question or follow-for-more line.
Each scene needs a simple Pexels search query of 1-3 English words.
Title: English only, <=90 characters, ending in #Shorts.
Description: 2-3 English sentences and then exactly 5 hashtags.
Tags: 8-12 lowercase English keywords.
No emojis. No Arabic outside subtitle_ar.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "script": {"type": "string"},
        "subtitle_ar": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "query": {"type": "string"},
        "topic": {"type": "string"},
        "category": {"type": "string"},
        "scenes": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "text_en": {"type": "string"},
                    "text_ar": {"type": "string"},
                    "pexels_query": {"type": "string"},
                },
                "required": ["text_en", "text_ar", "pexels_query"],
            },
        },
    },
    "required": [
        "hook", "script", "subtitle_ar", "title", "description", "tags",
        "query", "topic", "category", "scenes",
    ],
}


def request(model: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "temperature": 0.55,
            "maxOutputTokens": 3000,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def extract_json(result: dict) -> dict:
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(p.get("text", "")) for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("Gemini response is not a JSON object")
    return value


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def validate(data: dict) -> None:
    required = [
        "hook", "script", "subtitle_ar", "title", "description", "tags",
        "query", "topic", "category", "scenes",
    ]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")

    scenes = data["scenes"]
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Expected exactly 5 scenes")

    script = str(data["script"]).strip()
    joined_script = " ".join(str(scene.get("text_en", "")).strip() for scene in scenes).strip()
    script_words = words(script)
    if not 85 <= script_words <= 95:
        raise ValueError(f"English script has {script_words} words; expected 85-95")
    if script != joined_script:
        raise ValueError("script must exactly equal the scenes' English narration joined with spaces")
    if str(data["hook"]).strip() != str(scenes[0]["text_en"]).strip():
        raise ValueError("hook must exactly equal the first scene English narration")
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("subtitle_ar must contain Arabic text")

    scene_words = 0
    for i, scene in enumerate(scenes, 1):
        for key in ("text_en", "text_ar", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"Scene {i} missing {key}")
        count = words(scene["text_en"])
        scene_words += count
        if not 10 <= count <= 25:
            raise ValueError(f"Scene {i} English text length is invalid: {count}")
        if re.search(r"[\u0600-\u06ff]", scene["text_en"]):
            raise ValueError(f"Scene {i} English text contains Arabic")
        query_words = scene["pexels_query"].split()
        if not 1 <= len(query_words) <= 3:
            raise ValueError(f"Scene {i} Pexels query must contain 1-3 words")

    if not 70 <= scene_words <= 115:
        raise ValueError(f"Scene narration has {scene_words} words; expected 70-115")

    title = str(data["title"]).strip()
    if len(title) > 90:
        raise ValueError("Title exceeds 90 characters")
    if not title.endswith("#Shorts"):
        raise ValueError("Title must end with #Shorts")

    tags = data["tags"]
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    for tag in tags:
        if not re.fullmatch(r"[a-z0-9_-]+", str(tag).strip().lower()):
            raise ValueError(f"Invalid tag: {tag}")

    metadata = "".join(str(data[key]) for key in ("title", "description", "query", "topic", "category"))
    if re.search(r"[\u0600-\u06ff]", metadata):
        raise ValueError("Metadata contains Arabic outside subtitles")


def main() -> None:
    last_error: Exception | None = None
    data = None

    for model in MODELS:
        for attempt in range(1, 5):
            print(f"Gemini model={model} attempt={attempt}/4")
            try:
                candidate = extract_json(request(model))
                validate(candidate)
                data = candidate
                print("Gemini generation and validation succeeded.")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Gemini HTTP {exc.code}: {detail[:1200]}")
                print(last_error)
                if exc.code == 404:
                    break
                if exc.code not in {429, 500, 502, 503, 504}:
                    raise
                time.sleep(min(8 * (2 ** (attempt - 1)) + random.uniform(0, 2), 45))
            except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
                last_error = exc
                print(f"Invalid Gemini response: {exc!r}")
                time.sleep(min(3 * attempt, 12))
        if data is not None:
            break

    if data is None:
        raise SystemExit(f"Generation failed: {last_error}")

    data["voice"] = os.environ.get("VOICE", "af_bella")
    data["speed"] = float(os.environ.get("SPEED", "1.0"))
    data["lang"] = os.environ.get("KOKORO_LANG", "en-us")
    data["music"] = os.environ.get("MUSIC_ENABLED", "true").lower() == "true"
    data["music_volume"] = float(os.environ.get("MUSIC_VOLUME", "0.10"))
    data["animation"] = os.environ.get("ANIMATION_ENABLED", "true").lower() == "true"
    data["ads"] = False
    data["narration"] = data["script"]
    data["pexels_query"] = data["scenes"][0]["pexels_query"]

    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
