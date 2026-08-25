#!/usr/bin/env python3
"""Aqaaab AI Router: free-only, quota-aware, health-aware provider routing."""
from __future__ import annotations
import json, os, time, sys, urllib.error, urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path: sys.path.insert(0, str(SCRIPTS))
RUN_DIR = Path(os.environ.get("RUN_DIR", "data/daily-production"))
STATE_DIR = RUN_DIR / "ai_router"; STATE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG = Path(os.environ.get("AI_ROUTER_CONFIG", str(ROOT / "config/ai-router.json")))
BLOCKRUN_BASE_URL = os.environ.get("BLOCKRUN_BASE_URL", "https://blockrun.ai/api/v1").rstrip("/")
BLOCKRUN_MODEL = os.environ.get("BLOCKRUN_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
BLOCKRUN_FREE_ONLY = os.environ.get("BLOCKRUN_FREE_ONLY", "true").lower() == "true"


def _load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"free_only": True}

def _load_state() -> dict:
    p = STATE_DIR / "state.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return {"providers": {}, "requests": 0, "tokens_estimated": 0}

def _save_state(state: dict) -> None:
    (STATE_DIR / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def estimate_tokens(text: str) -> int: return max(1, int(len(str(text).split()) * 1.35) + 300)

def _classify(exc: Exception) -> str:
    msg = str(exc).lower()
    if any(x in msg for x in ("401", "unauthorized", "invalid api key")): return "AUTH"
    if any(x in msg for x in ("402", "payment_required", "payment required")): return "PAID_REQUIRED"
    if any(x in msg for x in ("403", "accessdenied", "unpurchased", "allocationquota.freetieronly")): return "ACCESS_OR_QUOTA"
    if any(x in msg for x in ("404", "model_not_found", "model not found")): return "MODEL_NOT_FOUND"
    if any(x in msg for x in ("429", "rate limit", "too many requests", "tpm", "tpd")): return "RATE_LIMIT"
    if any(x in msg for x in ("400", "invalid request", "schema")): return "BAD_REQUEST"
    if any(x in msg for x in ("timeout", "timed out", "temporarily unavailable", "502", "503", "504")): return "TRANSIENT"
    return "UNKNOWN"

@dataclass
class Provider:
    name: str
    task_types: list[str]
    priority: int
    free_only: bool
    call: Callable[[str], Any]
    health: Callable[[], bool] | None = None
    model: str | None = None

class AIRouter:
    def __init__(self, providers: list[Provider], task: str = "long_story"):
        cfg = _load_config()
        if bool(cfg.get("free_only", True)) and any(not p.free_only for p in providers):
            raise RuntimeError("AI Router free-only protection rejected a paid-capable provider")
        self.providers = [p for p in providers if task in p.task_types or "*" in p.task_types]
        self.providers.sort(key=lambda p: p.priority); self.state = _load_state(); self.task = task

    def _entry(self, name: str) -> dict:
        return self.state.setdefault("providers", {}).setdefault(name, {"status":"UNKNOWN","failures":0,"calls":0,"estimated_tokens":0,"cooldown_until":0,"last_error":""})
    def _record(self, provider: Provider, status: str, tokens: int, error: str = "") -> None:
        e=self._entry(provider.name); e["status"]=status
        e["calls"] += 1 if status=="PASS" else 0; e["estimated_tokens"] += tokens if status=="PASS" else 0
        if error: e["last_error"]=error[:1000]
        if status!="PASS": e["failures"] += 1
        if status in {"PAID_REQUIRED","ACCESS_OR_QUOTA","RATE_LIMIT","AUTH","MODEL_NOT_FOUND"}: e["cooldown_until"]=int(time.time())+(86400 if status!="RATE_LIMIT" else 900)
        self.state["requests"]=int(self.state.get("requests",0))+1
        if status=="PASS": self.state["tokens_estimated"]=int(self.state.get("tokens_estimated",0))+tokens
        _save_state(self.state)
    def _eligible(self,p:Provider)->bool:
        e=self._entry(p.name); return time.time()>=float(e.get("cooldown_until",0)) and e.get("status") not in {"PAID_REQUIRED","ACCESS_OR_QUOTA","AUTH","MODEL_NOT_FOUND"}
    def route(self,prompt:str)->tuple[Any,str,str|None]:
        required=estimate_tokens(prompt); ledger=[]
        for p in self.providers:
            if not self._eligible(p): ledger.append({"provider":p.name,"decision":"SKIP_COOLDOWN","required_tokens":required}); continue
            if p.health is not None:
                try:
                    if not p.health(): self._record(p,"HEALTH_FAIL",0,"health check returned false"); ledger.append({"provider":p.name,"decision":"SKIP_HEALTH"}); continue
                except Exception as e: self._record(p,"HEALTH_FAIL",0,str(e)); ledger.append({"provider":p.name,"decision":"SKIP_HEALTH","error":str(e)[:300]}); continue
            try:
                result=p.call(prompt); self._record(p,"PASS",required); ledger.append({"provider":p.name,"decision":"PASS","estimated_tokens":required,"model":p.model}); self._write_ledger(ledger); return result,p.name,p.model
            except Exception as e:
                kind=_classify(e); self._record(p,kind,0,str(e)); ledger.append({"provider":p.name,"decision":"FAIL","classification":kind,"error":str(e)[:500]})
        self._write_ledger(ledger); raise RuntimeError("AI Router exhausted all eligible providers: "+json.dumps(ledger,ensure_ascii=False))
    def _write_ledger(self,ledger:list[dict])->None:
        (STATE_DIR/"routing_ledger.json").write_text(json.dumps({"task":self.task,"entries":ledger},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def _blockrun_free_model_available() -> bool:
    """Non-billing discovery probe. Never sends a paid request."""
    req=urllib.request.Request(f"{BLOCKRUN_BASE_URL}/models",headers={"Accept":"application/json","User-Agent":"Aqaaab-AI-Router/1.0"},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            data=json.loads(r.read().decode("utf-8","replace"))
        ids={str(x.get("id")) for x in data.get("data",[]) if isinstance(x,dict)}
        # BlockRun's documented free model is allow-listed. If /models omits it,
        # fail closed rather than trying an unknown or potentially paid model.
        return not ids or BLOCKRUN_MODEL in ids
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"BlockRun model discovery HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
    except Exception as e:
        raise RuntimeError(f"BlockRun model discovery failed: {e}")


def blockrun_long_story(prompt: str) -> dict:
    if not BLOCKRUN_FREE_ONLY: raise RuntimeError("BLOCKRUN_FREE_ONLY must remain true for production")
    if not _blockrun_free_model_available(): raise RuntimeError(f"BlockRun free model not listed: {BLOCKRUN_MODEL}")
    body={"model":BLOCKRUN_MODEL,"messages":[{"role":"system","content":"Return exactly one valid JSON object. No markdown or prose outside JSON."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":4000,"response_format":{"type":"json_object"}}
    req=urllib.request.Request(f"{BLOCKRUN_BASE_URL}/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":"Aqaaab-AI-Router/1.0","Authorization":"Bearer not-needed-for-free-models"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=180) as r: data=json.loads(r.read().decode("utf-8","replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"BlockRun HTTP {e.code}: {e.read().decode('utf-8','replace')[:700]}")
    content=((data.get("choices") or [{}])[0].get("message") or {}).get("content","")
    if isinstance(content,dict): return content
    from generate_job import extract
    return extract(str(content))


def build_long_story_router() -> AIRouter:
    from generate_job import openrouter, gemini, cf, compat
    from patent_provider_router import qwencloud_long_story
    from cerebras_provider import generate as cerebras_generate
    providers=[]
    # BlockRun is credentialless and strictly allow-listed as FREE-only.
    providers.append(Provider("BlockRun",["long_story"],5,True,blockrun_long_story,model=BLOCKRUN_MODEL))
    if os.getenv("QWENCLOUD_API_KEY"): providers.append(Provider("QwenCloud",["long_story"],10,True,lambda p:qwencloud_long_story(os.environ["QWENCLOUD_API_KEY"],p),model=os.getenv("QWENCLOUD_MODEL") or "auto-free-model"))
    if os.getenv("GROQ_API_KEY"):
        models=[]
        for m in [os.getenv("GROQ_TEXT_MODEL","openai/gpt-oss-120b"),"openai/gpt-oss-20b","qwen/qwen3.6-27b"]:
            if m and m not in models: models.append(m)
        for idx,model in enumerate(models): providers.append(Provider(f"Groq:{model}",["long_story"],20+idx,True,lambda p,m=model:compat("Groq",os.environ["GROQ_API_KEY"],m,p),model=model))
    if os.getenv("GEMINI_API_KEY"): providers.append(Provider("Gemini",["long_story"],40,True,lambda p:gemini(os.environ["GEMINI_API_KEY"],p),model=os.getenv("GEMINI_MODEL")))
    if os.getenv("CEREBRAS_API_KEY") and os.getenv("CEREBRAS_FREE_ONLY","true").lower()=="true": providers.append(Provider("Cerebras",["long_story"],50,True,lambda p:cerebras_generate(os.environ["CEREBRAS_API_KEY"],p),model=os.getenv("CEREBRAS_MODEL")))
    if os.getenv("TOGETHER_API_KEY") and os.getenv("ENABLE_TOGETHER_PROVIDER","false").lower()=="true": providers.append(Provider("Together",["long_story"],60,True,lambda p:compat("Together",os.environ["TOGETHER_API_KEY"],os.getenv("TOGETHER_TEXT_MODEL","Qwen/Qwen3.5-9B"),p),model=os.getenv("TOGETHER_TEXT_MODEL")))
    if os.getenv("OPENROUTER_API_KEY"): providers.append(Provider("OpenRouter",["long_story"],70,True,lambda p:openrouter(os.environ["OPENROUTER_API_KEY"],p),model=os.getenv("OPENROUTER_MODEL")))
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID"): providers.append(Provider("Cloudflare",["long_story"],80,True,lambda p:cf(os.environ["CLOUDFLARE_API_TOKEN"],os.environ["CLOUDFLARE_ACCOUNT_ID"],p)))
    return AIRouter(providers,task="long_story")

if __name__ == "__main__": raise SystemExit(0)
