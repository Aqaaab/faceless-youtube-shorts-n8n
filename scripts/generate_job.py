#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,urllib.request
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'; OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
CF_MODEL=os.environ.get('CLOUDFLARE_MODEL','@cf/meta/llama-3.3-70b-instruct-fp8-fast')
GROQ_MODEL=os.environ.get('GROQ_TEXT_MODEL',os.environ.get('GROQ_VISION_MODEL','qwen/qwen3.6-27b')); TOGETHER_MODEL=os.environ.get('TOGETHER_TEXT_MODEL',os.environ.get('TOGETHER_VISION_MODEL','Qwen/Qwen3.5-9B'))
PROMPT='''Create ONE factual, high-retention YouTube Shorts story in English with accurate Modern Standard Arabic translations. Return ONLY JSON. Exactly 5 scenes. Each scene has text_en, text_ar, visual_subject, pexels_query. Each English scene 13-19 words; total 75-95 words. No CTA or absolute claims. visual_subject is a concrete 1-3 word physical subject. pexels_query directly searches that subject and may add one concrete shot word. Keep the same core subject while varying shot concepts. text_ar faithfully preserves every qualifier. script is all text_en joined by spaces; narration equals script; subtitle_ar is all text_ar joined by spaces. Title English-only <=85 chars ending #Shorts. Description English-only with exactly 5 hashtags. Tags are 8-12 lowercase ASCII tokens.'''
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
  try:
   from json_repair import repair_json; x=repair_json(raw,return_objects=True); return x if isinstance(x,dict) else (_ for _ in ()).throw(ValueError('not object'))
  except Exception as e: raise ValueError('invalid JSON') from e
def post(url,body,headers):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,'User-Agent':'faceless-youtube-shorts/1.0','Accept':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode('utf-8','replace'))
def openrouter(k):
 x=post(OPENROUTER_URL,{'model':OPENROUTER_MODEL,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT}],'temperature':.1,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {k}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts'}); return extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
