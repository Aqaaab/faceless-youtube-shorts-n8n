#!/usr/bin/env python3
"""Generate a validated job.json for the Shorts renderer.

Provider failures must never leave the workflow without a valid job. The
script tries configured AI providers once each, then uses a deterministic,
fully validated factual fallback. This also prevents wasting quota on retries
when a provider is already rate-limited.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip() or "openrouter/free"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip() or "gemini-3.6-flash"
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast").strip() or "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

PROMPT = r'''
Create one accurate and surprising YouTube Shorts "Did You Know?" story.
Return ONLY one valid JSON object. No Markdown, code fences, commentary, or reasoning.

Required fields: hook, script, subtitle_ar, title, description, tags, query, topic, category, scenes.
scenes must contain exactly 5 objects with text_en, text_ar, pexels_query.

Requirements:
- Exactly 5 scenes.
- Each scene must contain 7-30 English words; total narration must be 50-110 words.
- Scene 1 is the hook. Scene 5 ends with a short question or follow-for-more line.
- Every scene needs a complete Modern Standard Arabic translation.
- script must equal the five English scene texts joined with single spaces.
- Use one verifiable fact. Do not invent statistics, dates, scientific claims, or quotations.
- Each Pexels query must be 1-3 concrete English words describing the literal visual subject of that scene.
- Prefer literal footage subjects such as honeybee, beehive, flower, telescope, volcano; avoid abstract queries.
- Title is English only, <=90 characters, and ends with #Shorts.
- Description contains 2-3 English sentences followed by exactly 5 hashtags.
- Metadata fields title, description, tags, query, topic, category contain no Arabic.
- Tags contain 8-12 lowercase English keywords using only letters, digits, underscore, or hyphen.
- No emojis.
'''


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def _extract_json(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("Empty AI response")
    text = text.strip().replace("\ufeff", "")
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    candidate = text[start:end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as first:
        try:
            from json_repair import repair_json
            value = json.loads(repair_json(candidate))
        except Exception:
            repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                value = json.loads(repaired)
            except json.JSONDecodeError:
                raise first
    if not isinstance(value, dict):
        raise ValueError("AI response is not a JSON object")
    return value


def _post_json(url: str, body: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _openrouter(prompt: str, key: str) -> dict:
    payload = _post_json(
        OPENROUTER_URL,
        {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No reasoning."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 3500,
            "response_format": {"type": "json_object"},
        },
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless YouTube Shorts",
        },
    )
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OpenRouter returned empty content")
    return _extract_json(content)


def _gemini(prompt: str, key: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = _post_json(
        url,
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 3500, "responseMimeType": "application/json"},
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    return _extract_json(content)


def _cloudflare(prompt: str, key: str, account: str) -> dict:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CLOUDFLARE_MODEL}"
    payload = _post_json(
        url,
        {
            "messages": [
                {"role": "system", "content": "Return only valid JSON. No reasoning."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 3500,
        },
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    if payload.get("success") is False:
        raise ValueError("Cloudflare request failed")
    content = (payload.get("result") or {}).get("response")
    if isinstance(content, dict):
        return content
    return _extract_json(str(content or ""))


def validate(data: dict) -> dict:
    required = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")

    scenes = data["scenes"]
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("Expected exactly 5 scenes")

    texts = []
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {index} is not an object")
        for key in ("text_en", "text_ar", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"Scene {index} missing {key}")
        en = scene["text_en"].strip()
        count = _words(en)
        if not 7 <= count <= 30:
            raise ValueError(f"Scene {index} English text length is invalid: {count}; expected 7-30")
        if re.search(r"[\u0600-\u06ff]", en):
            raise ValueError(f"Scene {index} English text contains Arabic")
        if not 1 <= len(scene["pexels_query"].split()) <= 3:
            raise ValueError(f"Scene {index} Pexels query must contain 1-3 words")
        if not re.search(r"[\u0600-\u06ff]", scene["text_ar"]):
            raise ValueError(f"Scene {index} Arabic translation is missing")
        texts.append(en)

    data["script"] = " ".join(texts)
    data["hook"] = texts[0]
    total = _words(data["script"])
    if not 50 <= total <= 110:
        raise ValueError(f"English narration has {total} words; expected 50-110")
    if not re.search(r"[\u0600-\u06ff]", str(data["subtitle_ar"])):
        raise ValueError("subtitle_ar must contain Arabic text")

    title = str(data["title"]).strip()
    if len(title) > 90 or not title.endswith("#Shorts"):
        raise ValueError("Title must be <=90 characters and end with #Shorts")

    tags = data["tags"]
    if not isinstance(tags, list) or not 8 <= len(tags) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    data["tags"] = [str(tag).strip().lower() for tag in tags]
    if any(not re.fullmatch(r"[a-z0-9_-]+", tag) for tag in data["tags"]):
        raise ValueError("Tags contain invalid characters")

    metadata = "".join(str(data[k]) for k in ("title", "description", "query", "topic", "category"))
    if re.search(r"[\u0600-\u06ff]", metadata):
        raise ValueError("Metadata contains Arabic")
    return data


def deterministic_fallback() -> dict:
    """Network-free fallback with literal visual queries and Arabic translations."""
    scenes = [
        {
            "text_en": "Honeybees can tell other bees where food is by performing a waggle dance.",
            "text_ar": "تستطيع نحل العسل إخبار النحل الآخر بمكان الطعام من خلال أداء رقصة الاهتزاز.",
            "pexels_query": "honeybee",
        },
        {
            "text_en": "The dancer moves in a pattern that carries information about direction and distance.",
            "text_ar": "تتحرك النحلة الراقصة بنمط يحمل معلومات عن الاتجاه والمسافة.",
            "pexels_query": "bee dance",
        },
        {
            "text_en": "Other bees watch the movement and use the sun as a compass.",
            "text_ar": "يراقب النحل الآخر الحركة ويستخدم الشمس كبوصلة لتحديد الاتجاه.",
            "pexels_query": "honeybee closeup",
        },
        {
            "text_en": "This remarkable behavior helps a colony find flowers without maps or spoken instructions.",
            "text_ar": "يساعد هذا السلوك المذهل المستعمرة على العثور على الأزهار من دون خرائط أو تعليمات منطوقة.",
            "pexels_query": "bees flowers",
        },
        {
            "text_en": "So a tiny bee can share a route with its entire colony. Follow for more.",
            "text_ar": "وهكذا تستطيع نحلة صغيرة مشاركة طريق مع مستعمرتها بأكملها. تابعنا للمزيد.",
            "pexels_query": "honeybee hive",
        },
    ]
    data = {
        "hook": scenes[0]["text_en"],
        "script": " ".join(s["text_en"] for s in scenes),
        "subtitle_ar": " ".join(s["text_ar"] for s in scenes),
        "title": "How Honeybees Share Directions Without Words #Shorts",
        "description": "Honeybees use a waggle dance to communicate information about food locations. The behavior helps other bees navigate to useful resources. #Honeybees #Bees #Science #Nature #Shorts",
        "tags": ["honeybees", "bees", "waggle-dance", "science", "nature", "insects", "biology", "animalfacts", "didyouknow"],
        "query": "honeybee",
        "topic": "Honeybee communication",
        "category": "Science",
        "scenes": scenes,
        "provider": "deterministic-fallback",
    }
    return validate(data)


def generate_with_providers(prompt: str) -> dict:
    errors = []
    providers = []
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        providers.append(("OpenRouter", lambda: _openrouter(prompt, os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GEMINI_API_KEY", "").strip():
        providers.append(("Gemini", lambda: _gemini(prompt, os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip():
        providers.append(("Cloudflare Workers AI", lambda: _cloudflare(prompt, os.environ["CLOUDFLARE_API_TOKEN"].strip(), os.environ["CLOUDFLARE_ACCOUNT_ID"].strip())))

    for name, fn in providers:
        print(f"AI provider={name} attempt=1/1", flush=True)
        try:
            result = validate(fn())
            result["provider"] = name
            print(f"AI provider={name} generation and validation succeeded", flush=True)
            return result
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            errors.append(f"{name} HTTP {exc.code}: {detail[:500]}")
            print(errors[-1], flush=True)
            if exc.code == 429:
                print(f"{name} is rate-limited; no retry will be attempted.", flush=True)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"Invalid {name} response: {exc!r}", flush=True)

    print("All AI providers unavailable; using deterministic fallback.", flush=True)
    if errors:
        print("Provider summary: " + " | ".join(errors), flush=True)
    return deterministic_fallback()


def main() -> None:
    data = generate_with_providers(PROMPT)
    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"job.json written: {output}", flush=True)
    print(f"provider={data.get('provider')} topic={data.get('topic')} scenes={len(data['scenes'])} words={_words(data['script'])}", flush=True)


if __name__ == "__main__":
    main()
