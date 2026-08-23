#!/usr/bin/env python3
"""Generate a validated job.json for the Shorts renderer.

Provider order:
1. OpenRouter Free Models Router
2. Gemini 3.7 Flash

The generator is deliberately self-contained so the workflow never depends on
an external Python package for JSON repair or provider routing.
"""
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash").strip() or "gemini-3.7-flash"

PROMPT = r'''
Create one accurate and surprising YouTube Shorts "Did You Know?" story.
Return ONLY one valid JSON object. Do not use Markdown fences or commentary.

Required JSON shape:
{
  "hook": "string",
  "script": "string",
  "subtitle_ar": "complete Modern Standard Arabic translation",
  "title": "English title ending with #Shorts",
  "description": "2-3 English sentences followed by exactly 5 hashtags",
  "tags": ["8-12 lowercase English keywords"],
  "query": "1-3 English words",
  "topic": "English",
  "category": "English",
  "scenes": [
    {"text_en":"...","text_ar":"...","pexels_query":"1-3 English words"}
  ]
}

Hard requirements:
- Exactly 5 scenes.
- The complete English narration must be 85-95 words.
- Each scene must be 14-22 English words. Keep the total exactly equal to the scene texts joined by spaces.
- Scene 1 is the hook.
- Scene 5 ends with a short question or follow-for-more line.
- Every scene has a complete Modern Standard Arabic translation.
- Use one verifiable fact only. Do not invent statistics, dates, scientific claims, or quotations.
- Each Pexels query is 1-3 simple English words.
- Title is English only, <=90 characters, and ends with #Shorts.
- Metadata (title, description, tags, query, topic, category) must contain no Arabic.
- Tags must be lowercase English words using only letters, digits, underscore, or hyphen.
- No emojis.
'''


def _extract_json(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("Empty AI response")
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text, flags=re.I)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    candidate = text[start:end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as first:
        # Repair only common transport/model formatting damage; never invent fields.
        repaired = candidate.replace("\ufeff", "").replace("\r", " ")
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        try:
            value = json.loads(repaired)
        except json.JSONDecodeError:
            raise first
    if not isinstance(value, dict):
        raise ValueError("AI response is not a JSON object")
    return value


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def _post_json(url: str, body: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Provider returned non-JSON HTTP body: {raw[:500]}") from exc


def _openrouter_request(prompt: str, api_key: str, model: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON matching the user's required object. No markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 3500,
    }
    payload = _post_json(
        OPENROUTER_URL,
        body,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless YouTube Shorts",
        },
    )
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError(f"OpenRouter returned no choices: {json.dumps(payload)[:700]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter returned empty content")
    return _extract_json(content)


def _gemini_request(prompt: str, api_key: str, model: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 3500,
            "responseMimeType": "application/json",
        },
    }
    payload = _post_json(url, body, {"x-goog-api-key": api_key, "Content-Type": "application/json"})
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {json.dumps(payload)[:700]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
    if not content:
        raise ValueError("Gemini returned empty content")
    return _extract_json(content)


def validate(data: dict) -> None:
    required = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")

    scenes = data["scenes"]
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Expected exactly 5 scenes")

    scene_texts = []
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} is not an object")
        for key in ("text_en", "text_ar", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"Scene {index} missing {key}")
        en = scene["text_en"].strip()
        scene_texts.append(en)
        count = _words(en)
        if not 14 <= count <= 22:
            raise ValueError(f"Scene {index} English text length is invalid: {count}; expected 14-22")
        if re.search(r"[\u0600-\u06ff]", en):
            raise ValueError(f"Scene {index} English text contains Arabic")
        qwords = scene["pexels_query"].split()
        if not 1 <= len(qwords) <= 3:
            raise ValueError(f"Scene {index} Pexels query must contain 1-3 words")

    script = str(data["script"]).strip()
    joined = " ".join(scene_texts)
    count = _words(script)
    if not 85 <= count <= 95:
        raise ValueError(f"English script has {count} words; expected 85-95")
    if script != joined:
        raise ValueError("script must exactly equal the scenes' English narration joined with spaces")
    if str(data["hook"]).strip() != scene_texts[0]:
        raise ValueError("hook must exactly equal the first scene English narration")
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("subtitle_ar must contain Arabic text")

    title = str(data["title"]).strip()
    if len(title) > 90 or not title.endswith("#Shorts"):
        raise ValueError("Title must be <=90 characters and end with #Shorts")

    tags = data["tags"]
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    normalized_tags = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]+", tag):
            raise ValueError(f"Invalid tag: {tag}")
        normalized_tags.append(tag)
    data["tags"] = normalized_tags

    metadata = "".join(str(data[k]) for k in ("title", "description", "query", "topic", "category"))
    if re.search(r"[\u0600-\u06ff]", metadata):
        raise ValueError("Metadata contains Arabic outside subtitles")


def _try_provider(name: str, fn, attempts: int):
    last = None
    for attempt in range(1, attempts + 1):
        print(f"AI provider={name} attempt={attempt}/{attempts}", flush=True)
        try:
            data = fn()
            validate(data)
            print(f"AI provider={name} generation and validation succeeded", flush=True)
            return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{name} HTTP {exc.code}: {detail[:1200]}")
            print(last, flush=True)
            if exc.code in {400, 401, 403, 404}:
                break
            if exc.code not in {408, 409, 425, 429, 500, 502, 503, 504}:
                break
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
            last = exc
            print(f"Invalid {name} response: {exc!r}", flush=True)
        if attempt < attempts:
            time.sleep(min(2 * attempt + random.uniform(0, 1), 6))
    return last


def generate_with_providers(prompt: str) -> dict:
    errors = []
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if openrouter_key:
        error = _try_provider("OpenRouter", lambda: _openrouter_request(prompt, openrouter_key, OPENROUTER_MODEL), 2)
        if isinstance(error, dict):
            return error
        if error:
            errors.append(f"OpenRouter: {error}")
    else:
        print("OPENROUTER_API_KEY is not configured; skipping OpenRouter", flush=True)

    if gemini_key:
        print("OpenRouter unavailable; switching to Gemini fallback.", flush=True)
        error = _try_provider("Gemini", lambda: _gemini_request(prompt, gemini_key, GEMINI_MODEL), 1)
        if isinstance(error, dict):
            return error
        if error:
            errors.append(f"Gemini: {error}")
    else:
        print("GEMINI_API_KEY is not configured; skipping Gemini", flush=True)

    raise RuntimeError("All configured AI providers failed. No job.json was produced. " + " | ".join(errors))


def main() -> None:
    data = generate_with_providers(PROMPT)

    data["voice"] = os.environ.get("VOICE", "af_bella")
    data["speed"] = float(os.environ.get("SPEED", "1.0"))
    data["lang"] = os.environ.get("KOKORO_LANG", "en-us")
    data["music"] = os.environ.get("MUSIC_ENABLED", "true").lower() == "true"
    data["music_volume"] = float(os.environ.get("MUSIC_VOLUME", "0.10"))
    data["animation"] = os.environ.get("ANIMATION_ENABLED", "true").lower() == "true"
    data["ads"] = os.environ.get("ADS_ENABLED", "false").lower() == "true"
    data["narration"] = data["script"]
    data["pexels_query"] = data["scenes"][0]["pexels_query"]
    data["provider"] = "OpenRouter" if os.environ.get("OPENROUTER_API_KEY", "").strip() else "Gemini"

    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}", flush=True)


if __name__ == "__main__":
    main()
