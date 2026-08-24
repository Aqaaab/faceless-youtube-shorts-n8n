#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,os,re,shutil,subprocess,tempfile,time,urllib.error,urllib.request
from pathlib import Path
PEXELS_URL='https://api.pexels.com/videos/search'
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'; OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
VISION_RETRIES=max(1,int(os.environ.get('VISION_RETRIES','3'))); VISION_BACKOFF=max(1.,float(os.environ.get('VISION_BACKOFF','4')))
SHOT_ROLES={1:'closeup',2:'behavior',3:'flight',4:'hive',5:'feeding'}
def post(url,body,headers,timeout=120):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
def get(url,headers,timeout=120):
 req=urllib.request.Request(url,headers=headers,method='GET')
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
def extract_json(text):
 raw=(text or '').strip().replace('\ufeff',''); a,b=raw.find('{'),raw.rfind('}')
 if a<0 or b<=a: raise RuntimeError('vision model returned no JSON')
 raw=raw[a:b+1]
 try:
  v=json.loads(raw)
  if isinstance(v,dict): return v
 except Exception: pass
 try:
  from json_repair import repair_json
  v=repair_json(raw,return_objects=True)
  if isinstance(v,dict): return v
 except Exception: pass
 raise RuntimeError('invalid vision JSON')
def run(cmd,capture=False):
 r=subprocess.run(cmd,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True); return r.stdout.strip() if capture else ''
def scene_index(output):
 m=re.search(r'source_(\d+)',Path(output).name); return int(m.group(1)) if m else 0
def candidate_frames(video,out):
 out.mkdir(parents=True,exist_ok=True); d=max(float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video)],True) or '0'),1.0); frames=[]
 for idx,ratio in enumerate((.15,.38,.62,.85),1):
  t=max(.05,min(d-.05,d*ratio)); p=out/f'f{idx}.jpg'; run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','6',str(p)]); frames.append(p)
 sheet=out/'sheet.jpg'; args=['ffmpeg','-hide_banner','-loglevel','error','-y']
 for p in frames: args += ['-i',str(p)]
 args += ['-filter_complex','[0:v]scale=270:480[a];[1:v]scale=270:480[b];[2:v]scale=270:480[c];[3:v]scale=270:480[d];[a][b][c][d]hstack=inputs=4','-frames:v','1',str(sheet)]; run(args)
def search_candidates(query,tmp,key):
 import urllib.parse
 params=urllib.parse.urlencode({'query':query,'orientation':'portrait','size':'large','per_page':'20'}); payload=get(f'{PEXELS_URL}?{params}',{'Authorization':key,'Accept':'application/json','User-Agent':'faceless-youtube-shorts/3.0'}); rows=[]
 for v in payload.get('videos',[]):
  files=[f for f in v.get('video_files',[]) if f.get('file_type')=='video/mp4' and f.get('link') and f.get('width') and f.get('height') and int(f['height'])>=int(f['width'])]
  if files:
   files.sort(key=lambda x:x.get('width',0)*x.get('height',0),reverse=True); rows.append((files[0]['link'],int(v.get('id',0))))
  if len(rows)>=10: break
 paths=[]
 for idx,(url,vid) in enumerate(rows,1):
  p=tmp/f'candidate_{idx}_{vid or idx}.mp4'
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'faceless-youtube-shorts/3.0'})
   with urllib.request.urlopen(req,timeout=120) as r:
    with p.open('wb') as pw: shutil.copyfileobj(r,pw)
   if p.stat().st_size>=100000: paths.append((p,vid))
  except Exception: pass
 return paths
def ask_gemini(prompt,sheets,key):
 parts=[{'text':prompt}]+[{'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(p.read_bytes()).decode()}} for p in sheets]; payload=post(GEMINI_URL,{'contents':[{'role':'user','parts':parts}],'generationConfig':{'temperature':0,'maxOutputTokens':1400,'responseMimeType':'application/json'}},{'x-goog-api-key':key,'Content-Type':'application/json'}); return extract_json(''.join(str(p.get('text','')) for p in (((payload.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
def ask_openrouter(prompt,sheets,key):
 content=[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(p.read_bytes()).decode()}} for p in sheets]; payload=post(OPENROUTER_URL,{'model':OPENROUTER_MODEL,'messages':[{'role':'user','content':content}],'temperature':0,'max_tokens':1400},{'Authorization':f'Bearer {key}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts Candidate Selector'}); return extract_json(((payload.get('choices') or [{}])[0].get('message') or {}).get('content',''))
def retryable(e):
 if isinstance(e,urllib.error.HTTPError): return e.code in {408,409,425,429,500,502,503,504}
 s=str(e).lower(); return any(x in s for x in ('429','too many requests','rate limit','timeout','timed out','temporarily unavailable'))
