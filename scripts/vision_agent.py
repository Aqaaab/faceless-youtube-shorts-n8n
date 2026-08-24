#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
CLOUDFLARE_VISION_MODEL = os.environ.get("CLOUDFLARE_VISION_MODEL", "@cf/meta/llama-4-scout-17b-16e-instruct")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
TOGETHER_VISION_MODEL = os.environ.get("TOGETHER_VISION_MODEL", "Qwen/Qwen3.5-9B")
CACHE_DIR = Path(os.environ.get("VISION_CACHE_DIR", "data/vision_cache"))
STATE_FILE = CACHE_DIR / "provider_state.json"
MAX_REQUESTS = max(1, int(os.environ.get("VISION_MAX_REQUESTS_PER_RUN", "32")))
RETRIES = max(1, int(os.environ.get("VISION_RETRY_MAX", "2")))
BACKOFF = max(1.0, float(os.environ.get("VISION_BACKOFF_BASE", "3")))
CIRCUIT_SECONDS = max(30, int(os.environ.get("VISION_CIRCUIT_BREAKER_SECONDS", "600")))
MIN_SCORE = float(os.environ.get("VISION_MIN_SCORE", "0.88"))
MIN_SEMANTIC = float(os.environ.get("VISION_MIN_SEMANTIC_SCORE", "0.85"))


def _state():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"requests": 0, "providers": {}}


def _save(s):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def _key(prompt, images):
    h = hashlib.sha256(prompt.encode()).hexdigest()
    for p in images:
        h = hashlib.sha256(h.encode() + hashlib.sha256(Path(p).read_bytes()).digest()).hexdigest()
    return h


def _json(text):
    raw = (text or "").strip().replace("\ufeff", "")
    a, b = raw.find("{"), raw.rfind("}")
    if a < 0 or b <= a:
        raise RuntimeError("vision provider returned no JSON")
    raw = raw[a:b + 1]
    try:
        return json.loads(raw)
    except Exception:
        try:
            from json_repair import repair_json
            return repair_json(raw, return_objects=True)
        except Exception:
            raise RuntimeError("invalid vision JSON")


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _gemini(prompt, images, key):
    parts = [{"text": prompt}] + [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]
    x = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 3000,
                "responseMimeType": "application/json",
            },
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    return _json(
        "".join(
            str(p.get("text", ""))
            for p in (((x.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            if isinstance(p, dict)
        )
    )


def _openrouter(prompt, images, key):
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]
    x = _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
        },
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless Shorts Vision Agent",
        },
    )
    return _json(((x.get("choices") or [{}])[0].get("message") or {}).get("content", ""))


def _cloudflare_montage(images):
    images = [str(x) for x in images]
    if len(images) == 1:
        return Path(images[0])
    digest = hashlib.sha256()
    for p in images:
        digest.update(hashlib.sha256(Path(p).read_bytes()).digest())
    out = CACHE_DIR / f"vision_montage_{digest.hexdigest()}.jpg"
    if out.exists() and out.stat().st_size > 1000:
        return out
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    inputs = [Path(p) for p in images]
    filters = []
    for i, _ in enumerate(inputs):
        filters.append(
            f"[{i}:v]scale=420:746:force_original_aspect_ratio=decrease,pad=420:746:(ow-iw)/2:(oh-ih)/2:black[s{i}]"
        )
    stacked = "".join(f"[s{i}]" for i in range(len(inputs)))
    filters.append(f"{stacked}hstack=inputs={len(inputs)}:shortest=1[out]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", "-q:v", "4", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=90)
        if out.exists() and out.stat().st_size > 1000:
            return out
    except Exception as e:
        raise RuntimeError(f"could not build vision montage: {e}")
    raise RuntimeError("could not build vision montage")


