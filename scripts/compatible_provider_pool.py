"""Opt-in free-tier provider adapters for Aqaaab AI Router."""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any

PROVIDERS={
"Mistral":{"base":"https://api.mistral.ai/v1","key":"MISTRAL_API_KEY","model":"mistral-small-latest"},
"SambaNova":{"base":"https://api.sambanova.ai/v1","key":"SAMBANOVA_API_KEY","model":"Meta-Llama-3.3-70B-Instruct"},
"HuggingFace":{"base":"https://router.huggingface.co/v1","key":"HF_TOKEN","model":"Qwen/Qwen2.5-7B-Instruct-1M"},
"LLM7":{"base":"https://api.llm7.io/v1","key":"LLM7_API_KEY","model":"gpt-oss-120b"},
"AnyAPI":{"base":"https://api.anyapi.ai/v1","key":"ANYAPI_API_KEY","model":"gpt-oss-120b"},
"ArliAI":{"base":"https://api.arliai.com/v1","key":"ARLIAI_API_KEY","model":"Qwen2.5-72B-Instruct"},
"OllamaCloud":{"base":"https://ollama.com/v1","key":"OLLAMA_API_KEY","model":"gpt-oss:20b"},
"ModelScope":{"base":"https://api-inference.modelscope.cn/v1","key":"MODELSCOPE_API_KEY","model":"Qwen/Qwen3-Next-80B-A3B-Instruct"},
"Together":{"base":"https://api.together.ai/v1","key":"TOGETHER_API_KEY","model":"Qwen/Qwen3.5-9B"},
"OpenRouter":{"base":"https://openrouter.ai/api/v1","key":"OPENROUTER_API_KEY","model":"openai/gpt-oss-120b:free"},
"CloudflareWorkersAI":{"base":"https://api.cloudflare.com/client/v4","key":"CLOUDFLARE_API_TOKEN","model":"@cf/zai-org/glm-4.7-flash","account_key":"CLOUDFLARE_ACCOUNT_ID"},
}
SLOT_OUTPUT_TOKENS=int(os.environ.get("LONG_SLOT_MAX_OUTPUT_TOKENS","1200"))

def _post(url:str,key:str,body:dict[str,Any],extra_headers:dict[str,str]|None=None,retries:int=3)->dict[str,Any]:
 headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","Accept":"application/json","User-Agent":"aqaaab-ai-router/1.0"}
 if extra_headers: headers.update(extra_headers)
 last=None
 for attempt in range(1,retries+1):
  req=urllib.request.Request(url,data=json.dumps(body).encode(),method="POST",headers=headers)
  try:
   with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode("utf-8","replace"))
  except urllib.error.HTTPError as e:
   payload=e.read().decode("utf-8","replace")[:1200]; last=RuntimeError(f"HTTP {e.code}: {payload}")
   if e.code in {400,401,402,403,404}: raise last
   if e.code not in {408,425,429,500,502,503,504,520,521,522,523,524}: raise last
   if attempt<retries:
    retry_after=e.headers.get("Retry-After")
    try: delay=max(1,min(90,int(float(retry_after)))) if retry_after else min(30,5*(2**(attempt-1)))
    except Exception: delay=min(30,5*(2**(attempt-1)))
    time.sleep(delay)
  except (urllib.error.URLError,TimeoutError) as e:
   last=e
   if attempt<retries: time.sleep(min(20,3*(2**(attempt-1))))
 raise last or RuntimeError("provider request failed")

def _content(data:dict[str,Any])->str:
 value=((data.get("choices") or [{}])[0].get("message") or {}).get("content","")
 if isinstance(value,list):value="".join(str(x.get("text","")) if isinstance(x,dict) else str(x) for x in value)
 if not str(value).strip():raise RuntimeError("empty provider response")
 return str(value)

def _cloudflare_post(model:str,prompt:str)->dict[str,Any]:
 account=os.getenv("CLOUDFLARE_ACCOUNT_ID",""); token=os.getenv("CLOUDFLARE_API_TOKEN","")
 if not account or not token: raise RuntimeError("CloudflareWorkersAI: missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN")
 url=f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
 return _post(url,token,{"messages":[{"role":"system","content":"Return exactly one valid JSON object. No markdown, no prose outside JSON."},{"role":"user","content":prompt}],"max_tokens":SLOT_OUTPUT_TOKENS,"temperature":0.1})

