#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, random, urllib.error, urllib.request
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'; OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
CF_MODEL=os.environ.get('CLOUDFLARE_MODEL','@cf/meta/llama-3.3-70b-instruct-fp8-fast')
GROQ_MODEL=os.environ.get('GROQ_TEXT_MODEL',os.environ.get('GROQ_VISION_MODEL','qwen/qwen3.6-27b')); TOGETHER_MODEL=os.environ.get('TOGETHER_TEXT_MODEL',os.environ.get('TOGETHER_VISION_MODEL','Qwen/Qwen3.5-9B'))
MIN_SCENES=int(os.environ.get('MIN_SCENES','5')); MAX_SCENES=int(os.environ.get('MAX_SCENES','10'))

PROMPT=f'''Create ONE factual, high-retention YouTube Shorts story in English with accurate Modern Standard Arabic translations. Return ONLY one JSON object. Create {MIN_SCENES} to {MAX_SCENES} scenes, preferably 6-8 when useful. Each scene has text_en, text_ar, visual_subject, pexels_query. Each English scene is 8-18 words; total 80-110 words. No CTA and no absolute claims. visual_subject is a concrete 1-3 word physical subject. pexels_query is 1-5 concrete words and keeps the core subject while adding an action/context when useful. text_ar faithfully preserves every qualifier. script is all text_en joined by spaces; narration equals script; subtitle_ar is all text_ar joined by spaces. Title is English-only, <=85 characters, and ends with #Shorts. Description is English-only, 2-3 sentences that specifically explain the topic and key fact, followed by exactly 5 relevant hashtags. Tags are 8-12 lowercase ASCII tokens relevant to the topic.'''
REPAIR_PROMPT=f'''Return ONLY a valid JSON object for a YouTube Short. This is a repair attempt. Use exactly {MIN_SCENES} scenes if possible, never fewer than {MIN_SCENES} or more than {MAX_SCENES}. Every scene MUST contain text_en (8-18 English words), text_ar (Arabic translation), visual_subject (1-3 concrete physical words), and pexels_query (1-5 concrete words). Total English narration MUST be 80-110 words. Include a specific English title <=85 chars ending #Shorts, a topic, category, a specific 2-3 sentence English description followed by exactly 5 hashtags, and 8-12 lowercase ASCII tags. Return no markdown and no prose outside JSON.''' 
GENERIC={'nature','background','abstract','object','thing','scene','person','people','landscape','random','sun','sky','light','ancient','historical','modern','old','futuristic'}
ABS_EN=re.compile(r'\b(always|never|the only|forever|immortal|never spoils|never expires|lasts forever|completely safe|100%)\b',re.I); ABS_AR=re.compile(r'(دائماً|دائمًا|أبداً|أبدًا|للأبد|إلى الأبد|الوحيد|الوحيدة|لا يفسد|لا تنتهي صلاحيته|آمن تماماً|آمن تمامًا|100٪)')

def word_count(t): return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",str(t)))
def extract(t):
 t=(t or '').strip().replace('\ufeff',''); a,b=t.find('{'),t.rfind('}')
 if a<0 or b<=a: raise ValueError('no JSON object')
 raw=t[a:b+1]
 try:
  x=json.loads(raw); return x if isinstance(x,dict) else (_ for _ in ()).throw(ValueError('not object'))
 except Exception:
  from json_repair import repair_json
  x=repair_json(raw,return_objects=True)
  if not isinstance(x,dict): raise ValueError('invalid JSON')
  return x

def post(url,body,headers,retries=3):
 last=None
 for attempt in range(1,retries+1):
  try:
   req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,'User-Agent':'faceless-youtube-shorts/1.0','Accept':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode('utf-8','replace'))
  except urllib.error.HTTPError as e:
   body_text=e.read().decode('utf-8','replace')[:500]; last=RuntimeError(f'HTTP {e.code}: {body_text}')
   if e.code not in {408,425,429,500,502,503,504}: raise last
  except (urllib.error.URLError,TimeoutError) as e: last=e
  if attempt<retries:
   delay=min(30,2**(attempt-1)*2)+random.uniform(0,.8); print(f'API retry {attempt+1}/{retries} after {delay:.1f}s'); time.sleep(delay)
 raise last or RuntimeError('request failed')

