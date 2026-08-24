#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,os,re,subprocess,time,urllib.error,urllib.request
from pathlib import Path
try:
 from json_repair import repair_json
except Exception: repair_json=None
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'; OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
REQUIRE_VISION_QA=os.environ.get('REQUIRE_VISION_QA','true').lower()=='true'; VISION_RETRIES=max(1,int(os.environ.get('VISION_RETRIES','3'))); VISION_BACKOFF=max(1.,float(os.environ.get('VISION_BACKOFF','4')))
STRICT=.88; MIN_SEMANTIC=.85; MIN_DIVERSITY=.18
def extract(text):
 raw=(text or '').strip().replace('\ufeff',''); a,b=raw.find('{'),raw.rfind('}')
 if a<0 or b<=a: raise RuntimeError('model returned no JSON')
 raw=raw[a:b+1]
 try:
  v=json.loads(raw)
  if isinstance(v,dict): return v
 except Exception: pass
 if repair_json:
  v=repair_json(raw,return_objects=True)
  if isinstance(v,dict): return v
 raise RuntimeError('invalid model JSON')
def post(url,body,headers):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(req,timeout=120) as r:return json.loads(r.read().decode('utf-8','replace'))
def ask_gemini(prompt,images,key):
 parts=[{'text':prompt}]+[{'inline_data':{'mime_type':'image/jpeg','data':base64.b64encode(p.read_bytes()).decode()}} for p in images]; x=post(GEMINI_URL,{'contents':[{'role':'user','parts':parts}],'generationConfig':{'temperature':0,'maxOutputTokens':3000,'responseMimeType':'application/json'}},{'x-goog-api-key':key,'Content-Type':'application/json'}); return extract(''.join(str(p.get('text','')) for p in (((x.get('candidates') or [{}])[0].get('content') or {}).get('parts') or []) if isinstance(p,dict)))
def ask_openrouter(prompt,images,key):
 content=[{'type':'text','text':prompt}]+[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(p.read_bytes()).decode()}} for p in images]; x=post(OPENROUTER_URL,{'model':OPENROUTER_MODEL,'messages':[{'role':'user','content':content}],'temperature':0,'max_tokens':3000},{'Authorization':f'Bearer {key}','Content-Type':'application/json','HTTP-Referer':'https://github.com/Aqaaab/faceless-youtube-shorts-n8n','X-Title':'Faceless YouTube Shorts Strict Visual QA'}); return extract(((x.get('choices') or [{}])[0].get('message') or {}).get('content',''))
def retryable(e):
 if isinstance(e,urllib.error.HTTPError): return e.code in {408,409,425,429,500,502,503,504}
 s=str(e).lower(); return any(x in s for x in ('429','too many requests','rate limit','timeout','timed out','temporarily unavailable'))
def vision(prompt,images):
 providers=[]; g=os.environ.get('GEMINI_API_KEY','').strip(); o=os.environ.get('OPENROUTER_API_KEY','').strip()
 if g: providers.append((f'Gemini:{GEMINI_MODEL}',lambda:ask_gemini(prompt,images,g)))
 if o: providers.append((f'OpenRouter:{OPENROUTER_MODEL}',lambda:ask_openrouter(prompt,images,o)))
 errors=[]
 for label,fn in providers:
  for attempt in range(1,VISION_RETRIES+1):
   try:return fn(),label,errors
   except Exception as e:
    errors.append(f'{label} attempt {attempt}: {e}')
    if attempt<VISION_RETRIES and retryable(e): time.sleep(VISION_BACKOFF*(2**(attempt-1)))
    else: break
 return None,'none',errors
def duration(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],text=True).strip())
def frame(video,out,ratio):
 d=duration(video); t=max(.05,min(d-.05,d*ratio)); subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','5',str(out)],check=True)
