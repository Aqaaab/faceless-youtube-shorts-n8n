#!/usr/bin/env python3
"""Generate a validated job.json with OpenRouter primary and Gemini fallback."""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

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
        "hook": {"type": "string"}, "script": {"type": "string"},
        "subtitle_ar": {"type": "string"}, "title": {"type": "string"},
        "description": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
        "query": {"type": "string"}, "topic": {"type": "string"}, "category": {"type": "string"},
        "scenes": {"type": "array", "minItems": 5, "maxItems": 5, "items": {
            "type": "object", "properties": {
                "text_en": {"type": "string"}, "text_ar": {"type": "string"}, "pexels_query": {"type": "string"}
            }, "required": ["text_en", "text_ar", "pexels_query"]
        }}
    },
    "required": ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
}


def request_openrouter() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Include every required field and exactly 5 scenes."},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.55,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
                 "X-Title": "YouTube Shorts Automation"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def request_gemini() -> dict:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()
    body = {
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0.55, "maxOutputTokens": 3000,
                             "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def extract_openrouter(result: dict) -> dict:
    choices = result.get("choices") or []
    text = str(((choices[0].get("message") or {}).get("content") or "")).strip() if choices else ""
    if not text:
        raise RuntimeError("OpenRouter returned empty content")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def extract_gemini(result: dict) -> dict:
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(p.get("text", "")) for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def validate(data: dict) -> None:
    required = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")
    scenes = data["scenes"]
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Expected exactly 5 scenes")
    script = str(data["script"]).strip()
    joined = " ".join(str(s.get("text_en", "")).strip() for s in scenes).strip()
    if not 85 <= words(script) <= 95:
        raise ValueError(f"English script has {words(script)} words; expected 85-95")
    if script != joined:
        raise ValueError("script must equal the scenes' English narration joined with spaces")
    if str(data["hook"]).strip() != str(scenes[0].get("text_en", "")).strip():
        raise ValueError("hook must equal the first scene English narration")
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("subtitle_ar must contain Arabic text")
    for i, scene in enumerate(scenes, 1):
        for key in ("text_en", "text_ar", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"Scene {i} missing {key}")
        count = words(scene["text_en"])
        if not 14 <= count <= 22:
            raise ValueError(f"Scene {i} English text length is invalid: {count}")
        if re.search(r"[\u0600-\u06ff]", scene["text_en"]):
            raise ValueError(f"Scene {i} English text contains Arabic")
        if not 1 <= len(scene["pexels_query"].split()) <= 3:
            raise ValueError(f"Scene {i} Pexels query must contain 1-3 words")
    title = str(data["title"]).strip()
    if len(title) > 90 or not title.endswith("#Shorts"):
        raise ValueError("Title must be <=90 characters and end with #Shorts")
    tags = data["tags"]
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    for tag in tags:
        if not re.fullmatch(r"[a-z0-9_-]+", str(tag).strip().lower()):
            raise ValueError(f"Invalid tag: {tag}")
    metadata = "".join(str(data[k]) for k in ("title", "description", "query", "topic", "category"))
    if re.search(r"[\u0600-\u06ff]", metadata):
        raise ValueError("Metadata contains Arabic outside subtitles")


def finalize(data: dict) -> None:
    data["voice"] = os.environ.get("VOICE", "af_bella")
    data["speed"] = float(os.environ.get("SPEED", "1.0"))
    data["lang"] = os.environ.get("KOKORO_LANG", "en-us")
    data["music"] = os.environ.get("MUSIC_ENABLED", "true").lower() == "true"
    data["music_volume"] = float(os.environ.get("MUSIC_VOLUME", "0.10"))
    data["animation"] = os.environ.get("ANIMATION_ENABLED", "true").lower() == "true"
    data["ads"] = False
    data["narration"] = data["script"]
    data["pexels_query"] = data["scenes"][0]["pexels_query"]
    (RUN_DIR / "job.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def try_provider(name, request_fn, extract_fn, attempts: int) -> bool:
    for attempt in range(1, attempts + 1):
        print(f"AI provider={name} attempt={attempt}/{attempts}")
        try:
            data = extract_fn(request_fn())
            validate(data)
            finalize(data)
            print(f"AI provider={name} succeeded")
            return True
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"{name} HTTP {exc.code}: {detail[:1000]}")
            if exc.code == 429:
                print(f"{name} quota/rate limit; switching to next provider")
                return False
            if exc.code not in {500, 502, 503, 504}:
                return False
        except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
            print(f"Invalid {name} response: {exc!r}")
        if attempt < attempts:
            time.sleep(min(4 * attempt + random.uniform(0, 2), 12))
    return False


def main() -> None:
    if try_provider("OpenRouter", request_openrouter, extract_openrouter, 3):
        return
    print("OpenRouter unavailable; switching to Gemini fallback.")
    if try_provider("Gemini", request_gemini, extract_gemini, 2):
        return
    raise SystemExit("All configured AI providers failed. No job.json was produced.")


if __name__ == "__main__":
    main()
