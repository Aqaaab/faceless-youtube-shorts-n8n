#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, urllib.error, urllib.request
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OR_URL='https://openrouter.ai/api/v1/chat/completions'; OR_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
GEM_URL=f"https://generativelanguage.googleapis.com/v1beta/models/{os.environ.get('GEMINI_MODEL','gemini-3.6-flash')}:generateContent"; GEM_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
CF_MODEL=os.environ.get('CLOUDFLARE_MODEL','@cf/meta/llama-3.3-70b-instruct-fp8-fast')
PROMPT='''Create ONE high-retention, factual YouTube Shorts story in English with accurate Modern Standard Arabic subtitles. Return ONLY JSON. Required top-level fields: hook,script,subtitle_ar,title,description,tags,query,topic,category,scenes. Exactly 5 scenes. Each scene fields: text_en,text_ar,visual_subject,pexels_query. Total English narration 65-90 words; each scene 10-22 words. Scene 1 must be a strong curiosity hook: no greetings, no "today", no "did you know", no generic introduction. Use a concrete surprising fact that can be verified; never invent numbers or claims. Scene 2 develops the mystery, scenes 3-4 explain it, scene 5 gives a memorable payoff without a forced CTA. Every Arabic scene must faithfully translate its English scene. visual_subject must be the literal main thing the viewer should see. pexels_query must be 1-3 concrete English words naming that subject, optionally with one visual modifier such as closeup or hive; never generic words like nature, background, person, landscape, object. The five scenes must have visual variety while staying on the same subject. script must equal all text_en joined by single spaces. subtitle_ar must equal all text_ar joined by single spaces. Title <=85 chars, English only, curiosity-driven, ends #Shorts. Description: 2 concise English sentences + exactly 5 hashtags. Tags: 8-12 lowercase English tokens. No emojis. Metadata must contain no Arabic.'''
def words(s): return len(re.findall(r"\b[\w'-]+\b",s))
def json_obj(t):
 t=(t or '').strip().replace('\ufeff',''); a,b=t.find('{'),t.rfind('}')
 if a<0 or b<=a: raise ValueError('no JSON object')
 raw=t[a:b+1]
 try: return json.loads(raw)
 except Exception as first:
  try:
   from json_repair import repair_json
   x=repair_json(raw,return_objects=True)
   if isinstance(x,dict): return x
  except Exception: pass
  raise ValueError('invalid JSON') from first