def sheet(video,out):
 imgs=[]
 for n,r in enumerate((.12,.30,.50,.70,.88),1):
  p=out.parent/f'{out.stem}_{n}.jpg'; frame(video,p,r); imgs.append(p)
 args=['ffmpeg','-hide_banner','-loglevel','error','-y']
 for p in imgs: args+=['-i',str(p)]
 args+=['-filter_complex','[0:v]scale=324:576[a];[1:v]scale=324:576[b];[2:v]scale=324:576[c];[3:v]scale=324:576[d];[4:v]scale=324:576[e];[a][b][c][d][e]hstack=inputs=5','-frames:v','1',str(out)]; subprocess.run(args,check=True)
def ahash(path):
 try:
  from PIL import Image
  a=list(Image.open(path).convert('L').resize((16,16)).getdata()); m=sum(a)/len(a); return [x>m for x in a]
 except Exception:return None
def diversity_score(paths):
 hs=[ahash(p) for p in paths]; vals=[]
 for i in range(len(hs)):
  for j in range(i+1,len(hs)):
   if hs[i] is not None and hs[j] is not None: vals.append(sum(x!=y for x,y in zip(hs[i],hs[j]))/len(hs[i]))
 return min(vals) if vals else 1.0
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('run_dir'); a=ap.parse_args(); run=Path(a.run_dir); job=json.loads((run/'job.json').read_text(encoding='utf-8')); scenes=job.get('scenes') or []; failures=[]; reports=[]; images=[]; image_paths=[]
 contract=run/'render_contract.json'; ass=run/'subtitles'/'subtitles.ass'
 if not contract.exists(): failures.append({'type':'render_contract','reason':'missing render contract'})
 else:
  c=json.loads(contract.read_text());
  if c.get('english_overlay') is not False or c.get('arabic_overlay') is not True: failures.append({'type':'render_contract','reason':'Arabic-only overlay contract violated'})
 if not ass.exists(): failures.append({'type':'subtitle_file','reason':'missing subtitles.ass'})
 else:
  t=ass.read_text(encoding='utf-8')
  if 'Style: EN' in t or re.search(r'Dialogue:.*?,EN,',t): failures.append({'type':'subtitle_file','reason':'English subtitle layer found'})
  if 'Style: AR' not in t or not re.search(r'Dialogue:.*?,AR,',t): failures.append({'type':'subtitle_file','reason':'Arabic subtitle layer missing'})
 if len(scenes)!=5: failures.append({'type':'scene_count','reason':f'expected 5 scenes, got {len(scenes)}'})
 for i,s in enumerate(scenes,1):
  en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); sub=str(s.get('visual_subject','')).strip(); q=str(s.get('pexels_query','')).strip(); r={'scene':i,'text_en':en,'text_ar':ar,'visual_subject':sub,'pexels_query':q,'translation_ok':bool(re.search(r'[\u0600-\u06ff]',ar)),'passed':False}
  meta=run/'downloads'/f'source_{i}.selection.json'
  if meta.exists():
   try:r['candidate_selection']=json.loads(meta.read_text())
   except Exception:r['candidate_selection']={'error':'invalid selection metadata'}
  source=run/'downloads'/f'source_{i}.mp4'; rendered=run/'scenes'/f'scene_{i}.mp4'
  if not source.exists() or not rendered.exists() or source.stat().st_size<100000:
   r['reason']='missing or suspicious footage'; failures.append({'scene':i,'type':'qa','reason':r['reason']}); reports.append(r); continue
  p=run/'visual_qa'/f'scene_{i}_sheet.jpg'; p.parent.mkdir(parents=True,exist_ok=True)
  try: sheet(rendered,p); images.append(p); image_paths.append(p)
  except Exception as e:r['reason']=f'frame extraction failed: {e}'; failures.append({'scene':i,'type':'qa','reason':r['reason']})
  reports.append(r)
 model='none'; provider_errors=[]
 if len(images)==5:
  prompt='''You are a strict human-level editorial visual QA gate. The five supplied images are scenes 1-5 in order. For EACH scene, judge the actual footage against the narration, not just whether the main object appears. A scene passes only when the visible action/composition materially supports the specific sentence. Merely showing the same animal/object while narration describes an invisible mechanism, direction, distance, communication, or scientific relationship is NOT sufficient unless footage visibly depicts that relationship. Reject semantic adjacency. Compare all five scenes: repeated or near-identical compositions are a failure even when the subject is correct. Require meaningful visual progression and different shot roles. Arabic translation must be natural Modern Standard Arabic, faithful to English meaning, and Arabic-only. Return ONLY JSON: {"scenes":[{"scene":1,"visual_match":true,"visual_score":0.95,"semantic_score":0.92,"translation_ok":true,"reason":"...","translation_reason":"..."}],"diversity_score":0.30,"overall_pass":true}. Exactly five scene objects. Publication threshold: visual_score >= 0.88 AND semantic_score >= 0.85. Diversity score 0-1 must be >= 0.18. Do not reward a scene simply because the subject exists.'''
  for i,s in enumerate(scenes,1): prompt+=f"\nSCENE {i}: SUBJECT={s.get('visual_subject','')} | EN={s.get('text_en','')} | AR={s.get('text_ar','')} | QUERY={s.get('pexels_query','')}"
  result,model,provider_errors=vision(prompt,images); actual_div=diversity_score(image_paths)
  if not result:
   failures.append({'type':'vision_provider','reason':'strict vision QA unavailable; fail closed','providers':provider_errors})
   for r in reports:r.update({'visual_match':False,'visual_score':0.0,'semantic_score':0.0,'passed':False,'reason':'vision QA unavailable'})
  else:
   items=result.get('scenes') if isinstance(result,dict) else None; model_div=float(result.get('diversity_score',0) or 0); final_div=min(actual_div,model_div) if model_div>0 else actual_div
   if not isinstance(items,list) or len(items)!=5: failures.append({'type':'vision_output','reason':'invalid five-scene vision assessment'}); items=[]
   if final_div<MIN_DIVERSITY: failures.append({'type':'diversity','reason':'visual scenes are too similar','diversity_score':final_div,'minimum':MIN_DIVERSITY})
   by={int(x.get('scene')):x for x in items if str(x.get('scene','')).isdigit()}
   for i,r in enumerate(reports,1):
    x=by.get(i,{}); vs=float(x.get('visual_score',0) or 0); ss=float(x.get('semantic_score',0) or 0); vm=bool(x.get('visual_match')); tr=bool(x.get('translation_ok')) and r['translation_ok']; ok=vm and vs>=STRICT and ss>=MIN_SEMANTIC and tr and final_div>=MIN_DIVERSITY
    r.update({'visual_match':vm,'visual_score':vs,'semantic_score':ss,'translation_ok':tr,'diversity_score':final_div,'reason':str(x.get('reason','')),'translation_reason':str(x.get('translation_reason','')),'passed':ok})
    if not(vm and vs>=STRICT and ss>=MIN_SEMANTIC): failures.append({'scene':i,'type':'semantic_visual','visual_score':vs,'semantic_score':ss,'reason':r['reason']})
    if not tr: failures.append({'scene':i,'type':'translation','reason':r['translation_reason']})
 else: failures.append({'type':'vision_input','reason':'not all five scene sheets available'})
 final={'passed':len(failures)==0,'model':model,'provider_errors':provider_errors,'diversity_score':diversity_score(image_paths) if len(image_paths)==5 else 0.0,'failures':failures,'scenes':reports,'thresholds':{'visual_score':STRICT,'semantic_score':MIN_SEMANTIC,'diversity_score':MIN_DIVERSITY}}
 out=run/'visual_qa'/'report.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(final,ensure_ascii=False)); return 0 if final['passed'] else 1
if __name__=='__main__': raise SystemExit(main())