def health_check(name:str)->tuple[bool,str]:
 cfg=PROVIDERS[name]
 if name=="CloudflareWorkersAI":
  if not os.getenv("CLOUDFLARE_ACCOUNT_ID") or not os.getenv("CLOUDFLARE_API_TOKEN"): return False,"missing_api_credentials"
  if os.getenv("ENABLE_CLOUDFLAREWORKERSAI_PROVIDER","false").lower()!="true": return False,"provider_not_enabled"
  try:
   x=_cloudflare_post(os.getenv("CLOUDFLAREWORKERSAI_MODEL",cfg["model"]),"Reply only with OK.")
   return (bool(x.get("success")) and bool((x.get("result") or {}).get("response")),"live_free_inference_ok")
  except Exception as e:return False,f"{type(e).__name__}:{e}"
 key=os.getenv(cfg["key"],"")
 if not key:return False,"missing_api_key"
 if os.getenv(f"ENABLE_{name.upper()}_PROVIDER","false").lower()!="true":return False,"provider_not_enabled"
 try:
  model=os.getenv(f"{name.upper()}_MODEL",cfg["model"]);out=_post(cfg["base"].rstrip("/")+"/chat/completions",key,{"model":model,"messages":[{"role":"user","content":"Reply only with OK."}],"max_tokens":4,"temperature":0});return (bool(_content(out).strip()),"live_inference_ok")
 except Exception as e:return False,f"{type(e).__name__}:{e}"

def generate(name:str,prompt:str)->dict[str,Any]:
 cfg=PROVIDERS[name]
 if name=="CloudflareWorkersAI":
  model=os.getenv("CLOUDFLAREWORKERSAI_MODEL",cfg["model"]); out=_cloudflare_post(model,prompt); value=(out.get("result") or {}).get("response","")
  if not str(value).strip(): raise RuntimeError("CloudflareWorkersAI: empty provider response")
  return {"content":str(value),"model":model,"provider":name}
 key=os.getenv(cfg["key"],"")
 if not key:raise RuntimeError(f"{name}: missing {cfg['key']}")
 if os.getenv(f"ENABLE_{name.upper()}_PROVIDER","false").lower()!="true":raise RuntimeError(f"{name}: provider disabled")
 model=os.getenv(f"{name.upper()}_MODEL",cfg["model"])
 if name=="OpenRouter" and not model.endswith(":free"): raise RuntimeError("OpenRouter: paid-capable model rejected; model must end with :free")
 body={"model":model,"messages":[{"role":"system","content":"Return exactly one valid JSON object. No markdown, no prose outside JSON."},{"role":"user","content":prompt}],"temperature":0.1,"max_tokens":SLOT_OUTPUT_TOKENS}
 if name=="Mistral":body["response_format"]={"type":"json_object"}
 try:out=_post(cfg["base"].rstrip("/")+"/chat/completions",key,body)
 except urllib.error.HTTPError as e:raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:800]}") from e
 return {"content":_content(out),"model":model,"provider":name}

def extend_router(router):
 from ai_router import Provider,_extract
 healthy=[]
 for idx,name in enumerate(PROVIDERS):
  if name=="Mistral" and os.getenv("ENABLE_MISTRAL_LONG_STORY_PROVIDER","false").lower()!="true":
   print("PROVIDER_HEALTH_SKIP provider=Mistral reason=long_story_opt_in_required");continue
  cfg=PROVIDERS[name]; required_key=cfg.get("key")
  if name=="CloudflareWorkersAI":
   if not os.getenv("CLOUDFLARE_ACCOUNT_ID") or not os.getenv(required_key,"") or os.getenv("ENABLE_CLOUDFLAREWORKERSAI_PROVIDER","false").lower()!="true": continue
  elif not os.getenv(required_key) or os.getenv(f"ENABLE_{name.upper()}_PROVIDER","false").lower()!="true": continue
  ok,reason=health_check(name)
  if not ok: print(f"PROVIDER_HEALTH_SKIP provider={name} reason={reason}"); continue
  def call(prompt,name=name):return _extract(generate(name,prompt)["content"])
  healthy.append(Provider(name,["long_story"],5+idx,True,call,model=os.getenv(("CLOUDFLAREWORKERSAI_MODEL" if name=="CloudflareWorkersAI" else f"{name.upper()}_MODEL"),cfg["model"])))
  entry=router.state.setdefault("providers",{}).setdefault(name,{"status":"UNKNOWN","failures":0,"calls":0,"estimated_tokens":0,"cooldown_until":0,"last_error":""})
  entry["cooldown_until"]=0; entry["status"]="HEALTHY"; entry["last_health_reason"]=reason
  print(f"PROVIDER_HEALTH_PASS provider={name} cooldown_cleared=true")
 state_path=Path(os.environ.get("RUN_DIR","data/daily-production"))/"ai_router"/"state.json"
 state_path.parent.mkdir(parents=True,exist_ok=True); state_path.write_text(json.dumps(router.state,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 router.providers=[p for p in router.providers if p.name not in {x.name for x in healthy}]+healthy
 router.providers.sort(key=lambda p:p.priority); return router
