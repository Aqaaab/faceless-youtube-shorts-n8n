#!/usr/bin/env python3
"""Opt-in OpenAI-compatible provider adapters for Aqaaab AI Router."""
from __future__ import annotations
import json, os, urllib.error, urllib.request
from typing import Any

PROVIDERS = {
    "Mistral": {"base": "https://api.mistral.ai/v1", "key": "MISTRAL_API_KEY", "model": "mistral-small-latest"},
    "SambaNova": {"base": "https://api.sambanova.ai/v1", "key": "SAMBANOVA_API_KEY", "model": "Meta-Llama-3.3-70B-Instruct"},
    "HuggingFace": {"base": "https://router.huggingface.co/v1", "key": "HF_TOKEN", "model": "Qwen/Qwen2.5-7B-Instruct-1M"},
    "LLM7": {"base": "https://api.llm7.io/v1", "key": "LLM7_API_KEY", "model": "gpt-oss-120b"},
    "AnyAPI": {"base": "https://api.anyapi.ai/v1", "key": "ANYAPI_API_KEY", "model": "gpt-oss-120b"},
    "ArliAI": {"base": "https://api.arliai.com/v1", "key": "ARLIAI_API_KEY", "model": "Qwen2.5-72B-Instruct"},
    "OllamaCloud": {"base": "https://ollama.com/v1", "key": "OLLAMA_API_KEY", "model": "gpt-oss:20b"},
    "ModelScope": {"base": "https://api-inference.modelscope.cn/v1", "key": "MODELSCOPE_API_KEY", "model": "Qwen/Qwen3-Next-80B-A3B-Instruct"},
    "Together": {"base": "https://api.together.ai/v1", "key": "TOGETHER_API_KEY", "model": "Qwen/Qwen3.5-9B"},
}

def _post(url: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "aqaaab-ai-router/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _content(data: dict[str, Any]) -> str:
    value = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if isinstance(value, list):
        value = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in value)
    if not str(value).strip():
        raise RuntimeError("empty provider response")
    return str(value)

def health_check(name: str) -> tuple[bool, str]:
    cfg = PROVIDERS[name]; key = os.getenv(cfg["key"], "")
    if not key: return False, "missing_api_key"
    if os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true": return False, "provider_not_enabled"
    try:
        model = os.getenv(f"{name.upper()}_MODEL", cfg["model"])
        out = _post(cfg["base"].rstrip("/") + "/chat/completions", key, {"model": model, "messages": [{"role": "user", "content": "Reply only with OK."}], "max_tokens": 4, "temperature": 0})
        return (bool(_content(out).strip()), "live_inference_ok")
    except urllib.error.HTTPError as e:
        return False, f"http_{e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}:{e}"

def generate(name: str, prompt: str) -> dict[str, Any]:
    cfg = PROVIDERS[name]; key = os.getenv(cfg["key"], "")
    if not key: raise RuntimeError(f"{name}: missing {cfg['key']}")
    if os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true": raise RuntimeError(f"{name}: provider disabled")
    model = os.getenv(f"{name.upper()}_MODEL", cfg["model"])
    body = {"model": model, "messages": [{"role": "system", "content": "Return exactly one valid JSON object. No markdown, no prose outside JSON."}, {"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 12000}
    if name == "Mistral":
        body["response_format"] = {"type": "json_object"}
    try:
        out = _post(cfg["base"].rstrip("/") + "/chat/completions", key, body)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:800]; raise RuntimeError(f"HTTP {e.code}: {text}") from e
    return {"content": _content(out), "model": model, "provider": name}

def extend_router(router):
    """Attach enabled providers only after a live inference health check."""
    from ai_router import Provider, _extract
    for idx, name in enumerate(PROVIDERS):
        cfg = PROVIDERS[name]
        if not os.getenv(cfg["key"]) or os.getenv(f"ENABLE_{name.upper()}_PROVIDER", "false").lower() != "true": continue
        ok, reason = health_check(name)
        if not ok:
            print(f"PROVIDER_HEALTH_SKIP provider={name} reason={reason}"); continue
        def call(prompt, name=name): return _extract(generate(name, prompt)["content"])
        router.providers.append(Provider(name, ["long_story"], 56 + idx, True, call, model=os.getenv(f"{name.upper()}_MODEL", cfg["model"])))
        print(f"PROVIDER_HEALTH_PASS provider={name}")
    router.providers.sort(key=lambda p: p.priority); return router