def openrouter(k,prompt):
 x=post(OPENROUTER_URL,{'model':OPENROUTER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object. No markdown.'},{'role':'user','content':prompt}],'temperature':.1,'max_tokens':5000},{'Authorization':f'Bearer {k}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts'})
 return extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
def gemini(k,prompt):
 x=post(GEMINI_URL,{'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'temperature':.1,'maxOutputTokens':5000,'responseMimeType':'application/json'}},{'x-goog-api-key':k,'Content-Type':'application/json'})
 return extract(''.join(str(p.get('text','')) for p in (((x.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
def cf(k,a,prompt):
 x=post(f'https://api.cloudflare.com/client/v4/accounts/{a}/ai/run/{CF_MODEL}',{'messages':[{'role':'system','content':'Return exactly one JSON object. No markdown.'},{'role':'user','content':prompt}],'temperature':.1,'max_tokens':5000},{'Authorization':f'Bearer {k}','Content-Type':'application/json'})
 c=(x.get('result') or {}).get('response'); return c if isinstance(c,dict) else extract(c or '')
def compat(provider,k,model,prompt):
 url='https://api.groq.com/openai/v1/chat/completions' if provider=='Groq' else 'https://api.together.ai/v1/chat/completions'
 # Do not force response_format: some compatible endpoints reject it with HTTP 400.
 x=post(url,{'model':model,'messages':[{'role':'system','content':'Return exactly one JSON object. No markdown.'},{'role':'user','content':prompt}],'temperature':.1,'max_tokens':5000},{'Authorization':f'Bearer {k}','Content-Type':'application/json'})
 return extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))

def ground(v,q):
 vw=[w for w in re.sub(r'[^A-Za-z0-9 -]',' ',v.lower()).split() if w not in GENERIC]; qw=[w for w in re.sub(r'[^A-Za-z0-9 -]',' ',q.lower()).split() if w not in GENERIC and w not in vw]
 if not vw: raise ValueError('weak visual_subject')
 return ' '.join((vw[:3]+qw[:2])[:5])

def publication_metadata(d,sc):
 topic=str(d.get('topic') or d.get('query') or sc[0].get('visual_subject') or 'Science').strip()
 topic=re.sub(r'\s+',' ',topic)
 clean=re.sub(r'[^A-Za-z0-9 ,:!?\-]','',topic).strip(' -,:') or 'Science'
 title=str(d.get('title') or '').strip()
 if not title or len(title)>85 or not title.endswith('#Shorts') or re.search(r'[\u0600-\u06ff]',title):
  title=f"{clean[:68].rstrip()} — What You Need To Know #Shorts"
  if len(title)>85: title=f"{clean[:55].rstrip()} Explained #Shorts"
 hook=re.sub(r'\s+',' ',str(sc[0].get('text_en','')).strip())
 body=re.sub(r'\s+',' ',str(d.get('description') or '').strip())
 if not body or body.startswith('A surprising science fact explained'):
  body=f"This Short explains {clean.lower()} and the key fact behind it. {hook}"
  body=body[:850]
 tags=[]
 for raw in [topic,d.get('category',''),'science','facts','explained','education','shorts']+[s.get('visual_subject','') for s in sc]:
  for tag in re.findall(r'[a-z0-9]+',str(raw).lower()):
   if tag not in {'the','and','of','for','a','an','to','in','with'} and tag not in tags: tags.append(tag)
 d['topic']=topic; d['title']=title; d['description']=body.rstrip()+('' if body.rstrip().endswith(tuple('#')) else '')+' #'+(''.join(re.findall(r'[A-Za-z]+',clean)[:1]) or 'Science')+' #Facts #Explained #Education #Shorts'; d['description']=re.sub(r'\s+',' ',d['description']); d['tags']=tags[:12]
 while len(d['tags'])<8: d['tags'].append(['learning','knowledge','discovery','science'][len(d['tags'])%4])
 return d

def normalize(d):
 sc=d.get('scenes')
 if not isinstance(sc,list) or not MIN_SCENES<=len(sc)<=MAX_SCENES: raise ValueError(f'scene count must be {MIN_SCENES}-{MAX_SCENES}')
 ens=[]; ars=[]
 for i,s in enumerate(sc,1):
  en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); v=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip()
  if not en or not ar or not v or not q: raise ValueError(f'scene {i} missing fields')
  if not 8<=word_count(en)<=18 or re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language/word contract failed')
  if ABS_EN.search(en) or ABS_AR.search(ar): raise ValueError(f'scene {i} unsupported absolute claim')
  s['pexels_query']=ground(v,q); ens.append(en); ars.append(ar)
 script=' '.join(ens)
 if not 80<=word_count(script)<=110: raise ValueError('total narration word count invalid')
 d['script']=script; d['narration']=script; d['subtitle_ar']=' '.join(ars); d['hook']=ens[0]; d['scene_count']=len(sc)
 d=publication_metadata(d,sc)
 if len(d['tags'])<8: raise ValueError('not enough tags')
 return d

def fallback():
 return normalize({'provider':'deterministic-fallback','title':'How Honeybees Give Directions Without Words #Shorts','topic':'Honeybee communication','category':'Science','scenes':[
 {'text_en':'A honeybee can tell its colony where food is hidden without making a sound or spoken signal.','text_ar':'تستطيع نحلة العسل أن تخبر مستعمرتها بمكان الطعام المختبئ من دون إصدار صوت أو إشارة كلامية.','visual_subject':'honeybee','pexels_query':'honeybee'},
 {'text_en':'A worker bee performs a waggle dance, using precise movement to communicate where a useful food source lies.','text_ar':'تؤدي النحلة العاملة رقصة اهتزاز مستخدمة حركة دقيقة للتواصل بشأن مكان مصدر غذاء مفيد.','visual_subject':'honeybee','pexels_query':'honeybee dance'},
 {'text_en':'The dance angle relates to the sun, helping other bees understand the direction they should fly.','text_ar':'ترتبط زاوية الرقصة بالشمس، ما يساعد النحل الآخر على فهم الاتجاه الذي ينبغي أن يطير نحوه.','visual_subject':'honeybee','pexels_query':'honeybee flight'},
 {'text_en':'The dance duration also provides information about the approximate distance between the colony and the food.','text_ar':'كما توفر مدة الرقصة معلومات عن المسافة التقريبية بين المستعمرة والطعام.','visual_subject':'honeybee','pexels_query':'honeybee dance'},
 {'text_en':'So one tiny insect can guide many others through movement alone, turning a simple dance into directions.','text_ar':'وهكذا تستطيع حشرة صغيرة توجيه حشرات أخرى كثيرة من خلال الحركة وحدها، وتحويل رقصة بسيطة إلى تعليمات.','visual_subject':'honeybee','pexels_query':'honeybee colony'}]})

def main():
 providers=[]
 if os.getenv('OPENROUTER_API_KEY'): providers.append(('OpenRouter',lambda p:openrouter(os.environ['OPENROUTER_API_KEY'],p)))
 if os.getenv('GEMINI_API_KEY'): providers.append(('Gemini',lambda p:gemini(os.environ['GEMINI_API_KEY'],p)))
 if os.getenv('CLOUDFLARE_API_TOKEN') and os.getenv('CLOUDFLARE_ACCOUNT_ID'): providers.append(('Cloudflare',lambda p:cf(os.environ['CLOUDFLARE_API_TOKEN'],os.environ['CLOUDFLARE_ACCOUNT_ID'],p)))
 if os.getenv('GROQ_API_KEY'): providers.append(('Groq',lambda p:compat('Groq',os.environ['GROQ_API_KEY'],GROQ_MODEL,p)))
 if os.getenv('TOGETHER_API_KEY'): providers.append(('Together',lambda p:compat('Together',os.environ['TOGETHER_API_KEY'],TOGETHER_MODEL,p)))
 if not providers: raise SystemExit('No AI provider credentials are configured; production fallback is disabled')
 for name,fn in providers:
  for attempt,prompt in enumerate((PROMPT,REPAIR_PROMPT),1):
   try:
    print(f'AI provider={name} attempt={attempt}/2'); d=normalize(fn(prompt)); d['provider']=name; (RUN_DIR/'job.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n'); print(f'job.json written: provider={name}; topic={d.get("topic")}; scenes={d["scene_count"]}; words={word_count(d["script"])}'); return 0
   except Exception as e: print(f'{name} attempt {attempt} failed: {e}')
 raise SystemExit('All configured AI providers failed; deterministic fallback is disabled for production')
if __name__=='__main__': raise SystemExit(main())
