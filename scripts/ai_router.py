#!/usr/bin/env python3
"""Aqaaab AI Router: free-only, quota-aware, schema-aware provider fallback."""
from __future__ import annotations
import json, os, re, sys, time, urllib.error, urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any
ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=Path(__file__).resolve().parent
for p in (ROOT,SCRIPTS):
    if str(p) not in sys.path: sys.path.insert(0,str(p))
RUN_DIR=Path(os.environ.get("RUN_DIR","data/daily-production")); STATE_DIR=RUN_DIR/"ai_router"; STATE_DIR.mkdir(parents=True,exist_ok=True)
CONFIG=Path(os.environ.get("AI_ROUTER_CONFIG",str(ROOT/"config/ai-router.json")))
OUTPUT_TOKENS=int(os.environ.get("LONG_MAX_OUTPUT_TOKENS", "3600"))

def _load_config():
    try: return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {"free_only":True}
    except Exception: return {"free_only":True}

def _load_state():
    p=STATE_DIR/"state.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return {"providers":{},"requests":0,"tokens_estimated":0}

def _save_state(s): STATE_DIR.mkdir(parents=True,exist_ok=True); (STATE_DIR/"state.json").write_text(json.dumps(s,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def estimate_tokens(text): return max(1,int(len(str(text).split())*1.30)+240)

def _classify(exc):
    m=str(exc).lower()
    if any(x in m for x in ("schema_invalid","schema invalid","scene count","word count","language contract","missing story beats","invalid long-form","invalid tags","required fields","visual/query length contract","invalid beat","no json object","invalid json object")): return "SCHEMA_INVALID"
    if any(x in m for x in ("401","unauthorized","invalid api key")): return "AUTH"
    if any(x in m for x in ("402","payment_required","payment required")): return "PAID_REQUIRED"
    if any(x in m for x in ("403","accessdenied","unpurchased","allocationquota.freetieronly")): return "ACCESS_OR_QUOTA"
    if any(x in m for x in ("404","model_not_found","model not found","model_unavailable")): return "MODEL_NOT_FOUND"
    if any(x in m for x in ("429","rate limit","too many requests","tpm","tpd")): return "RATE_LIMIT"
    if any(x in m for x in ("400","invalid request")): return "BAD_REQUEST"
    if any(x in m for x in ("timeout","timed out","500","502","503","504","520","521","522","523","524")): return "TRANSIENT"
    return "UNKNOWN"

@dataclass
class Provider:
    name:str; task_types:list[str]; priority:int; free_only:bool; call:Callable[[str],Any]; model:str|None=None

class AIRouter:
    def __init__(self,providers,task="long_story"):
        cfg=_load_config()
        if bool(cfg.get("free_only",True)) and any(not p.free_only for p in providers): raise RuntimeError("AI Router free-only protection rejected a paid-capable provider")
        self.providers=sorted([p for p in providers if task in p.task_types or "*" in p.task_types],key=lambda p:p.priority)
        self.state=_load_state(); self.task=task
    def _entry(self,name): return self.state.setdefault("providers",{}).setdefault(name,{"status":"UNKNOWN","failures":0,"calls":0,"estimated_tokens":0,"cooldown_until":0,"last_error":""})
    def _record(self,p,status,tokens=0,error="",cooldown_seconds=None):
        e=self._entry(p.name); e["status"]=status
        if status=="PASS":
            e["calls"]+=1; e["estimated_tokens"]+=tokens; self.state["tokens_estimated"]=int(self.state.get("tokens_estimated",0))+tokens
        else: e["failures"]+=1
        if error: e["last_error"]=str(error)[:1500]
        defaults={"PASS":0,"PAID_REQUIRED":86400,"ACCESS_OR_QUOTA":86400,"AUTH":86400,"MODEL_NOT_FOUND":86400,"RATE_LIMIT":900,"TRANSIENT":120,"BAD_REQUEST":300,"UNKNOWN":300,"SCHEMA_INVALID":900}
        if cooldown_seconds is None: cooldown_seconds=defaults.get(status,300)
        e["cooldown_until"]=int(time.time())+cooldown_seconds if cooldown_seconds>0 else 0
        self.state["requests"]=int(self.state.get("requests",0))+1; _save_state(self.state)
    def _eligible(self,p): return time.time()>=float(self._entry(p.name).get("cooldown_until",0))
    def next_ready_delay(self,exclude=None):
        exclude=set(exclude or set()); now=time.time(); delays=[]
        for p in self.providers:
            if p.name in exclude: continue
            until=float(self._entry(p.name).get("cooldown_until",0))
            if until<=now: return 0
            delays.append(max(0,int(until-now)))
        return min(delays) if delays else None
    def clear_expired_cooldowns(self):
        now=time.time(); changed=False
        for p in self.providers:
            e=self._entry(p.name)
            if e.get("cooldown_until",0) and float(e["cooldown_until"])<=now:
                e["cooldown_until"]=0; changed=True
        if changed: _save_state(self.state)
    def route(self,prompt,exclude=None,force_provider=None,wait_for_ready=False,max_wait_seconds=None):
        exclude=set(exclude or set()); required=estimate_tokens(prompt); self.clear_expired_cooldowns(); ledger=[]; started=time.time()
        while True:
            made_attempt=False
            for p in self.providers:
                if force_provider and p.name!=force_provider: ledger.append({"provider":p.name,"decision":"SKIP_NOT_FORCED","required_tokens":required}); continue
                if p.name in exclude: ledger.append({"provider":p.name,"decision":"SKIP_EXCLUDED","required_tokens":required}); continue
                if not force_provider and not self._eligible(p): ledger.append({"provider":p.name,"decision":"SKIP_COOLDOWN","required_tokens":required}); continue
                made_attempt=True
                try:
                    result=p.call(prompt); self._record(p,"PASS",required); ledger.append({"provider":p.name,"decision":"PASS","estimated_tokens":required,"model":p.model}); self._write(ledger); return result,p.name,p.model
                except Exception as e:
                    kind=_classify(e); self._record(p,kind,0,str(e)); ledger.append({"provider":p.name,"decision":"FAIL","classification":kind,"error":str(e)[:700],"model":p.model})
                    if force_provider: break
            if force_provider or made_attempt or not wait_for_ready: self._write(ledger); raise RuntimeError("AI Router exhausted all eligible providers: "+json.dumps(ledger,ensure_ascii=False))
            delay=self.next_ready_delay(exclude=exclude)
            if delay is None: self._write(ledger); raise RuntimeError("AI Router exhausted all eligible providers: "+json.dumps(ledger,ensure_ascii=False))
            if max_wait_seconds is not None and time.time()-started+delay>max_wait_seconds: self._write(ledger); raise RuntimeError("AI Router cooldown wait exceeds max_wait_seconds")
            delay=max(1,min(delay,60)); print(f"AI_ROUTER_WAIT_FOR_COOLDOWN delay={delay}s"); time.sleep(delay); self.clear_expired_cooldowns()
    def report_validation_failure(self,provider_name,error):
        for p in self.providers:
            if p.name==provider_name: self._record(p,"SCHEMA_INVALID",0,str(error),cooldown_seconds=900); return
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

def _retry_delay(exc,attempt):
    m=re.search(r"(?:try again in|retry after)\s*([0-9]+(?:\.[0-9]+)?)s",str(exc),re.I)
    if m:
        try: return max(1,min(90,int(float(m.group(1))+1)))
        except Exception: pass
    return min(30,2**(attempt-1))

def _http_post(url,body,headers,retries=2):
    last=None
    for attempt in range(1,retries+1):
        try:
            req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,"User-Agent":"faceless-youtube-shorts/1.0","Accept":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=180) as r: return json.loads(r.read().decode("utf-8","replace"))
        except urllib.error.HTTPError as e:
            payload=e.read().decode("utf-8","replace")[:1200]; last=RuntimeError(f"HTTP {e.code}: {payload}")
            if e.code in {400,401,402,403,404}: raise last
            if e.code not in {408,425,429,500,502,503,504,520,521,522,523,524}: raise last
        except (urllib.error.URLError,TimeoutError) as e: last=e
        if attempt<retries:
            delay=_retry_delay(last,attempt); print(f"API retry {attempt+1}/{retries} after {delay}s"); time.sleep(delay)
    raise last or RuntimeError("request failed")

def _compat(provider,key,model,prompt,base_url=None,max_tokens=None):
    url=(base_url or ("https://api.groq.com/openai/v1" if provider=="Groq" else "https://api.together.ai/v1")).rstrip("/")+"/chat/completions"
    body={"model":model,"messages":[{"role":"system","content":"Return exactly one valid JSON object. No markdown and no prose outside JSON."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":max_tokens or OUTPUT_TOKENS,"response_format":{"type":"json_object"}}
    headers={"Content-Type":"application/json"}
    if key: headers["Authorization"]=f"Bearer {key}"
    try: x=_http_post(url,body,headers)
    except Exception as e:
        msg=str(e).lower()
        if not any(k in msg for k in ("response_format","json_object","400")): raise
        body.pop("response_format",None); x=_http_post(url,body,headers)
    return _extract(((x.get("choices") or [{}])[0].get("message") or {}).get("content",""))

def _openrouter(prompt):
    key=os.getenv("OPENROUTER_API_KEY","")
    if not key: raise RuntimeError("OpenRouter: missing OPENROUTER_API_KEY")
    model=os.getenv("OPENROUTER_MODEL","openai/gpt-oss-120b:free")
    if model=="openrouter/free": model="openai/gpt-oss-120b:free"
    if not model.endswith(":free"): raise RuntimeError("OpenRouter: paid model blocked; :free model required")
    return _compat("OpenRouter",key,model,prompt,base_url="https://openrouter.ai/api/v1")

def _cloudflare(prompt):
    token=os.getenv("CLOUDFLARE_API_TOKEN",""); account=os.getenv("CLOUDFLARE_ACCOUNT_ID","")
    if not token or not account: raise RuntimeError("CloudflareWorkersAI: missing credentials")
    model=os.getenv("CLOUDFLARE_MODEL","@cf/zai-org/glm-4.7-flash")
    url=f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    body={"messages":[{"role":"system","content":"Return exactly one valid JSON object. No markdown."},{"role":"user","content":prompt}],"max_tokens":OUTPUT_TOKENS,"temperature":0.1}
    x=_http_post(url,body,{"Authorization":f"Bearer {token}","Content-Type":"application/json"})
    result=x.get("result") or {}; text=result.get("response") or result.get("text") or (((result.get("choices") or [{}])[0].get("message") or {}).get("content",""))
    return _extract(text)

def _cohere(key,prompt): return _compat("Cohere",key,os.getenv("COHERE_MODEL","command-r7b-12-2024"),prompt,base_url="https://api.cohere.com/compatibility/v1")
def _ollama(prompt): return _compat("Ollama",os.getenv("OLLAMA_API_KEY",""),os.getenv("OLLAMA_MODEL","qwen3:8b"),prompt,base_url=os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434/v1"))
def _freellmapi(prompt): return _compat("FreeLLMAPI",os.getenv("FREELLMAPI_API_KEY",""),os.getenv("FREELLMAPI_MODEL","auto"),prompt,base_url=os.getenv("FREELLMAPI_BASE_URL","http://127.0.0.1:3001/v1"))

def build_long_story_router():
    from generate_job import gemini, compat
    from patent_provider_router import qwencloud_long_story
    providers=[]
    if os.getenv("QWENCLOUD_API_KEY"): providers.append(Provider("QwenCloud",["long_story"],10,True,lambda p:qwencloud_long_story(os.environ["QWENCLOUD_API_KEY"],p),model=os.getenv("QWENCLOUD_MODEL") or "auto-free-model"))
    if os.getenv("GROQ_API_KEY"):
        models=[]
        for m in [os.getenv("GROQ_TEXT_MODEL","openai/gpt-oss-120b"),"openai/gpt-oss-20b","qwen/qwen3.6-27b"]:
            if m and m not in models: models.append(m)
        for idx,m in enumerate(models): providers.append(Provider(f"Groq:{m}",["long_story"],20+idx,True,lambda p,m=m:compat("Groq",os.environ["GROQ_API_KEY"],m,p),model=m))
    if os.getenv("GEMINI_API_KEY"): providers.append(Provider("Gemini",["long_story"],40,True,lambda p:gemini(os.environ["GEMINI_API_KEY"],p),model=os.getenv("GEMINI_MODEL")))
    if os.getenv("CEREBRAS_API_KEY") and os.getenv("CEREBRAS_FREE_ONLY","true").lower()=="true":
        from cerebras_provider import generate as cerebras_generate; providers.append(Provider("Cerebras",["long_story"],50,True,lambda p:cerebras_generate(os.environ["CEREBRAS_API_KEY"],p),model=os.getenv("CEREBRAS_MODEL")))
    if os.getenv("COHERE_API_KEY"): providers.append(Provider("Cohere",["long_story"],55,True,lambda p:_cohere(os.environ["COHERE_API_KEY"],p),model=os.getenv("COHERE_MODEL","command-r7b-12-2024")))
    if os.getenv("OPENROUTER_API_KEY") and os.getenv("OPENROUTER_FREE_ONLY","true").lower()=="true": providers.append(Provider("OpenRouter",["long_story"],56,True,_openrouter,model=os.getenv("OPENROUTER_MODEL","openai/gpt-oss-120b:free")))
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_FREE_ONLY","true").lower()=="true": providers.append(Provider("CloudflareWorkersAI",["long_story"],57,True,_cloudflare,model=os.getenv("CLOUDFLARE_MODEL","@cf/zai-org/glm-4.7-flash")))
    if os.getenv("TOGETHER_API_KEY") and os.getenv("ENABLE_TOGETHER_PROVIDER","false").lower()=="true":
        m=os.getenv("TOGETHER_TEXT_MODEL","Qwen/Qwen3.5-9B"); providers.append(Provider("Together",["long_story"],60,True,lambda p:compat("Together",os.environ["TOGETHER_API_KEY"],m,p),model=m))
    if os.getenv("ENABLE_FREELLMAPI_PROVIDER","false").lower()=="true": providers.append(Provider("FreeLLMAPI",["long_story"],70,True,_freellmapi,model=os.getenv("FREELLMAPI_MODEL","auto")))
    if os.getenv("ENABLE_OLLAMA_PROVIDER","false").lower()=="true": providers.append(Provider("Ollama",["long_story"],80,True,_ollama,model=os.getenv("OLLAMA_MODEL","qwen3:8b")))
    return AIRouter(providers,task="long_story")
