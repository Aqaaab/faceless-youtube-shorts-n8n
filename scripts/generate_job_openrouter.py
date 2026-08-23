#!/usr/bin/env python3
"""Fallback job generator using OpenRouter when Gemini is unavailable or exhausted."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from generate_job import PROMPT, RUN_DIR, validate

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free").strip()


def request() -> dict:
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing from GitHub Secrets")

    url = "https://openrouter.ai/api/v1/chat/completions"
    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict JSON generator. Return only valid JSON. "
                    "Include every field requested by the user, especially hook, "
                    "script, subtitle_ar, title, description, tags, query, topic, "
                    "category, and exactly 5 scenes."
                ),
            },
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.55,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "YouTube Shorts Automation",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def extract_json(result: dict) -> dict:
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise RuntimeError("OpenRouter returned empty content")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError("OpenRouter response is not a JSON object")
    return value


def normalize(data: dict) -> dict:
    """Normalize common free-model omissions into the renderer's required schema."""
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        return data

    # Free models sometimes omit metadata that can be deterministically derived.
    first = scenes[0]
    data.setdefault("hook", str(first.get("text_en", "")).strip())
    data.setdefault(
        "subtitle_ar",
        " ".join(str(scene.get("text_ar", "")).strip() for scene in scenes).strip(),
    )
    data.setdefault("query", str(first.get("pexels_query", "nature")).strip())
    data.setdefault("topic", str(data.get("title", "Did You Know")).replace("#Shorts", "").strip())
    data.setdefault("category", "Did You Know")
    return data


def main() -> None:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        print(f"OpenRouter model={MODEL} attempt={attempt}/3")
        try:
            data = normalize(extract_json(request()))
            validate(data)
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
            print(f"OpenRouter fallback succeeded; wrote {output}")
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"OpenRouter HTTP {exc.code}: {detail[:1200]}")
            print(last_error)
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
            last_error = exc
            print(f"Invalid OpenRouter response: {exc!r}")
        time.sleep(3 * attempt)
    raise SystemExit(f"OpenRouter fallback failed: {last_error}")


if __name__ == "__main__":
    main()
