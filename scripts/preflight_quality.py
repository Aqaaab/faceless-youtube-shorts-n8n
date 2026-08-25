#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,sys,urllib.error,urllib.parse,urllib.request,time
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); JOB_FILE=RUN_DIR/'job.json'
MIN_SCENES=int(os.environ.get('MIN_SCENES','5')); MAX_SCENES=int(os.environ.get('MAX_SCENES','10')); MIN_WORDS=80; MAX_WORDS=110
BANNED_CTA=re.compile(r'\b(follow for more|subscribe for more|like and subscribe|follow us)\b',re.I)
GENERIC={'nature','background','abstract','object','thing','scene','person','people','landscape','random'}
def words(text:str)->int:return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b",text))
def pexels_probe(query:str)->tuple[bool,str]:
 key=os.environ.get('PEXELS_API_KEY','').strip()
 if not key:return False,'PEXELS_API_KEY missing; Gemini Image fallback remains available'
 params=urllib.parse.urlencode({'query':query,'orientation':'portrait','size':'large','per_page':'3'})
 req=urllib.request.Request('https://api.pexels.com/v1/videos/search?'+params,headers={'Authorization':key,'Accept':'application/json','User-Agent':'faceless-youtube-shorts/6.0'})
 for attempt in range(1,4):
  try:
   with urllib.request.urlopen(req,timeout=30) as r:data=json.loads(r.read().decode('utf-8','replace'))
   return bool(data.get('videos')),'ok' if data.get('videos') else 'no clips'
  except urllib.error.HTTPError as e:
   body=e.read().decode('utf-8','replace')[:300]
   if e.code in {408,425,429,500,502,503,504} and attempt<3:
    time.sleep(2**(attempt-1)); continue
   if e.code in {401,403}:return False,f'Pexels authentication failed HTTP {e.code}: {body}'
   if e.code==429:return False,'Pexels rate limited HTTP 429'
   return False,f'Pexels HTTP {e.code}'
  except Exception as e:
   if attempt<3: time.sleep(2**(attempt-1)); continue
   return False,f'Pexels probe error: {e}'
 return False,'Pexels probe failed'
def main()->int:
 if not JOB_FILE.is_file():print(f'ERROR: missing {JOB_FILE}',file=sys.stderr);return 1
 job=json.loads(JOB_FILE.read_text(encoding='utf-8'));scenes=job.get('scenes') or []
 if not MIN_SCENES<=len(scenes)<=MAX_SCENES:print(f'ERROR: scene count {len(scenes)} outside {MIN_SCENES}-{MAX_SCENES}',file=sys.stderr);return 1
 english=[str(s.get('text_en','')).strip() for s in scenes];arabic=[str(s.get('text_ar','')).strip() for s in scenes];script=' '.join(english);subtitle_ar=' '.join(arabic);count=words(script)
 if not MIN_WORDS<=count<=MAX_WORDS:print(f'ERROR: narration has {count} words; expected {MIN_WORDS}-{MAX_WORDS}',file=sys.stderr);return 1
 if BANNED_CTA.search(script):print('ERROR: forced CTA detected in narration',file=sys.stderr);return 1
 status=[]
 for i,scene in enumerate(scenes,1):
  en=english[i-1];ar=arabic[i-1]
  if not re.search(r'[\u0600-\u06ff]',ar):print(f'ERROR: scene {i} Arabic translation is missing',file=sys.stderr);return 1
  if re.search(r'[\u0600-\u06ff]',en):print(f'ERROR: scene {i} English narration contains Arabic',file=sys.stderr);return 1
  if not 8<=words(en)<=18:print(f'ERROR: scene {i} English narration length is invalid',file=sys.stderr);return 1
  subject=' '.join(str(scene.get('visual_subject','')).lower().split());query=' '.join(str(scene.get('pexels_query','')).lower().split())
  if not subject or not 1<=len(subject.split())<=3:print(f'ERROR: scene {i} visual_subject is invalid: {subject!r}',file=sys.stderr);return 1
  if not query or not 1<=len(query.split())<=5 or any(token in GENERIC for token in query.split()):print(f'ERROR: scene {i} has an invalid Pexels query: {query!r}',file=sys.stderr);return 1
  ok,detail=pexels_probe(query);status.append({'scene':i,'query':query,'available':ok,'detail':detail})
  print(f'Preflight visual scene {i}: Pexels {"PASS" if ok else "fallback"} query={query!r} ({detail})')
 hashtags=re.findall(r'#[A-Za-z0-9]+',str(job.get('description','')))
 if len(hashtags)!=5: print(f'ERROR: description must contain exactly 5 hashtags; found {len(hashtags)}',file=sys.stderr); return 1
 job['script']=script;job['narration']=script;job['subtitle_ar']=subtitle_ar;job['scene_count']=len(scenes);job['quality_preflight']={'passed':True,'word_count':count,'scene_count':len(scenes),'pexels_checked':True,'pexels_status':status,'arabic_only_overlay':True,'visual_fallback_enabled':bool(os.environ.get('GEMINI_IMAGE_API_KEY','').strip())}
 JOB_FILE.write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f'Preflight PASS: {count} narration words, {len(scenes)} scenes; visual fallback enabled={bool(os.environ.get("GEMINI_IMAGE_API_KEY",""))}'); return 0
if __name__=='__main__':raise SystemExit(main())