def vision(prompt,sheets):
 providers=[]; g=os.environ.get('GEMINI_API_KEY','').strip(); o=os.environ.get('OPENROUTER_API_KEY','').strip()
 if g: providers.append((f'Gemini:{GEMINI_MODEL}',lambda:ask_gemini(prompt,sheets,g)))
 if o: providers.append((f'OpenRouter:{OPENROUTER_MODEL}',lambda:ask_openrouter(prompt,sheets,o)))
 errors=[]
 for label,fn in providers:
  for attempt in range(1,VISION_RETRIES+1):
   try:return fn(),label,errors
   except Exception as e:
    errors.append(f'{label} attempt {attempt}: {e}')
    if attempt<VISION_RETRIES and retryable(e): time.sleep(VISION_BACKOFF*(2**(attempt-1)))
    else: break
 return None,'none',errors
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('query'); ap.add_argument('visual_subject'); ap.add_argument('narration'); ap.add_argument('output'); a=ap.parse_args(); key=os.environ.get('PEXELS_API_KEY','').strip()
 if not key: print('PEXELS_API_KEY missing'); return 2
 idx=scene_index(a.output); role=SHOT_ROLES.get(idx,'varied'); base=' '.join(re.sub(r'[^A-Za-z0-9 -]',' ',a.visual_subject).lower().split()); query_words=base.split()[:2]; context=role if role not in query_words else ''; search_query=' '.join((query_words+[context])[:3])
 with tempfile.TemporaryDirectory(prefix='pexels-candidates-') as td:
  tmp=Path(td); candidates=search_candidates(search_query,tmp,key)
  if not candidates: print(f'No Pexels candidates for {search_query}'); return 1
  used=set()
  for meta in Path(a.output).parent.glob('source_*.selection.json'):
   try: used.add(int(json.loads(meta.read_text()).get('selected_video_id',0)))
   except Exception: pass
  usable=[]; sheets=[]
  for n,(video,vid) in enumerate(candidates,1):
   if vid in used: continue
   c=tmp/f'c{n}'
   try:
    candidate_frames(video,c); s=c/'sheet.jpg'
    if s.exists(): usable.append((video,vid)); sheets.append(s)
   except Exception: pass
  if not usable:
   usable=[]; sheets=[]
   for n,(video,vid) in enumerate(candidates,1):
    c=tmp/f'retry{n}'
    try:
     candidate_frames(video,c); s=c/'sheet.jpg'
     if s.exists(): usable.append((video,vid)); sheets.append(s)
    except Exception: pass
  prompt=f'''You are the final candidate selector for a production YouTube Short. Candidate sheets are in order 1..{len(sheets)}.\nLiteral subject: {a.visual_subject}\nNarration: {a.narration}\nRequired shot role for scene {idx}: {role}\nSearch query: {search_query}\n\nChoose the candidate whose visible footage best matches the literal subject AND the specific narrated meaning. Presence of the subject alone is insufficient. Reject generic footage, unrelated props, tiny incidental subjects, repeated-looking compositions, and footage that cannot support the sentence. Prefer a distinct composition appropriate to the shot role. Do not infer invisible scientific facts from ordinary footage. Return ONLY JSON {{"selected":1,"score":0.95,"semantic_score":0.93,"diversity_score":0.90,"reason":"..."}}. Publication-quality selection requires score >= 0.88 and semantic_score >= 0.85.'''
  result,provider,errors=vision(prompt,sheets) if sheets else (None,'none',[])
  if not result: print(json.dumps({'error':'vision selection unavailable','provider_errors':errors})); return 1
  try: sel=max(0,min(int(result.get('selected',1))-1,len(usable)-1)); score=float(result.get('score',0)); sem=float(result.get('semantic_score',0))
  except Exception: return 1
  if score<.88 or sem<.85: print(json.dumps({'error':'candidate quality below publication threshold','score':score,'semantic_score':sem,'provider':provider})); return 1
  chosen,vid=usable[sel]; Path(a.output).parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(chosen,a.output); meta=Path(a.output).with_suffix('.selection.json')
  meta.write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_index':sel+1,'selected_video_id':vid,'candidate_count':len(candidates),'selection_score':score,'semantic_score':sem,'diversity_score':float(result.get('diversity_score',0)),'provider':provider,'reason':str(result.get('reason','')),'provider_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8'); print(f'Selected Pexels candidate {sel+1}/{len(usable)} score={score:.2f} semantic={sem:.2f} provider={provider}')
 return 0
if __name__=='__main__': raise SystemExit(main())