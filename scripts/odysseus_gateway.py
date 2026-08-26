#!/usr/bin/env python3
"""Small, dependency-free client for the Odysseus HTTP gateway.

Odysseus is the primary intelligence service. This module deliberately uses
only the Python standard library so validation and production runners do not
need the full Odysseus dependency tree just to import the client.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = int(os.getenv("ODYSSEUS_GATEWAY_TIMEOUT", "180"))


def chat_url(base_url: str | None = None) -> str:
    base = (base_url or os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "")).strip().rstrip("/")
    if not base:
        raise RuntimeError("ODYSSEUS_GATEWAY_BASE_URL is not configured")
    if base.endswith("/api/v1/chat"):
        return base
    if base.endswith("/api/v1"):
        return base + "/chat"
    if base.endswith("/api"):
        return base + "/v1/chat"
    return base + "/api/v1/chat"


def chat(
    message: str,
    *,
    session: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    key = api_key if api_key is not None else os.getenv("ODYSSEUS_GATEWAY_API_KEY", "")
    if not key:
        raise RuntimeError("ODYSSEUS_GATEWAY_API_KEY is not configured")
    payload: dict[str, Any] = {"message": message}
    if session:
        payload["session"] = session
    if model:
        payload["model"] = model
    request = urllib.request.Request(
        chat_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "faceless-youtube-shorts/odysseus-client",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout or DEFAULT_TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"Odysseus HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Odysseus transport failure: {exc}") from exc
    if not isinstance(body, dict):
        raise RuntimeError("Odysseus returned a non-object response")
    if not body.get("response"):
        raise RuntimeError("Odysseus response field is empty")
    return body


def extract_response(body: dict[str, Any]) -> dict[str, Any]:
    """Extract the JSON object generated inside Odysseus' response text."""
    value = body.get("response")
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Odysseus returned no response text")
    text = value.strip().replace("\ufeff", "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Odysseus response contains no JSON object")
    raw = text[start : end + 1]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            obj = repair_json(raw, return_objects=True)
        except Exception as exc:
            raise ValueError("Odysseus response is not valid JSON") from exc
    if not isinstance(obj, dict):
        raise ValueError("Odysseus response JSON is not an object")
    return obj


def health_url(base_url: str | None = None) -> str:
    base = (base_url or os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "")).strip().rstrip("/")
    if not base:
        raise RuntimeError("ODYSSEUS_GATEWAY_BASE_URL is not configured")
    return base + "/"


__all__ = ["chat", "chat_url", "extract_response", "health_url"]
