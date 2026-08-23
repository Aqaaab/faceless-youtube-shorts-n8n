# PATCH: provider routing hardening
# OpenRouter free router is used instead of retired :free model slugs.
# Gemini fallback uses a direct request function with explicit model argument.
# Existing generation logic should call generate_with_providers() below.

import json
import os
import re
import time
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")


def _extract_json(text):
    if not text:
        raise ValueError("Empty AI response")
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    starts = [p for p in (text.find("{"), text.find("[")) if p >= 0]
    if not starts:
        raise ValueError("No JSON object found")
    start = min(starts)
    candidate = text[start:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Conservative repair for common truncated/string/markdown cases.
        candidate = candidate.replace("\r", " ").replace("\n", " ")
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            raise


def _openrouter_request(prompt, api_key, model=OPENROUTER_MODEL):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON. No markdown. No commentary."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless YouTube Shorts",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode())
    content = payload["choices"][0]["message"]["content"]
    return _extract_json(content)


def _gemini_request(prompt, api_key, model=GEMINI_MODEL):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read().decode())
    content = payload["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(content)


def generate_with_providers(prompt):
    """Reliable provider chain. Returns parsed JSON or raises one final error."""
    errors = []
    or_key = os.getenv("OPENROUTER_API_KEY")
    gem_key = os.getenv("GEMINI_API_KEY")

    if or_key:
        for attempt in range(1, 3):
            try:
                print(f"AI provider=OpenRouter model={OPENROUTER_MODEL} attempt={attempt}/2", flush=True)
                return _openrouter_request(prompt, or_key, OPENROUTER_MODEL)
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")
                print(f"OpenRouter HTTP {e.code}: {msg[:1200]}", flush=True)
                errors.append(f"OpenRouter HTTP {e.code}")
                if e.code in (400, 401, 403, 404):
                    break
            except Exception as e:
                print(f"Invalid OpenRouter response: {e!r}", flush=True)
                errors.append(f"OpenRouter: {e}")
            time.sleep(2 * attempt)
    else:
        print("OPENROUTER_API_KEY is not configured; skipping OpenRouter", flush=True)

    if gem_key:
        for attempt in range(1, 2):
            try:
                print(f"AI provider=Gemini model={GEMINI_MODEL} attempt={attempt}/1", flush=True)
                return _gemini_request(prompt, gem_key, GEMINI_MODEL)
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")
                print(f"Gemini HTTP {e.code}: {msg[:1200]}", flush=True)
                errors.append(f"Gemini HTTP {e.code}")
                break
            except Exception as e:
                print(f"Invalid Gemini response: {e!r}", flush=True)
                errors.append(f"Gemini: {e}")
    else:
        print("GEMINI_API_KEY is not configured; skipping Gemini", flush=True)

    raise RuntimeError("All configured AI providers failed: " + " | ".join(errors))
