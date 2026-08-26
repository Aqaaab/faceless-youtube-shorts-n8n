#!/usr/bin/env python3
"""Aqaaab AI Router: free-only, quota-aware, validation-aware provider fallback."""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for p in (ROOT, SCRIPTS):
    if str(p) not in sys.path: sys.path.insert(0, str(p))
RUN_DIR = Path(os.environ.get("RUN_DIR", "data/daily-production"))
STATE_DIR = RUN_DIR / "ai_router"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG = Path(os.environ.get("AI_ROUTER_CONFIG", str(ROOT / "config/ai-router.json")))

def _load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"free_only": True}

def _load_state():
    p=STATE_DIR/"state.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return {"providers":{},"requests":0,"tokens_estimated":0}

def _save_state(s): (STATE_DIR/"state.json").write_text(json.dumps(s,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def estimate_tokens(text): return max(1,int(len(str(text).split())*1.35)+300)

def _classify(exc):
    m=str(exc).lower()
    if any(x in m for x in ("schema_invalid","schema invalid","scene count","word count","language contract","missing story beats","invalid long-form","invalid tags","required fields","visual/query length contract","invalid beat")): return "SCHEMA_INVALID"
    if any(x in m for x in ("401","unauthorized","invalid api key")): return "AUTH"
    if any(x in m for x in ("402","payment_required","payment required")): return "PAID_REQUIRED"
    if any(x in m for x in ("403","accessdenied","unpurchased","allocationquota.freetieronly")): return "ACCESS_OR_QUOTA"
    if any(x in m for x in ("404","model_not_found","model not found")): return "MODEL_NOT_FOUND"
    if any(x in m for x in ("429","rate limit","too many requests","tpm","tpd")): return "RATE_LIMIT"
    if any(x in m for x in ("400","invalid request")): return "BAD_REQUEST"
    if any(x in m for x in ("timeout","timed out","500","502","503","504","520","521","522","523","524")): return "TRANSIENT"
    return "UNKNOWN"

@dataclass
class Provider:
    name:str; task_types:list[str]; priority:int; free_only:bool; call:Callable[[str],Any]; model:str|None=None

class AIRouter:
    def __init__(self,providers,task="long_story"):
        if bool(_load_config().get("free_only",True)) and any(not p.free_only for p in providers): raise RuntimeError("AI Router free-only protection rejected a paid-capable provider")
        self.providers=sorted([p for p in providers if task in p.task_types or "*" in p.task_types],key=lambda p:p.priority)
        self.state=_load_state(); self.task=task
    def _entry(self,name):
        return self.state.setdefault("providers",{}).setdefault(name,{"status":"UNKNOWN","failures":0,"calls":0,"estimated_tokens":0,"cooldown_until":0,"last_error":""})
    def _record(self,p,status,tokens,error="",cooldown_seconds=None):
        e=self._entry(p.name); e["status"]=status
        if status=="PASS":
            e["calls"]+=1; e["estimated_tokens"]+=tokens; self.state["tokens_estimated"]=int(self.state.get("tokens_estimated",0))+tokens
        else: e["failures"]+=1
        if error: e["last_error"]=error[:1500]
        if cooldown_seconds is None: cooldown_seconds={"PAID_REQUIRED":86400,"ACCESS_OR_QUOTA":86400,"AUTH":86400,"MODEL_NOT_FOUND":86400,"RATE_LIMIT":900,"TRANSIENT":120,"BAD_REQUEST":300,"UNKNOWN":300,"SCHEMA_INVALID":0}.get(status,300)
        e["cooldown_until"]=int(time.time())+cooldown_seconds if cooldown_seconds>0 else 0
        self.state["requests"]=int(self.state.get("requests",0))+1; _save_state(self.state)
    def _eligible(self,p): return time.time()>=float(self._entry(p.name).get("cooldown_until",0))
    def route(self,prompt,exclude=None):
        exclude=exclude or set(); required=estimate_tokens(prompt); ledger=[]
        for p in self.providers:
            if p.name in exclude: ledger.append({"provider":p.name,"decision":"SKIP_EXCLUDED","required_tokens":required}); continue
            if not self._eligible(p): ledger.append({"provider":p.name,"decision":"SKIP_COOLDOWN","required_tokens":required}); continue
            try:
                result=p.call(prompt); self._record(p,"PASS",required); ledger.append({"provider":p.name,"decision":"PASS","estimated_tokens":required,"model":p.model}); self._write(ledger); return result,p.name,p.model
            except Exception as e:
                kind=_classify(e); self._record(p,kind,0,str(e)); ledger.append({"provider":p.name,"decision":"FAIL","classification":kind,"error":str(e)[:700],"model":p.model})
        self._write(ledger); raise RuntimeError("AI Router exhausted all eligible providers: "+json.dumps(ledger,ensure_ascii=False))
    def report_validation_failure(self,provider_name,error):
        for p in self.providers:
            if p.name==provider_name:
                e=self._entry(provider_name)
                if e.get("status")=="PASS" and int(e.get("calls",0))>0:
                    e["calls"]=max(0,int(e.get("calls",0))-1); tokens=int(e.get("estimated_tokens",0)); e["estimated_tokens"]=0; self.state["tokens_estimated"]=max(0,int(self.state.get("tokens_estimated",0))-tokens)
                self._record(p,"SCHEMA_INVALID",0,str(error),cooldown_seconds=0); return
    def _write(self,ledger): (STATE_DIR/"routing_ledger.json").write_text(json.dumps({"task":self.task,"entries":ledger},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def _extract(text):
    text=(text or "").strip().replace("\ufeff",""); a,b=text.find("{"),text.rfind("}")
    if a<0 or b<=a: raise ValueError("no JSON object")
    raw=text[a:b+1]
    try: obj=json.loads(raw)
    except Exception:
        from json_repair import repair_json; obj=repair_json(raw,return_objects=True)
    if not isinstance(obj,dict): raise ValueError("invalid JSON object")
    return obj

def _http_post(url,body,headers,retries=2):
    last=None
    for attempt in range(1,retries+1):
        try:
            req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,"User-Agent":"faceless-youtube-shorts/1.0","Accept":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=180) as r: return json.loads(r.read().decode("utf-8","replace"))
        except urllib.error.HTTPError as e:
            last=RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:800]}")
            if e.code in {400,401,402,403,404}: raise last
            if e.code not in {408,425,429,500,502,503,504,520,521,522,523,524}: raise last
        except (urllib.error.URLError,TimeoutError) as e: last=e
        if attempt<retries: time.sleep(min(8,2**(attempt-1)))
    raise last or RuntimeError("request failed")

def _compat(provider,key,model,prompt,base_url=None):
    url=(base_url or ("https://api.groq.com/openai/v1" if provider=="Groq" else "https://api.together.ai/v1")).rstrip("/")+"/chat/completions"
    body={"model":model,"messages":[{"role":"system","content":"Return exactly one JSON object. No markdown."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":4500,"response_format":{"type":"json_object"}}
    try: x=_http_post(url,body,{"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    except Exception as e:
        if "400" not in str(e).lower() and "response_format" not in str(e).lower(): raise
        body.pop("response_format",None); x=_http_post(url,body,{"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    return _extract(((x.get("choices") or [{}])[0].get("message") or {}).get("content",""))

def _blockrun_models():
    req=urllib.request.Request("https://blockrun.ai/api/v1/models",headers={"Accept":"application/json","User-Agent":"faceless-youtube-shorts/1.0"},method="GET")
    with urllib.request.urlopen(req,timeout=30) as r: data=json.loads(r.read().decode("utf-8","replace"))
    return {str(x.get("id")):x for x in data.get("data",[]) if isinstance(x,dict) and x.get("id")}

def _blockrun(prompt):
    preferred=["nvidia/nemotron-3-nano-omni-30b-a3b-reasoning","nvidia/nemotron-nano-12b-v2-vl","nvidia/nemotron-nano-9b-v2","nvidia/mistral-nemotron"]; models=_blockrun_models(); candidates=[]
    for model in preferred:
        meta=models.get(model)
        if meta and str(meta.get("billing_mode",""))=="free" and float(meta.get("pricing",{}).get("input",1))==0 and float(meta.get("pricing",{}).get("output",1))==0: candidates.append(model)
    if not candidates: raise RuntimeError("BlockRun has no verified free allow-listed model")
    errors=[]
    for model in candidates:
        body={"model":model,"messages":[{"role":"system","content":"Return exactly one JSON object. No markdown."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":4500,"response_format":{"type":"json_object"}}
        try:
            x=_http_post("https://blockrun.ai/api/v1/chat/completions",body,{"Authorization":"Bearer not-needed-for-free-models","Content-Type":"application/json"},retries=2); print(f"BLOCKRUN_INFERENCE=PASS model={model}"); return _extract(((x.get("choices") or [{}])[0].get("message") or {}).get("content",""))
        except Exception as e:
            msg=str(e); errors.append(f"{model}: {msg}"); print(f"BLOCKRUN_MODEL_SKIP model={model} reason={msg}")
            if "400" in msg.lower() or "response_format" in msg.lower():
                try:
                    body.pop("response_format",None); x=_http_post("https://blockrun.ai/api/v1/chat/completions",body,{"Authorization":"Bearer not-needed-for-free-models","Content-Type":"application/json"},retries=2); print(f"BLOCKRUN_INFERENCE=PASS model={model} mode=plain_json"); return _extract(((x.get("choices") or [{}])[0].get("message") or {}).get("content",""))
                except Exception as e2: errors.append(f"{model}: retry {e2}")
    raise RuntimeError("BlockRun free model pool exhausted: "+" | ".join(errors[-8:]))

def _cohere(key,prompt): return _compat("Cohere",key,os.getenv("COHERE_MODEL","command-r7b-12-2024"),prompt,base_url="https://api.cohere.com/compatibility/v1")

def build_long_story_router():
    from generate_job import gemini, compat
    from patent_provider_router import qwencloud_long_story
    providers=[]
    if os.getenv("QWENCLOUD_API_KEY"): providers.append(Provider("QwenCloud",["long_story"],10,True,lambda p:qwencloud_long_story(os.environ["QWENCLOUD_API_KEY"],p),model=os.getenv("QWENCLOUD_MODEL") or "auto-free-model"))
    if os.getenv("BLOCKRUN_FREE_ENABLED","true").lower()=="true": providers.append(Provider("BlockRun",["long_story"],15,True,_blockrun,model="blockrun-free-pool"))
    if os.getenv("GROQ_API_KEY"):
        models=[]
        for m in [os.getenv("GROQ_TEXT_MODEL","openai/gpt-oss-120b"),"openai/gpt-oss-20b","qwen/qwen3.6-27b"]:
            if m and m not in models: models.append(m)
        for idx,m in enumerate(models): providers.append(Provider(f"Groq:{m}",["long_story"],20+idx,True,lambda p,m=m:compat("Groq",os.environ["GROQ_API_KEY"],m,p),model=m))
    if os.getenv("GEMINI_API_KEY"): providers.append(Provider("Gemini",["long_story"],40,True,lambda p:gemini(os.environ["GEMINI_API_KEY"],p),model=os.getenv("GEMINI_MODEL")))
    if os.getenv("CEREBRAS_API_KEY") and os.getenv("CEREBRAS_FREE_ONLY","true").lower()=="true":
        from cerebras_provider import generate as cerebras_generate; providers.append(Provider("Cerebras",["long_story"],50,True,lambda p:cerebras_generate(os.environ["CEREBRAS_API_KEY"],p),model=os.getenv("CEREBRAS_MODEL")))
    if os.getenv("COHERE_API_KEY"): providers.append(Provider("Cohere",["long_story"],55,True,lambda p:_cohere(os.environ["COHERE_API_KEY"],p),model=os.getenv("COHERE_MODEL","command-r7b-12-2024")))
    if os.getenv("TOGETHER_API_KEY") and os.getenv("ENABLE_TOGETHER_PROVIDER","false").lower()=="true":
        m=os.getenv("TOGETHER_TEXT_MODEL","Qwen/Qwen3.5-9B"); providers.append(Provider("Together",["long_story"],60,True,lambda p:compat("Together",os.environ["TOGETHER_API_KEY"],m,p),model=m))
    return AIRouter(providers,task="long_story")
