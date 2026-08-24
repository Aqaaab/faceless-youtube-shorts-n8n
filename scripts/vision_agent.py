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
USER_AGENT = "faceless-youtube-shorts-n8n/1.0"


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
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json", **headers}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=merged, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e.reason}") from e


def _extract_response(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        # Cloudflare REST can return result as either an object or the raw
        # generated response string depending on model/runtime version.
        result = x.get("result")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for k in ("response", "text", "output"):
                if isinstance(result.get(k), str):
                    return result[k]
            # Some OpenAI-compatible Cloudflare responses nest choices under result.
            choices = result.get("choices") or []
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message") or {}
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    return msg["content"]
        if isinstance(x.get("response"), str):
            return x["response"]
        choices = x.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(choices[0].get("text"), str):
                return choices[0]["text"]
    raise RuntimeError("vision provider returned an unexpected response shape")


def _gemini(prompt, images, key):
    parts = [{"text": prompt}] + [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]
    x = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 3000, "responseMimeType": "application/json"},
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    return _json(_extract_response(x))


def _openrouter(prompt, images, key):
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]
    x = _post(
        "https://openrouter.ai/api/v1/chat/completions",
        {"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0, "max_tokens": 3000, "response_format": {"type": "json_object"}},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless Shorts Vision Agent"},
    )
    return _json(_extract_response(x))


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
    filters = [f"[{i}:v]scale=420:746:force_original_aspect_ratio=decrease,pad=420:746:(ow-iw)/2:(oh-ih)/2:black[s{i}]" for i in range(len(inputs))]
    stacked = "".join(f"[s{i}]" for i in range(len(inputs)))
    filters.append(f"{stacked}hstack=inputs={len(inputs)}:shortest=1[out]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1", "-q:v", "4", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=90)
    except Exception as e:
        raise RuntimeError(f"could not build vision montage: {e}") from e
    if out.exists() and out.stat().st_size > 1000:
        return out
    raise RuntimeError("could not build vision montage")


def _cloudflare(prompt, images, token, account_id):
    image_path = _cloudflare_montage(images)
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    x = _post(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_VISION_MODEL}",
        {
            "messages": [{"role": "user", "content": prompt}],
            "image": "data:image/jpeg;base64," + image_b64,
            "max_tokens": 3000,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    return _json(_extract_response(x))


def _openai_vision_payload(prompt, images):
    if len(images) > 3:
        images = [str(_cloudflare_montage(images))]
    return [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(p).read_bytes()).decode()}}
        for p in images
    ]


def _groq(prompt, images, key):
    x = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {"model": GROQ_VISION_MODEL, "messages": [{"role": "user", "content": _openai_vision_payload(prompt, images)}], "temperature": 0, "max_completion_tokens": 3000, "response_format": {"type": "json_object"}},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    return _json(_extract_response(x))


def _together(prompt, images, key):
    x = _post(
        "https://api.together.ai/v1/chat/completions",
        {"model": TOGETHER_VISION_MODEL, "messages": [{"role": "user", "content": _openai_vision_payload(prompt, images)}], "temperature": 0, "max_tokens": 3000, "response_format": {"type": "json_object"}, "reasoning": {"enabled": False}},
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    return _json(_extract_response(x))


def _quota(e):
    s = str(e).lower()
    return "http 429" in s or any(x in s for x in ("quota", "rate limit", "too many requests", "insufficient_quota"))


def _transient(e):
    s = str(e).lower()
    return _quota(e) or any(x in s for x in ("http 500", "http 502", "http 503", "http 504", "timeout", "timed out", "network error", "connection reset"))


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
            ps["last_error"] = None
            _save(state)
            return result
        except Exception as e:
            last = e
            ps["last_error"] = str(e)[:1500]
            if _transient(e):
                ps["failures"] = int(ps.get("failures", 0)) + 1
                if _quota(e) or ps["failures"] >= 2:
                    ps["open_until"] = time.time() + CIRCUIT_SECONDS
            _save(state)
            if not _transient(e) or attempt >= RETRIES:
                break
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
        providers.append(("cloudflare", lambda: _cloudflare(prompt, images, os.environ["CLOUDFLARE_API_TOKEN"].strip(), os.environ["CLOUDFLARE_ACCOUNT_ID"].strip())))
    if os.environ.get("GEMINI_API_KEY", "").strip():
        providers.append(("gemini", lambda: _gemini(prompt, images, os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        providers.append(("openrouter", lambda: _openrouter(prompt, images, os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GROQ_API_KEY", "").strip():
        providers.append(("groq", lambda: _groq(prompt, images, os.environ["GROQ_API_KEY"].strip())))
    if os.environ.get("TOGETHER_API_KEY", "").strip():
        providers.append(("together", lambda: _together(prompt, images, os.environ["TOGETHER_API_KEY"].strip())))

    if not providers:
        raise RuntimeError("Vision Agent unavailable: no Vision provider credentials configured")

    for name, fn in providers:
        try:
            x = _call(name, fn, state)
            if not isinstance(x, dict):
                raise RuntimeError(f"{name}: provider result is not a JSON object")
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
    return {"requests": s.get("requests", 0), "max_requests": MAX_REQUESTS, "providers": s.get("providers", {}), "cache_files": len(list(CACHE_DIR.glob("*.json")))}
