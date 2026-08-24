#!/usr/bin/env python3
"""Generate a Shorts job with a small, persistent performance-learning loop.

This is intentionally separate from generate_job.py so the existing generator
remains an untouched fallback while the growth engine is validated.
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
CONTEXT_FILE = Path(os.environ.get("GROWTH_CONTEXT_FILE", "learning/context.txt"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip() or "gemini-3.6-flash"
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

PROMPT = r'''
Create ONE original, accurate, high-retention YouTube Shorts "Did You Know?" story.
Return ONLY one valid JSON object. No Markdown, no code fences, no commentary, no reasoning.

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
  "scenes": [{"text_en":"...","text_ar":"...","pexels_query":"1-3 English words"}]
}

High-retention requirements:
- Exactly 5 scenes.
- Total English narration: 55-95 words.
- Scene 1 is a direct curiosity hook; no greeting, no channel intro, no filler.
- Put the strongest concrete payoff in scene 4.
- Scene 5 is a concise payoff/curiosity bridge; do NOT use generic "subscribe" filler unless it naturally fits.
- Every scene must move the story forward; no repeated wording.
- Use one verifiable fact or one tightly related fact cluster. Do not invent statistics, dates, quotes, or scientific claims.
- Prefer a concrete visual fact that is easy to illustrate with stock footage.
- The first sentence must create an information gap or surprising contrast.
- Use short spoken sentences and natural conversational English.
- Every scene has a complete Modern Standard Arabic translation.
- The "script" must equal the five English scene narrations joined with single spaces.
- Each Pexels query is 1-3 simple English words and visually concrete.
- Title is English only, <=90 characters, and ends with #Shorts.
- Metadata must contain no Arabic.
- Tags are lowercase English and only letters, digits, underscore, or hyphen.
- No emojis.

The system may provide a LEARNING CONTEXT section. Treat it as evidence about this channel's own historical performance, not as facts to copy. Reuse successful structural patterns, but never copy wording, titles, or topics verbatim.
'''

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
        "scenes": {"type": "array", "minItems": 5, "maxItems": 5, "items": {
            "type": "object",
            "properties": {
                "text_en": {"type": "string"},
                "text_ar": {"type": "string"},
                "pexels_query": {"type": "string"}
            },
            "required": ["text_en", "text_ar", "pexels_query"]
        }}
    },
    "required": ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
}


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def extract_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    candidate = text[start:end + 1].replace("\ufeff", "").replace("\r", " ")
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("AI response is not an object")
    return value


def post_json(url: str, body: dict, headers: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def openrouter(prompt: str, key: str) -> dict:
    payload = post_json(OPENROUTER_URL, {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Return only the requested JSON object."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.18,
        "max_tokens": 3500,
        "response_format": {"type": "json_object"},
    }, {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless YouTube Shorts Growth Engine"})
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError(f"OpenRouter returned no choices: {json.dumps(payload)[:700]}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter returned empty content")
    return extract_json(content)


def gemini(prompt: str, key: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = post_json(url, {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 3500,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }, {"x-goog-api-key": key, "Content-Type": "application/json"})
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError(f"Gemini returned no candidates: {json.dumps(payload)[:700]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    return extract_json(content)


def cloudflare(prompt: str, key: str, account: str) -> dict:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CLOUDFLARE_MODEL}"
    payload = post_json(url, {
        "messages": [
            {"role": "system", "content": "Return only the requested JSON object."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.18,
        "max_tokens": 3500,
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
    }, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if payload.get("success") is False:
        raise ValueError(f"Cloudflare failure: {json.dumps(payload)[:1000]}")
    result = payload.get("result") or {}
    response = result.get("response")
    return response if isinstance(response, dict) else extract_json(str(response or ""))


def validate(data: dict) -> None:
    required = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")
    scenes = data["scenes"]
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Exactly 5 scenes are required")
    scene_texts = []
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {i} is invalid")
        for key in ("text_en", "text_ar", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"Scene {i} missing {key}")
        en = scene["text_en"].strip()
        if not 7 <= words(en) <= 28:
            raise ValueError(f"Scene {i} has an invalid narration length")
        if re.search(r"[\u0600-\u06ff]", en):
            raise ValueError(f"Scene {i} English text contains Arabic")
        if not 1 <= len(scene["pexels_query"].split()) <= 3:
            raise ValueError(f"Scene {i} has an invalid Pexels query")
        scene_texts.append(en)
    script = " ".join(scene_texts)
    if not 55 <= words(script) <= 95:
        raise ValueError(f"Narration length {words(script)} is outside 55-95 words")
    data["script"] = script
    data["hook"] = scene_texts[0]
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("Arabic subtitle missing")
    title = str(data["title"]).strip()
    if len(title) > 90 or not title.endswith("#Shorts"):
        raise ValueError("Invalid title")
    tags = data["tags"]
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    data["tags"] = [str(t).strip().lower() for t in tags]
    for tag in data["tags"]:
        if not re.fullmatch(r"[a-z0-9_-]+", tag):
            raise ValueError(f"Invalid tag: {tag}")
    metadata = "".join(str(data[k]) for k in ("title", "description", "query", "topic", "category"))
    if re.search(r"[\u0600-\u06ff]", metadata):
        raise ValueError("Metadata contains Arabic")


def try_provider(name: str, fn):
    last = None
    for attempt in range(1, 4):
        print(f"Growth generator: {name} attempt {attempt}/3", flush=True)
        try:
            data = fn()
            validate(data)
            data["provider"] = name
            return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last = RuntimeError(f"{name} HTTP {exc.code}: {detail[:1000]}")
            print(last, flush=True)
            if exc.code in {400, 401, 403, 404}:
                break
        except Exception as exc:  # noqa: BLE001 - provider fallback boundary
            last = exc
            print(f"{name} invalid/failed: {exc}", flush=True)
        if attempt < 3:
            time.sleep(min(3 * attempt + random.uniform(0, 1.5), 10))
    return last


def build_prompt() -> str:
    context = ""
    if CONTEXT_FILE.is_file():
        context = CONTEXT_FILE.read_text(encoding="utf-8", errors="replace").strip()
        context = context[-10000:]
    if not context:
        context = "No historical performance data is available yet. Optimize for strong curiosity, clarity, originality, and visual match."
    return PROMPT + "\n\nLEARNING CONTEXT\n================\n" + context


def main() -> None:
    prompt = build_prompt()
    providers = []
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        providers.append(("OpenRouter", lambda: openrouter(prompt, os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GEMINI_API_KEY", "").strip():
        providers.append(("Gemini", lambda: gemini(prompt, os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip():
        providers.append(("Cloudflare Workers AI", lambda: cloudflare(prompt, os.environ["CLOUDFLARE_API_TOKEN"].strip(), os.environ["CLOUDFLARE_ACCOUNT_ID"].strip())))
    if not providers:
        raise SystemExit("No AI provider is configured")
    errors = []
    data = None
    for name, fn in providers:
        result = try_provider(name, fn)
        if isinstance(result, dict):
            data = result
            break
        errors.append(f"{name}: {result}")
    if data is None:
        raise SystemExit("All AI providers failed: " + " | ".join(errors))

    data["voice"] = os.environ.get("VOICE", "af_bella")
    data["speed"] = float(os.environ.get("SPEED", "1.0"))
    data["lang"] = os.environ.get("KOKORO_LANG", "en-us")
    data["music"] = os.environ.get("MUSIC_ENABLED", "true").lower() == "true"
    data["music_volume"] = float(os.environ.get("MUSIC_VOLUME", "0.10"))
    data["animation"] = os.environ.get("ANIMATION_ENABLED", "true").lower() == "true"
    data["ads"] = os.environ.get("ADS_ENABLED", "false").lower() == "true"
    data["narration"] = data["script"]
    data["pexels_query"] = data["scenes"][0]["pexels_query"]
    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote growth-optimized {output}", flush=True)


if __name__ == "__main__":
    main()
