#!/usr/bin/env python3
"""Robust AI job generator: OpenRouter primary, Gemini fallback."""
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from json_repair import repair_json

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

PROMPT = """
Create ONE accurate and surprising YouTube Shorts 'Did You Know?' story.
Return ONLY one JSON object. No Markdown, no explanation, no code fences.
Create exactly 5 scenes.
Each scene must contain: text_en, text_ar, pexels_query.
English narration target: 78-95 words total.
Each scene target: 14-21 English words.
Use one verifiable fact only. Do not invent statistics, dates, scientific claims, or quotations.
Scene 1 must be a strong curiosity hook.
Scene 5 must end with a short question or follow-for-more line.
Each pexels_query must be 1-3 simple English words.
Title: English only, <=90 characters, ending in #Shorts.
Description: 2-3 English sentences followed by exactly 5 hashtags.
Tags: 8-12 lowercase English keywords. Use single words or underscores, never spaces.
Arabic is allowed only in text_ar/subtitle_ar.
Include hook, script, subtitle_ar, query, topic, category when possible; the scenes are authoritative.
"""


def request_openrouter(model: str) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object. Never use Markdown. "
                    "Exactly 5 scenes. Keep each scene concise. "
                    "All required scene fields must be present."
                ),
            },
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.25,
        "max_tokens": 3500,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "YouTube Shorts Automation",
        },
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
        "generationConfig": {
            "temperature": 0.25,
            "maxOutputTokens": 3500,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def parse_json_text(text: str) -> dict:
    text = str(text or "").strip()
    if not text:
        raise RuntimeError("provider returned empty content")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    candidate = text[start : end + 1] if start >= 0 and end > start else text
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            value = json.loads(repair_json(candidate))
        except Exception as exc:
            raise ValueError(f"JSON repair failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("provider response must be a JSON object")
    return value


def extract_openrouter(result: dict) -> dict:
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    return parse_json_text(content)


def extract_gemini(result: dict) -> dict:
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return parse_json_text("".join(str(p.get("text", "")) for p in parts))


def words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", str(text), flags=re.UNICODE))


def clean_tag(tag: object) -> str:
    value = str(tag or "").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    return value.strip("_")


def normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Provider response must be a JSON object")
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or len(raw_scenes) != 5:
        raise ValueError("Expected exactly 5 scenes")

    scenes = []
    for i, scene in enumerate(raw_scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {i} is not an object")
        text_en = str(scene.get("text_en") or scene.get("text") or "").strip()
        text_ar = str(scene.get("text_ar") or scene.get("subtitle_ar") or "").strip()
        query = str(scene.get("pexels_query") or scene.get("query") or "").strip()
        if not text_en or not text_ar or not query:
            raise ValueError(f"Scene {i} is missing required content")
        scenes.append({"text_en": text_en, "text_ar": text_ar, "pexels_query": query})

    data["scenes"] = scenes
    data["hook"] = str(data.get("hook") or scenes[0]["text_en"]).strip()
    data["script"] = " ".join(s["text_en"] for s in scenes).strip()
    data["subtitle_ar"] = " ".join(s["text_ar"] for s in scenes).strip()
    data["query"] = str(data.get("query") or scenes[0]["pexels_query"]).strip()
    data["topic"] = str(data.get("topic") or data["query"] or "did you know").strip()
    data["category"] = str(data.get("category") or "did you know").strip()

    title = str(data.get("title") or "Amazing Fact #Shorts").strip()
    if not title.lower().endswith("#shorts"):
        title = title.rstrip() + " #Shorts"
    data["title"] = title[:90].rstrip()

    description = str(data.get("description") or "Discover a surprising fact. Follow for more.\n#Shorts #DidYouKnow #Facts #Knowledge #Interesting").strip()
    data["description"] = description

    tags = [clean_tag(t) for t in (data.get("tags") or [])]
    tags = [t for t in tags if t]
    for seed in [data["query"], data["topic"], "did_you_know", "facts", "knowledge", "shorts", "science"]:
        tag = clean_tag(seed)
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= 10:
            break
    data["tags"] = tags[:12]
    return data


def repair_length(data: dict) -> dict:
    data = normalize(data)
    count = words(data["script"])
    if 78 <= count <= 95:
        return data
    if count < 78:
        # Deterministic, truthful CTA only; no invented facts.
        en = "Would you have guessed that? Follow for more surprising facts."
        ar = "هل كنت تتوقع ذلك؟ تابعنا للمزيد من الحقائق المدهشة."
        data["scenes"][-1]["text_en"] = (data["scenes"][-1]["text_en"] + " " + en).strip()
        data["scenes"][-1]["text_ar"] = (data["scenes"][-1]["text_ar"] + " " + ar).strip()
        data["script"] = " ".join(s["text_en"] for s in data["scenes"]).strip()
        data["subtitle_ar"] = " ".join(s["text_ar"] for s in data["scenes"]).strip()
        return data
    # Trim only from the final scene while preserving at least 14 words.
    target = 94
    excess = count - target
    if excess > 0:
        final_words = data["scenes"][-1]["text_en"].split()
        keep = max(14, len(final_words) - excess)
        data["scenes"][-1]["text_en"] = " ".join(final_words[:keep])
        data["script"] = " ".join(s["text_en"] for s in data["scenes"]).strip()
    return data


def validate(data: dict) -> dict:
    data = repair_length(data)
    scenes = data["scenes"]
    count = words(data["script"])
    if not 78 <= count <= 95:
        raise ValueError(f"English script has {count} words; expected 78-95")
    if data["script"] != " ".join(s["text_en"].strip() for s in scenes).strip():
        raise ValueError("script does not match scenes")
    if data["hook"] != scenes[0]["text_en"]:
        data["hook"] = scenes[0]["text_en"]
    if not re.search(r"[\u0600-\u06ff]", data["subtitle_ar"]):
        raise ValueError("subtitle_ar must contain Arabic")
    for i, scene in enumerate(scenes, 1):
        n = words(scene["text_en"])
        if not 14 <= n <= 28:
            raise ValueError(f"Scene {i} English text length is invalid: {n}")
        if re.search(r"[\u0600-\u06ff]", scene["text_en"]):
            raise ValueError(f"Scene {i} English text contains Arabic")
        if not 1 <= len(scene["pexels_query"].split()) <= 3:
            raise ValueError(f"Scene {i} Pexels query must contain 1-3 words")
    if len(data["title"]) > 90 or not data["title"].endswith("#Shorts"):
        raise ValueError("Title must be <=90 characters and end with #Shorts")
    if not 8 <= len(data["tags"]) <= 12:
        raise ValueError("Tags must contain 8-12 items")
    if any(re.search(r"[\u0600-\u06ff]", str(data[k])) for k in ("title", "description", "query", "topic", "category")):
        raise ValueError("Metadata contains Arabic outside subtitles")
    return data


def finalize(data: dict, provider: str) -> None:
    data = validate(data)
    data["provider"] = provider
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


def try_provider(name: str, models: list[str], request_fn, extract_fn) -> bool:
    for model in models:
        for attempt in range(1, 3):
            print(f"AI provider={name} model={model} attempt={attempt}/2")
            os.environ["OPENROUTER_MODEL"] = model
            try:
                raw = request_fn(model) if name == "OpenRouter" else request_fn()
                data = extract_fn(raw)
                finalize(data, name)
                print(f"AI provider={name} succeeded with {model}")
                return True
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                print(f"{name} HTTP {exc.code}: {detail[:900]}")
                if exc.code == 429:
                    break
            except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
                print(f"Invalid {name} response: {exc!r}")
            if attempt < 2:
                time.sleep(2 + random.uniform(0, 2))
    return False


def main() -> None:
    openrouter_models = [
        os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        "openai/gpt-oss-120b:free",
    ]
    if not try_provider("OpenRouter", list(dict.fromkeys(openrouter_models)), request_openrouter, extract_openrouter):
        print("OpenRouter unavailable; switching to Gemini fallback.")
        if not try_provider("Gemini", [os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")], lambda _m: request_gemini(), extract_gemini):
            raise SystemExit("All configured AI providers failed. No job.json was produced.")


if __name__ == "__main__":
    main()
