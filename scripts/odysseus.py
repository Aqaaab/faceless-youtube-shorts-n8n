from __future__ import annotations
import json, os, urllib.request


def base_url() -> str:
    value = os.getenv("ODYSSEUS_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("ODYSSEUS_BASE_URL is required")
    return value


def chat_url() -> str:
    return base_url() + "/api/v1/chat"


def chat(prompt: str, model: str | None = None, timeout: int = 90) -> dict:
    key = os.getenv("ODYSSEUS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ODYSSEUS_API_KEY is required")
    body = json.dumps({"message": prompt, "model": model or os.getenv("ODYSSEUS_MODEL", "aqaaab/story")}).encode()
    req = urllib.request.Request(chat_url(), data=body, method="POST", headers={"Content-Type":"application/json", "Authorization":"Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = {"text": raw}
    return value if isinstance(value, dict) else {"response": value}


def extract_text(value: dict) -> str:
    for key in ("text", "response", "content", "message", "output"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return json.dumps(value, ensure_ascii=False)
