#!/usr/bin/env python3
"""Optional OpenAI-compatible provider pool for Aqaaab AI Router.

Providers are opt-in. A provider is eligible only when its API key exists and
ENABLE_<NAME>_PROVIDER=true. The router still enforces free_only globally.
No provider is treated as healthy merely because /models responds: production
must pass a real inference health check before activation.
"""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from typing import Any

PROVIDERS = {
    "GitHubModels": {"base": "https://models.github.ai/inference", "key": "GITHUB_TOKEN", "model": "openai/gpt-4.1-mini"},
    "Mistral": {"base": "https://api.mistral.ai/v1", "key": "MISTRAL_API_KEY", "model": "mistral-small-latest"},
    "SambaNova": {"base": "https://api.sambanova.ai/v1", "key": "SAMBANOVA_API_KEY", "model": "Meta-Llama-3.3-70B-Instruct"},
    "HuggingFace": {"base": "https://router.huggingface.co/v1", "key": "HF_TOKEN", "model": "openai/gpt-oss-120b"},
    "ZAI": {"base": "https://open.bigmodel.cn/api/paas/v4", "key": "ZAI_API_KEY", "model": "glm-4.5-flash"},
    "LLM7": {"base": "https://api.llm7.io/v1", "key": "LLM7_API_KEY", "model": "gpt-oss-120b"},
    "AnyAPI": {"base": "https://api.anyapi.ai/v1", "key": "ANYAPI_API_KEY", "model": "gpt-oss-120b"},
    "ArliAI": {"base": "https://api.arliai.com/v1", "key": "ARLIAI_API_KEY", "model": "Qwen2.5-72B-Instruct"},
    "OllamaCloud": {"base": "https://ollama.com/v1", "key": "OLLAMA_API_KEY", "model": "gpt-oss:20b"},
    "ModelScope": {"base": "https://api-inference.modelscope.cn/v1", "key": "MODELSCOPE_API_KEY", "model": "Qwen/Qwen3-Next-80B-A3B-Instruct"},
}


def _post(url: str, key: str, body: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "aqaaab-ai-router/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _extract(data: dict[str, Any]) -> str:
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    if not content:
        raise RuntimeError("provider returned empty content")
    return str(content)


def health_check(name: str) -> tuple[bool, str]:
    """Perform a real tiny inference; never infer health from /models alone."""
    cfg = PROVIDERS[name]
    key = os.getenv(cfg["key"], "")
    if not key:
        return False, "missing_api_key"
    if os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true":
        return False, "provider_not_enabled"
    try:
        data = _post(cfg["base"].rstrip("/") + "/chat/completions", cfg["key"], {
            "model": cfg["model"],
            "messages": [{"role": "user", "content": "Reply only with OK."}],
            "max_tokens": 4,
            "temperature": 0,
        })
        text = _extract(data).strip().lower()
        if not text:
            return False, "empty_health_response"
        return True, "live_inference_ok"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        return False, f"http_{e.code}:{body}"
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"


def generate(name: str, prompt: str) -> dict[str, Any]:
    cfg = PROVIDERS[name]
    key = os.getenv(cfg["key"], "")
    if not key:
        raise RuntimeError(f"{name}: missing {cfg['key']}")
    if os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true":
        raise RuntimeError(f"{name}: provider disabled")
    body = {
        "model": os.getenv(f"{name.upper()}_MODEL", cfg["model"]),
        "messages": [
            {"role": "system", "content": "Return exactly one JSON object. No markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 12000,
    }
    try:
        data = _post(cfg["base"].rstrip("/") + "/chat/completions", key, body)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {text}") from e
    return {"content": _extract(data), "model": body["model"], "provider": name}


def enabled_provider_names() -> list[str]:
    return [n for n in PROVIDERS if os.getenv(PROVIDERS[n]["key"]) and os.getenv(f"ENABLE_{n.upper()}_PROVIDER", "false").lower() == "true"]