def post(url,body,headers):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode('utf-8','replace'))
def openrouter(key):
 p=post(OR_URL,{'model':OR_MODEL,'messages':[{'role':'system','content':'Return JSON only.'},{'role':'user','content':PROMPT}],'temperature':.25,'max_tokens':4000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {key}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts'})
 c=(p.get('choices') or [{}])[0].get('message',{}).get('content',''); return json_obj(c)
def gemini(key):
 p=post(GEM_URL,{'contents':[{'role':'user','parts':[{'text':PROMPT}]}],'generationConfig':{'temperature':.25,'maxOutputTokens':4000,'responseMimeType':'application/json'}},{'x-goog-api-key':key,'Content-Type':'application/json'})
 parts=(((p.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []); return json_obj(''.join(x.get('text','') for x in parts if isinstance(x,dict)))
def cloudflare(key,account):
 url=f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CF_MODEL}'
 p=post(url,{'messages':[{'role':'system','content':'Return JSON only.'},{'role':'user','content':PROMPT}],'temperature':.25,'max_tokens':4000},{'Authorization':f'Bearer {key}','Content-Type':'application/json'})
 c=(p.get('result') or {}).get('response'); return c if isinstance(c,dict) else json_obj(c or '')
def validate(d):
 req=['hook','script','subtitle_ar','title','description','tags','query','topic','category','scenes']
 for k in req:
  if k not in d: raise ValueError('missing '+k)
 sc=d['scenes']
 if not isinstance(sc,list) or len(sc)!=5: raise ValueError('exactly 5 scenes required')
 en=[]; ar=[]
 for i,s in enumerate(sc,1):
  if not isinstance(s,dict): raise ValueError(f'scene {i} invalid')
  for k in ('text_en','text_ar','visual_subject','pexels_query'):
   if not isinstance(s.get(k),str) or not s[k].strip(): raise ValueError(f'scene {i} missing {k}')
  n=words(s['text_en'])
  if not 10<=n<=22: raise ValueError(f'scene {i} has {n} words')
  if re.search('[\\u0600-\\u06ff]',s['text_en']): raise ValueError(f'scene {i} English contains Arabic')
  if not re.search('[\\u0600-\\u06ff]',s['text_ar']): raise ValueError(f'scene {i} Arabic missing')
  q=s['pexels_query'].strip(); qw=q.split()
  if not 1<=len(qw)<=3 or any(x.lower() in {'nature','background','abstract','person','people','thing','object','landscape','scene'} for x in qw): raise ValueError(f'scene {i} has weak visual query')
  en.append(s['text_en'].strip()); ar.append(s['text_ar'].strip())
 d['script']=' '.join(en); d['subtitle_ar']=' '.join(ar); d['hook']=en[0]
 total=words(d['script'])
 if not 65<=total<=90: raise ValueError(f'narration has {total} words')
 if len(d['title'])>85 or not d['title'].endswith('#Shorts'): raise ValueError('bad title')
 if re.search('[\\u0600-\\u06ff]',''.join(str(d[k]) for k in ('title','description','query','topic','category'))): raise ValueError('Arabic in metadata')
 if not isinstance(d['tags'],list) or not 8<=len(d['tags'])<=12: raise ValueError('bad tags')
 d['tags']=[str(x).lower().strip() for x in d['tags']]
 if any(not re.fullmatch('[a-z0-9_-]+',x) for x in d['tags']): raise ValueError('invalid tag')
 return d
def fallback():
 sc=[
 {'text_en':'A honeybee can tell its colony where food is hiding without saying a word.','text_ar':'تستطيع نحلة العسل إخبار مستعمرتها بمكان الطعام المختبئ من دون أن تنطق بكلمة.','visual_subject':'honeybee','pexels_query':'honeybee'},
 {'text_en':'It does this with a waggle dance that points other bees toward the food source.','text_ar':'تفعل ذلك برقصة اهتزاز توجه النحل الآخر نحو مصدر الطعام.','visual_subject':'bee dance','pexels_query':'bee dance'},
 {'text_en':'The angle of the dance helps communicate direction relative to the sun.','text_ar':'تساعد زاوية الرقصة على نقل الاتجاه بالنسبة إلى الشمس.','visual_subject':'honeybee hive','pexels_query':'honeybee hive'},
 {'text_en':'The length and repetition of the movement also carry information about the journey.','text_ar':'كما تحمل مدة الحركة وتكرارها معلومات عن الرحلة المطلوبة.','visual_subject':'bees communicating','pexels_query':'bees hive'},
 {'text_en':'One tiny insect can therefore share a route with an entire colony.','text_ar':'وهكذا تستطيع حشرة صغيرة مشاركة طريق مع مستعمرة كاملة.','visual_subject':'honeybees','pexels_query':'honeybees flowers'}]
 d={'hook':sc[0]['text_en'],'script':'','subtitle_ar':'','title':'How Honeybees Give Directions Without Words #Shorts','description':'Honeybees communicate food directions through a remarkable waggle dance. Their movements help other workers navigate to resources. #Honeybees #Bees #Science #Nature #AnimalFacts','tags':['honeybees','bees','waggle-dance','science','nature','biology','insects','animalfacts','communication'],'query':'honeybee','topic':'Honeybee communication','category':'Science','scenes':sc,'provider':'deterministic-fallback'}
 return validate(d)
def main():
 errs=[]
 providers=[]
 if os.environ.get('OPENROUTER_API_KEY','').strip(): providers.append(('OpenRouter',lambda:openrouter(os.environ['OPENROUTER_API_KEY'].strip())))
 if os.environ.get('GEMINI_API_KEY','').strip(): providers.append(('Gemini',lambda:gemini(os.environ['GEMINI_API_KEY'].strip())))
 if os.environ.get('CLOUDFLARE_API_TOKEN','').strip() and os.environ.get('CLOUDFLARE_ACCOUNT_ID','').strip(): providers.append(('Cloudflare',lambda:cloudflare(os.environ['CLOUDFLARE_API_TOKEN'].strip(),os.environ['CLOUDFLARE_ACCOUNT_ID'].strip())))
 for name,fn in providers:
  print(f'AI provider={name} attempt=1/1',flush=True)
  try:
   d=validate(fn()); d['provider']=name; print(f'AI provider={name} succeeded',flush=True); break
  except urllib.error.HTTPError as e:
   detail=e.read().decode('utf-8','replace')[:300]; errs.append(f'{name} HTTP {e.code}: {detail}'); print(errs[-1],flush=True)
   d=None
  except Exception as e: errs.append(f'{name}: {e}'); print(errs[-1],flush=True); d=None
 else: d=None
 if d is None:
  print('All AI providers unavailable; using deterministic fallback.',flush=True); d=fallback()
 out=RUN_DIR/'job.json'; out.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f"job.json written: {out}; provider={d.get('provider')}; topic={d.get('topic')}; words={words(d['script'])}",flush=True)
if __name__=='__main__': main()
