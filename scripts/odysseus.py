from __future__ import annotations
import json, os, urllib.request


def base_url() -> str:
    value = os.getenv("ODYSSEUS_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("ODYSSEUS_BASE_URL is required")
    return value


def chat_url() -> str:
    return base_url() + "/api/chat"


def chat(prompt: str, model: str | None = None, timeout: int = 90) -> dict:
    body = json.dumps({"message": prompt, "model": model or os.getenv("ODYSSEUS_MODEL", "")}).encode()
    headers = {"Content-Type": "application/json"}
    key = os.getenv("ODYSSEUS_API_KEY", "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(chat_url(), data=body, method="POST", headers=headers)
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
