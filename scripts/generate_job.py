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
Return ONLY one JSON object. Do not use Markdown fences, commentary, or explanations.
The JSON must contain exactly 5 scenes. Each scene must have text_en, text_ar, and pexels_query.
The complete English narration must be 85-95 words; each scene's English text must be 14-22 words.
Use one verifiable fact only. Do not invent statistics, dates, scientific claims, or quotations.
The first scene should be a strong curiosity hook. The last scene should end with a short question or follow-for-more line.
Each pexels_query must contain 1-3 English words.
Title: English only, <=90 characters, ending in #Shorts.
Description: 2-3 English sentences and then exactly 5 hashtags.
Tags: 8-12 lowercase English keywords.
Metadata must be English only. Arabic is allowed only in text_ar/subtitle_ar.
If possible include hook, script, subtitle_ar, query, topic, and category, but scenes are the authoritative source.
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
    "required": ["title", "description", "tags", "scenes"]
}


def request_openrouter() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    model = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return exactly one valid JSON object. No Markdown. The scenes array is authoritative."},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.45,
        "max_tokens": 3500,
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
        "generationConfig": {"temperature": 0.45, "maxOutputTokens": 3500,
                             "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def extract_json_text(text: str) -> dict:
    text = str(text or "").strip()
    if not text:
        raise RuntimeError("provider returned empty content")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return json.loads(text[start:end + 1])


def extract_openrouter(result: dict) -> dict:
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    return extract_json_text(content)


def extract_gemini(result: dict) -> dict:
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(p.get("text", "")) for p in parts).strip()
    return extract_json_text(text)


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def normalize(data: dict) -> dict:
    """Fill deterministic metadata from scenes so weak/free models need not emit every field."""
    if not isinstance(data, dict):
        raise ValueError("Provider response must be a JSON object")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Expected exactly 5 scenes before normalization")

    clean_scenes = []
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {i} is not an object")
        text_en = str(scene.get("text_en") or scene.get("text") or "").strip()
        text_ar = str(scene.get("text_ar") or scene.get("subtitle_ar") or "").strip()
        pexels = str(scene.get("pexels_query") or scene.get("query") or "").strip()
        if not text_en or not text_ar or not pexels:
            raise ValueError(f"Scene {i} is missing text_en, text_ar, or pexels_query")
        clean_scenes.append({"text_en": text_en, "text_ar": text_ar, "pexels_query": pexels})

    data["scenes"] = clean_scenes
    data["hook"] = str(data.get("hook") or clean_scenes[0]["text_en"]).strip()
    data["script"] = " ".join(s["text_en"] for s in clean_scenes).strip()
    data["subtitle_ar"] = " ".join(s["text_ar"] for s in clean_scenes).strip()
    data["query"] = str(data.get("query") or clean_scenes[0]["pexels_query"]).strip()
    data["topic"] = str(data.get("topic") or data.get("query") or clean_scenes[0]["pexels_query"]).strip()
    data["category"] = str(data.get("category") or "did you know").strip()
    return data


def validate(data: dict) -> None:
    data = normalize(data)
    required = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")
    scenes = data["scenes"]
    script = str(data["script"]).strip()
    if not 85 <= words(script) <= 95:
        raise ValueError(f"English script has {words(script)} words; expected 85-95")
    joined = " ".join(str(s["text_en"]).strip() for s in scenes).strip()
    if script != joined:
        raise ValueError("script must equal the scenes' English narration joined with spaces")
    if str(data["hook"]).strip() != str(scenes[0]["text_en"]).strip():
        raise ValueError("hook must equal the first scene English narration")
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("subtitle_ar must contain Arabic text")
    for i, scene in enumerate(scenes, 1):
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
    data = normalize(data)
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
            data = normalize(data)
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
