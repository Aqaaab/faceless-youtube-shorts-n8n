from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
GEMINI_DEFAULT_MODEL = "gemini-3.7-flash"


def _url(base: str) -> str:
    b = base.rstrip("/")
    return b if b.endswith("/api/v1/chat") else b + "/api/v1/chat"


def _direct_url(base: str) -> str:
    b = base.rstrip("/")
    return b if b.endswith("/chat/completions") else b + "/v1/chat/completions"


def _has_fallback() -> bool:
    return bool(
        os.getenv("YOUTUBE_LLM_BASE_URL", "").strip()
        and os.getenv("YOUTUBE_LLM_API_KEY", "").strip()
    ) or bool(os.getenv("GEMINI_API_KEY", "").strip())


def _retryable_status(code: int) -> bool:
    return code in RETRYABLE_HTTP


def call(
    message: str,
    *,
    session: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    base = (base_url or os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "")).strip()
    key = (api_key or os.getenv("ODYSSEUS_GATEWAY_API_KEY", "")).strip()
    if not base or not key:
        raise RuntimeError("Odysseus gateway configuration is incomplete")

    payload: dict[str, Any] = {"message": message}
    if session:
        payload["session"] = session
    if model:
        payload["model"] = model

    attempts = max(1, int(os.getenv("ODYSSEUS_RETRIES", "2")) + 1)
    last_error: Exception | None = None

    for attempt in range(attempts):
        req = urllib.request.Request(
            _url(base),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
            if not isinstance(body, dict) or not body.get("response"):
                raise RuntimeError("Odysseus returned no response")
            return body
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            last_error = RuntimeError(f"Odysseus HTTP {exc.code}: {detail}")
            if not _retryable_status(exc.code):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = RuntimeError(f"Odysseus transport failure: {exc}")

        if attempt + 1 < attempts:
            time.sleep(min(8, 2**attempt))

    if _has_fallback():
        return _fallback_call(message, model=model, timeout=timeout)
    raise last_error or RuntimeError("Odysseus request failed")


def _fallback_call(message: str, *, model: str | None, timeout: int) -> dict[str, Any]:
    base = os.getenv("YOUTUBE_LLM_BASE_URL", "").strip()
    key = os.getenv("YOUTUBE_LLM_API_KEY", "").strip()
    errors: list[str] = []

    if base and key:
        try:
            return _direct_call(message, model=model, timeout=timeout)
        except RuntimeError as exc:
            errors.append(str(exc))

    try:
        return _gemini_call(message, timeout=timeout)
    except RuntimeError as exc:
        errors.append(str(exc))
        raise RuntimeError("All LLM fallbacks failed: " + " | ".join(errors)) from exc


def _direct_call(message: str, *, model: str | None, timeout: int) -> dict[str, Any]:
    base = os.getenv("YOUTUBE_LLM_BASE_URL", "").strip()
    key = os.getenv("YOUTUBE_LLM_API_KEY", "").strip()
    if not base or not key:
        raise RuntimeError("No YouTube direct LLM fallback is configured")

    fallback_model = os.getenv("YOUTUBE_LLM_MODEL", "").strip()
    payload_model = fallback_model or model or ""
    if not payload_model:
        raise RuntimeError("YOUTUBE_LLM_MODEL is not configured")

    payload = {
        "model": payload_model,
        "messages": [{"role": "user", "content": message}],
    }
    req = urllib.request.Request(
        _direct_url(base),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Direct YouTube LLM HTTP {exc.code}: "
            f"{exc.read().decode('utf-8', 'replace')[:1000]}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Direct YouTube LLM transport failure: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Direct YouTube LLM returned an unexpected response shape") from exc
    return {
        "response": content,
        "model": body.get("model", payload_model),
        "provider": "YouTubeFallback",
    }


def _gemini_call(message: str, *, timeout: int) -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    # A blank GitHub secret must not override the safe default.
    gemini_model = os.getenv("GEMINI_MODEL", "").strip() or GEMINI_DEFAULT_MODEL
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{gemini_model}:generateContent?key={key}"
    )

    # Gemini 3.x no longer accepts the legacy temperature parameter.
    payload = {
        "contents": [{"role": "user", "parts": [{"text": message}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    attempts = max(1, int(os.getenv("GEMINI_RETRIES", "2")) + 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
            content = body["candidates"][0]["content"]["parts"][0]["text"]
            if not content.strip():
                raise RuntimeError("Gemini returned an empty response")
            return {
                "response": content,
                "model": gemini_model,
                "provider": "GeminiFallback",
            }
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1200]
            last_error = RuntimeError(f"Gemini fallback HTTP {exc.code}: {detail}")
            if exc.code not in RETRYABLE_HTTP:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = RuntimeError(f"Gemini fallback transport failure: {exc}")
        except (KeyError, IndexError, TypeError) as exc:
            last_error = RuntimeError("Gemini fallback returned an unexpected response shape")
            break

        if attempt + 1 < attempts:
            time.sleep(min(8, 2**attempt))

    raise last_error or RuntimeError("Gemini fallback failed")


def extract_json(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("response")
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("LLM response is not text or object")
    text = value.strip().replace("\ufeff", "")
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("No JSON object in LLM response")
    raw = text[a : b + 1]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        from json_repair import repair_json
        obj = repair_json(raw, return_objects=True)
    if not isinstance(obj, dict):
        raise ValueError("LLM JSON is not an object")
    return obj