def _openai_vision_payload(prompt, images):
    # Groq's current Qwen vision model supports multiple images; keeping the
    # request to a single montage for >3 images maximizes cross-provider
    # compatibility and keeps the final five-scene QA payload deterministic.
    if len(images) > 3:
        images = [str(_cloudflare_montage(images))]
    content = [{"type": "text", "text": prompt}] + [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()},
        }
        for p in images
    ]
    return content


def _groq(prompt, images, key):
    content = _openai_vision_payload(prompt, images)
    x = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {
            "model": GROQ_VISION_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_completion_tokens": 3000,
            "response_format": {"type": "json_object"},
        },
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    return _json(((x.get("choices") or [{}])[0].get("message") or {}).get("content", ""))


def _together(prompt, images, key):
    content = _openai_vision_payload(prompt, images)
    x = _post(
        "https://api.together.xyz/v1/chat/completions",
        {
            "model": TOGETHER_VISION_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.1,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        },
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    return _json(((x.get("choices") or [{}])[0].get("message") or {}).get("content", ""))


def _quota(e):
    if isinstance(e, urllib.error.HTTPError) and e.code == 429:
        return True
    s = str(e).lower()
    return any(x in s for x in ("quota", "rate limit", "too many requests", "insufficient_quota"))


def _call(name, fn, state):
    ps = state["providers"].setdefault(name, {})
    if float(ps.get("open_until", 0)) > time.time():
        raise RuntimeError(f"{name} circuit open")
    if state["requests"] >= MAX_REQUESTS:
        raise RuntimeError("vision request budget exhausted")
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            state["requests"] += 1
            result = fn()
            ps["failures"] = 0
            ps.pop("open_until", None)
            _save(state)
            return result
        except Exception as e:
            last = e
            ps["failures"] = int(ps.get("failures", 0)) + 1
            if _quota(e) or ps["failures"] >= 2:
                ps["open_until"] = time.time() + CIRCUIT_SECONDS
            _save(state)
            if attempt < RETRIES and not _quota(e):
                time.sleep(BACKOFF * (2 ** (attempt - 1)))
    raise last


def evaluate(prompt, images, kind="qa"):
    images = [str(x) for x in images]
    key = _key(prompt, images)
    cp = CACHE_DIR / f"{key}.json"
    if cp.exists():
        try:
            x = json.loads(cp.read_text())
            x["cached"] = True
            x["kind"] = kind
            return x
        except Exception:
            pass

    state = _state()
    errors = []
    providers = []
    if os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip():
        providers.append(
            (
                "cloudflare",
                lambda: _cloudflare_montage(images) if False else _cloudflare(
                    prompt,
                    images,
                    os.environ["CLOUDFLARE_API_TOKEN"].strip(),
                    os.environ["CLOUDFLARE_ACCOUNT_ID"].strip(),
                ),
            )
        )
    if os.environ.get("GEMINI_API_KEY", "").strip():
        providers.append(("gemini", lambda: _gemini(prompt, images, os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        providers.append(("openrouter", lambda: _openrouter(prompt, images, os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GROQ_API_KEY", "").strip():
        providers.append(("groq", lambda: _groq(prompt, images, os.environ["GROQ_API_KEY"].strip())))
    if os.environ.get("TOGETHER_API_KEY", "").strip():
        providers.append(("together", lambda: _together(prompt, images, os.environ["TOGETHER_API_KEY"].strip())))

    for name, fn in providers:
        try:
            x = _call(name, fn, state)
            x["provider"] = name
            x["cached"] = False
            x["kind"] = kind
            cp.write_text(json.dumps(x, ensure_ascii=False, indent=2))
            return x
        except Exception as e:
            errors.append(f"{name}: {e}")

    raise RuntimeError("Vision Agent unavailable: " + " | ".join(errors))


def stats():
    s = _state()
    return {
        "requests": s.get("requests", 0),
        "max_requests": MAX_REQUESTS,
        "providers": s.get("providers", {}),
        "cache_files": len(list(CACHE_DIR.glob("*.json"))),
    }