def gemini(k):
 x=post(GEMINI_URL,{'contents':[{'role':'user','parts':[{'text':PROMPT}]}],'generationConfig':{'temperature':.1,'maxOutputTokens':5000,'responseMimeType':'application/json'}},{'x-goog-api-key':k,'Content-Type':'application/json'}); return extract(''.join(str(p.get('text','')) for p in (((x.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
def cf(k,a):
 x=post(f'https://api.cloudflare.com/client/v4/accounts/{a}/ai/run/{CF_MODEL}',{'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT}],'temperature':.1,'max_tokens':5000},{'Authorization':f'Bearer {k}','Content-Type':'application/json'}); c=(x.get('result') or {}).get('response'); return c if isinstance(c,dict) else extract(c or '')
def compat(provider,k,model):
 url='https://api.groq.com/openai/v1/chat/completions' if provider=='Groq' else 'https://api.together.ai/v1/chat/completions'; x=post(url,{'model':model,'messages':[{'role':'system','content':'Return exactly one JSON object.'},{'role':'user','content':PROMPT}],'temperature':.1,'max_tokens':5000,'response_format':{'type':'json_object'}},{'Authorization':f'Bearer {k}','Content-Type':'application/json'}); return extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
def ground(v,q):
 vw=[w for w in re.sub(r'[^A-Za-z0-9 -]',' ',v.lower()).split() if w not in GENERIC]; qw=[w for w in re.sub(r'[^A-Za-z0-9 -]',' ',q.lower()).split() if w not in GENERIC and w not in vw]
 if not vw: raise ValueError('weak visual_subject')
 return ' '.join((vw[:3]+(qw[:1] if len(vw)==1 else []))[:3])
def normalize(d):
 sc=d.get('scenes')
 if not isinstance(sc,list) or len(sc)!=5: raise ValueError('exactly 5 scenes required')
 ens=[]; ars=[]
 for i,s in enumerate(sc,1):
  en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); v=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip()
  if not en or not ar or not v or not q: raise ValueError(f'scene {i} missing fields')
  if not 13<=word_count(en)<=19 or re.search(r'[\u0600-\u06ff]',en) or not re.search(r'[\u0600-\u06ff]',ar): raise ValueError(f'scene {i} language/word contract failed')
  if ABS_EN.search(en) or ABS_AR.search(ar): raise ValueError(f'scene {i} unsupported absolute claim')
  s['pexels_query']=ground(v,q); ens.append(en); ars.append(ar)
 script=' '.join(ens)
 if not 75<=word_count(script)<=95: raise ValueError('total narration word count invalid')
 d['script']=script; d['narration']=script; d['subtitle_ar']=' '.join(ars); d['hook']=ens[0]
 title=str(d.get('title','')).strip(); d['title']=title if title and len(title)<=85 and title.endswith('#Shorts') and not re.search(r'[\u0600-\u06ff]',title) else 'The Fact You Did Not Expect About Honeybees #Shorts'
 d['description']='A surprising science fact explained in seconds. #Science #Facts #Nature #Animals #Shorts'
 tags=[]
 for t in re.findall(r'[a-z0-9]+',' '.join([str(d.get('topic','')),str(d.get('category',''))]+[str(s.get('visual_subject','')) for s in sc]).lower())+['science','facts','nature','animals','learning','shorts']:
  if t not in tags and t not in {'the','and','of','for','a','an','to','in','with'}: tags.append(t)
 d['tags']=tags[:12]
 if len(d['tags'])<8: raise ValueError('not enough tags')
 return d
def fallback():
 return normalize({'provider':'deterministic-fallback','title':'How Honeybees Give Directions Without Words #Shorts','topic':'Honeybee communication','category':'Science','scenes':[
 {'text_en':'A honeybee can tell its colony exactly where food is hidden without making a sound.','text_ar':'تستطيع نحلة العسل أن تخبر مستعمرتها بمكان الطعام المختبئ بدقة من دون إصدار صوت.','visual_subject':'honeybee','pexels_query':'honeybee'},
 {'text_en':'A worker bee performs a waggle dance, using movement to communicate the direction of a food source.','text_ar':'تؤدي النحلة العاملة رقصة اهتزاز، مستخدمة الحركة للتواصل بشأن اتجاه مصدر الطعام.','visual_subject':'honeybee','pexels_query':'honeybee dance'},
 {'text_en':'The dance angle relates to the sun, helping other bees understand which direction they should fly.','text_ar':'ترتبط زاوية الرقصة بالشمس، ما يساعد النحل الآخر على فهم الاتجاه الذي ينبغي أن يطير نحوه.','visual_subject':'honeybee','pexels_query':'honeybee flight'},
 {'text_en':'The dance duration and repetition also provide information about the approximate distance to the food.','text_ar':'كما توفر مدة الرقصة وتكرارها معلومات عن المسافة التقريبية للوصول إلى الطعام.','visual_subject':'honeybee','pexels_query':'honeybee dance'},
 {'text_en':'One tiny insect can therefore guide an entire colony toward useful resources through movement alone.','text_ar':'وهكذا تستطيع حشرة صغيرة توجيه مستعمرة كاملة نحو موارد مفيدة من خلال الحركة وحدها.','visual_subject':'honeybee','pexels_query':'honeybee dance'}]})
def main():
 providers=[]
 if os.getenv('OPENROUTER_API_KEY'): providers.append(('OpenRouter',lambda:openrouter(os.environ['OPENROUTER_API_KEY'])))
 if os.getenv('GEMINI_API_KEY'): providers.append(('Gemini',lambda:gemini(os.environ['GEMINI_API_KEY'])))
 if os.getenv('CLOUDFLARE_API_TOKEN') and os.getenv('CLOUDFLARE_ACCOUNT_ID'): providers.append(('Cloudflare',lambda:cf(os.environ['CLOUDFLARE_API_TOKEN'],os.environ['CLOUDFLARE_ACCOUNT_ID'])))
 if os.getenv('GROQ_API_KEY'): providers.append(('Groq',lambda:compat('Groq',os.environ['GROQ_API_KEY'],GROQ_MODEL)))
 if os.getenv('TOGETHER_API_KEY'): providers.append(('Together',lambda:compat('Together',os.environ['TOGETHER_API_KEY'],TOGETHER_MODEL)))
 for name,fn in providers:
  try:
   print(f'AI provider={name} attempt=1/1'); d=normalize(fn()); d['provider']=name; (RUN_DIR/'job.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n'); print(f'job.json written: provider={name}; topic={d.get("topic")}; words={word_count(d["script"])}'); return 0
  except Exception as e: print(f'{name} failed: {e}')
 if os.getenv('ALLOW_DETERMINISTIC_FALLBACK','true').lower()!='true': raise SystemExit('All AI providers failed and deterministic fallback is disabled')
 d=fallback(); (RUN_DIR/'job.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n'); print(f'All AI providers unavailable; using deterministic fallback. job.json written: provider=deterministic-fallback; topic={d["topic"]}; words={word_count(d["script"])}'); return 0
if __name__=='__main__': raise SystemExit(main())