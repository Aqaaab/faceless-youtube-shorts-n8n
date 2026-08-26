"""Provider registry with capability-first validation."""
from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "providers.json"

def load_registry() -> list[dict]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))["providers"]

def enabled(task: str) -> list[dict]:
    out=[]
    for p in load_registry():
        if p.get("enabled") and p.get("task")==task:
            if os.getenv(p.get("api_key_env", ""), "").strip() and os.getenv(p.get("base_url_env", ""), "").strip() and os.getenv(p.get("model_env", ""), "").strip():
                out.append(p)
    return out

def validate_registry() -> None:
    seen=set()
    for p in load_registry():
        pid=p.get("id")
        if not pid or pid in seen: raise ValueError("provider id missing or duplicated")
        seen.add(pid)
        for k in ("type","task","base_url_env","api_key_env","model_env"):
            if not p.get(k): raise ValueError(f"provider {pid} missing {k}")
        if p["type"] not in {"openai_compatible"}: raise ValueError(f"unsupported provider type: {p['type']}")

if __name__ == "__main__":
    validate_registry()
    print(f"PROVIDER_REGISTRY=PASS total={len(load_registry())} enabled_ready={len(enabled('long_story'))}")
