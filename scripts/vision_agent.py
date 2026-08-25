#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, json, os, urllib.error, urllib.request
from pathlib import Path

CACHE_DIR=Path(os.environ.get('VISION_CACHE_DIR','data/vision_cache'))
STATE=CACHE_DIR/'provider_state.json'
BLOCKRUN_MODELS=[os.environ.get('BLOCKRUN_VISION_MODEL','nvidia/nemotron-nano-12b-v2-vl'),'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning']
HF_MODELS=[os.environ.get('HF_VISION_MODEL','Qwen/Qwen2.5-VL-3B-Instruct')]

def _state():
 CACHE_DIR.mkdir(parents=True,exist_ok=True)
 try:return json.loads(STATE.read_text())
 except:return {'requests':0,'providers':{}}
def _save(s):
 CACHE_DIR.mkdir(parents=True,exist_ok=True);STATE.write_text(json.dumps(s,indent=2))
def _json(t):
 t=(t or '').strip();a,b=t.find('{'),t.rfind('}')
 if a<0 or b<=a:raise RuntimeError('vision provider returned no JSON')
 try:return json.loads(t[a:b+1])
 except Exception:
  from json_repair import repair_json
  return repair_json(t[a:b+1],return_objects=True)
def _content(prompt,images):return [{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(Path(p).read_bytes()).decode()}} for p in images]
def _post(url,body,headers,timeout=75):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Accept':'application/json',**headers},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
 except urllib.error.HTTPError as e:raise RuntimeError(f'HTTP {e.code}: '+e.read().decode('utf-8','replace')[:600]) from e
 except (TimeoutError,urllib.error.URLError) as e:raise RuntimeError(f'vision request failed: {e}') from e
def _extract(x):
 if isinstance(x,str):return x
 c=x.get('choices') or [] if isinstance(x,dict) else []
 if c and isinstance(c[0],dict):
  m=c[0].get('message') or {};v=m.get('content') if isinstance(m,dict) else None
  if isinstance(v,str):return v
  if isinstance(v,list):return ''.join(i.get('text','') for i in v if isinstance(i,dict))
 if isinstance(x,dict) and isinstance(x.get('response'),str):return x['response']
 raise RuntimeError('unexpected vision response shape')
def _blockrun(prompt,images,model):
 x=_post('https://blockrun.ai/api/v1/chat/completions',{'model':model,'messages':[{'role':'system','content':'You are a strict visual QA engine. Return ONLY JSON with keys selected, score, semantic_score, reason.'},{'role':'user','content':_content(prompt,images)}],'temperature':0,'max_tokens':800},{'Authorization':'Bearer not-needed-for-free-models'});return _json(_extract(x))
def _hf(prompt,images,key,model):
 x=_post('https://router.huggingface.co/v1/chat/completions',{'model':model,'messages':[{'role':'system','content':'You are a strict visual QA engine. Return ONLY JSON with keys selected, score, semantic_score, reason.'},{'role':'user','content':_content(prompt,images)}],'temperature':0,'max_tokens':800},{'Authorization':f'Bearer {key}'});return _json(_extract(x))
def evaluate(prompt,images,kind='qa'):
 images=[str(x) for x in images];digest=hashlib.sha256(prompt.encode()+b'|'+b'|'.join(Path(p).read_bytes() for p in images)).hexdigest();cache=CACHE_DIR/f'{digest}.json'
 if cache.exists():
  try:x=json.loads(cache.read_text());x['cached']=True;x['kind']=kind;return x
  except:pass
 s=_state();errors=[];providers=[]
 for model in BLOCKRUN_MODELS: providers.append((f'blockrun:{model}',lambda model=model:_blockrun(prompt,images,model)))
 if os.environ.get('HF_TOKEN','').strip():
  for model in HF_MODELS: providers.append((f'huggingface:{model}',lambda model=model:_hf(prompt,images,os.environ['HF_TOKEN'].strip(),model)))
 max_requests=int(os.environ.get('VISION_MAX_REQUESTS_PER_RUN','32'))
 for name,fn in providers:
  try:
   if s.get('requests',0)>=max_requests:raise RuntimeError('vision request budget exhausted')
   s['requests']=s.get('requests',0)+1;x=fn()
   if not isinstance(x,dict):raise RuntimeError('provider result is not JSON object')
   x['provider']=name;x['cached']=False;x['kind']=kind;cache.write_text(json.dumps(x,ensure_ascii=False,indent=2));_save(s);return x
  except Exception as e:
   errors.append(f'{name}: {e}');s.setdefault('providers',{}).setdefault(name,{})['last_error']=str(e)[:1000];_save(s)
 raise RuntimeError('Vision Agent unavailable: '+' | '.join(errors))
def stats():
 s=_state();return {'requests':s.get('requests',0),'max_requests':int(os.environ.get('VISION_MAX_REQUESTS_PER_RUN','32')),'providers':s.get('providers',{}),'cache_files':len(list(CACHE_DIR.glob('*.json')))}
