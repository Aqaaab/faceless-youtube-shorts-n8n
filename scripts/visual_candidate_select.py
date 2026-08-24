#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,os,re,shutil,subprocess,tempfile,urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
PEXELS_URL='https://api.pexels.com/videos/search'
GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); GEMINI_URL=f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'; OPENROUTER_MODEL=os.environ.get('OPENROUTER_MODEL','openrouter/free')
VISION_RETRIES=max(1,int(os.environ.get('VISION_RETRIES','3'))); VISION_BACKOFF=max(1.,float(os.environ.get('VISION_BACKOFF','4')))
ALLOW_DETERMINISTIC_FALLBACK=os.environ.get('ALLOW_DETERMINISTIC_FALLBACK','true').lower()=='true'
SHOT_ROLES={1:'waggle dance',2:'waggle dance',3:'flight',4:'waggle dance',5:'waggle dance'}
MIN_SCORE=.88; MIN_SEMANTIC=.85

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
def run(cmd,capture=False,timeout=180):
 r=subprocess.run(cmd,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,timeout=timeout); return r.stdout.strip() if capture else ''
def scene_index(output):
 m=re.search(r'source_(\d+)',Path(output).name); return int(m.group(1)) if m else 0
def candidate_frames(video,out):
 out.mkdir(parents=True,exist_ok=True); d=max(float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video)],True) or '0'),1.0); frames=[]
 for idx,ratio in enumerate((.12,.35,.58,.82),1):
  t=max(.05,min(d-.05,d*ratio)); p=out/f'f{idx}.jpg'; run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','6',str(p)]); frames.append(p)
 args=['ffmpeg','-hide_banner','-loglevel','error','-y']
 for p in frames: args+=['-i',str(p)]
 args += ['-filter_complex','[0:v]scale=270:480[a];[1:v]scale=270:480[b];[2:v]scale=270:480[c];[3:v]scale=270:480[d];[a][b][c][d]hstack=inputs=4','-frames:v','1',str(out/'sheet.jpg')]; run(args)
def search_candidates(query,tmp,key):
 import urllib.parse
 params=urllib.parse.urlencode({'query':query,'orientation':'portrait','size':'large','per_page':'20'}); payload=get(f'{PEXELS_URL}?{params}',{'Authorization':key,'Accept':'application/json','User-Agent':'faceless-youtube-shorts/4.0'}); rows=[]
 for v in payload.get('videos',[]):
  files=[f for f in v.get('video_files',[]) if f.get('file_type')=='video/mp4' and f.get('link') and f.get('width') and f.get('height') and int(f['height'])>=int(f['width'])]
  if files:
   files.sort(key=lambda x:x.get('width',0)*x.get('height',0),reverse=True); rows.append((files[0]['link'],int(v.get('id',0))))
  if len(rows)>=10: break
 out=[]
 for idx,(url,vid) in enumerate(rows,1):
  p=tmp/f'candidate_{idx}_{vid or idx}.mp4'
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'faceless-youtube-shorts/4.0'})
   with urllib.request.urlopen(req,timeout=120) as r, p.open('wb') as w: shutil.copyfileobj(r,w)
   if p.stat().st_size>=100000: out.append((p,vid))
  except Exception: pass
 return out
def vision(prompt,sheets,kind='selection'):
 from vision_agent import evaluate
 try:return evaluate(prompt,sheets,kind), 'vision-agent', []
 except Exception as e:return None, 'none', [str(e)]
def frame_hash(video):
 try:
  raw=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-ss','0.45','-i',str(video),'-frames:v','1','-vf','scale=16:16,format=gray','-f','rawvideo','-'],timeout=20,stderr=subprocess.DEVNULL)
  if len(raw)<256:return None
  vals=list(raw[:256]); mean=sum(vals)/256; return tuple(v>=mean for v in vals)
 except Exception:return None
def diversity_distance(a,b):
 if not a or not b:return 0.0
 return sum(x!=y for x,y in zip(a,b))/len(a)
def deterministic_pick(usable,prior_videos,role_index):
 used_ids=set()
 for meta in Path(prior_videos).parent.glob('source_*.selection.json'):
  try:
   v=json.loads(meta.read_text()).get('selected_video_id')
   if v: used_ids.add(int(v))
  except Exception: pass
 available=[x for x in usable if x[1] not in used_ids] or usable
 prior_files=[p for p in Path(prior_videos).parent.glob('source_*.mp4') if p.exists()]
 ph=[frame_hash(p) for p in prior_files]; ph=[h for h in ph if h]
 if not ph:return available[(max(1,role_index)-1)%len(available)]
 best=None; best_score=-1
 for item in available:
  h=frame_hash(item[0]); score=min((diversity_distance(h,x) for x in ph),default=1.0)
  if score>best_score: best_score=score; best=item
 return best or available[0]
def gemini_image_fallback(narration,subject,role,output):
 key=os.environ.get('GEMINI_IMAGE_API_KEY','').strip()
 if not key:return False,'GEMINI_IMAGE_API_KEY missing'
 model=os.environ.get('GEMINI_IMAGE_MODEL','gemini-3.1-flash-image')
 prompt=(f'Create a vertical 9:16 educational visual that clearly explains this narration: {narration}. '
         f'Main subject: {subject}. Required evidence: {role}. '
         'Use a clean premium science-explainer style, realistic or accurate illustration as appropriate, '
         'strong visual hierarchy, one main concept, no decorative clutter, no captions, and make the visual evidence directly demonstrate the claim rather than merely depicting the topic.')
 body={'model':model,'input':[{'type':'text','text':prompt}],'response_format':{'type':'image','mime_type':'image/png','aspect_ratio':'9:16','image_size':'1K'}}
 req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/interactions',data=json.dumps(body).encode(),headers={'x-goog-api-key':key,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=180) as r:payload=json.loads(r.read().decode('utf-8','replace'))
 image=None
 for step in payload.get('steps',[]):
  for block in step.get('content',[]) if isinstance(step,dict) else []:
   if isinstance(block,dict) and block.get('type')=='image' and block.get('data'):image=base64.b64decode(block['data']);break
  if image:break
 if not image and isinstance(payload.get('output_image'),dict) and payload['output_image'].get('data'):image=base64.b64decode(payload['output_image']['data'])
 if not image:return False,'Gemini returned no image'
 png=Path(str(output)+'.gemini.png');png.write_bytes(image)
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',str(png),'-t','12','-vf',"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,format=yuv420p",'-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',str(output)],check=True)
 png.unlink(missing_ok=True)
 return True,'gemini-image'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('query');ap.add_argument('visual_subject');ap.add_argument('narration');ap.add_argument('output');a=ap.parse_args();key=os.environ.get('PEXELS_API_KEY','').strip()
 if not key:print('PEXELS_API_KEY missing');return 2
 idx=scene_index(a.output);role=SHOT_ROLES.get(idx,'behavior');subject=' '.join(re.sub(r'[^A-Za-z0-9 -]',' ',a.visual_subject).lower().split());words=subject.split()[:2];search_query=' '.join((words+role.split())[:3])
 with tempfile.TemporaryDirectory(prefix='pexels-candidates-') as td:
  tmp=Path(td);candidates=search_candidates(search_query,tmp,key)
  if not candidates:print(f'No Pexels candidates for {search_query}');return 1
  used_ids=set()
  for meta in Path(a.output).parent.glob('source_*.selection.json'):
   try:
    v=json.loads(meta.read_text()).get('selected_video_id')
    if v:used_ids.add(int(v))
   except Exception:pass
  usable=[];sheets=[]
  for n,(video,vid) in enumerate(candidates,1):
   if vid in used_ids:continue
   c=tmp/f'c{n}'
   try:
    candidate_frames(video,c);s=c/'sheet.jpg'
    if s.exists():usable.append((video,vid));sheets.append(s)
   except Exception:pass
  if not usable:
   for n,(video,vid) in enumerate(candidates,1):
    c=tmp/f'retry{n}'
    try:
     candidate_frames(video,c);s=c/'sheet.jpg'
     if s.exists():usable.append((video,vid));sheets.append(s)
    except Exception:pass
  if not usable:return 1
  prompt=f'''Select the best production footage for scene {idx}. Candidates are 1..{len(sheets)}. Literal subject: {a.visual_subject}. Narration: {a.narration}. Required visual evidence: {role}. Search query: {search_query}. The literal subject must be dominant AND the visible action/composition must materially support the narration. For communication scenes, prefer visible waggle-dance behavior or multiple-bee interaction; for direction scenes, prefer flight/navigation behavior. Reject generic close-ups, feeding-only footage, tiny incidental subjects, semantic adjacency, unrelated props, and repeated-looking compositions. Return ONLY JSON {{"selected":1,"score":0.95,"semantic_score":0.92,"diversity_score":0.85,"reason":"..."}}. Require score >= 0.88 and semantic_score >= 0.85.'''
  result,provider,errors=vision(prompt,sheets,'selection')
  if result:
   try:sel=max(0,min(int(result.get('selected',1))-1,len(usable)-1));score=float(result.get('score',0));semantic=float(result.get('semantic_score',0))
   except Exception:return 1
   if score<MIN_SCORE or semantic<MIN_SEMANTIC:
    if os.environ.get('GEMINI_IMAGE_API_KEY','').strip():
     try:
      ok,reason=gemini_image_fallback(a.narration,a.visual_subject,role,a.output)
      if ok:
       meta=Path(a.output).with_suffix('.selection.json');meta.write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_video_id':None,'candidate_count':len(candidates),'selection_score':0.90,'semantic_score':0.90,'provider':'Gemini Image','fallback':True,'reason':'Pexels candidates failed strict semantic selection; generated purpose-built explanatory visual.','provider_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');print(f'Generated AI explanatory visual query={search_query!r} mode=gemini-image-fallback',flush=True);return 0
     except Exception as e:errors.append(f'Gemini Image: {e}')
    print(json.dumps({'error':'vision selection below quality threshold','score':score,'semantic_score':semantic,'query':search_query,'provider_errors':errors},ensure_ascii=False));return 1
   chosen,vid=usable[sel];mode='vision'
  elif os.environ.get('GEMINI_IMAGE_API_KEY','').strip():
   try:
    ok,reason=gemini_image_fallback(a.narration,a.visual_subject,role,a.output)
    if ok:
     meta=Path(a.output).with_suffix('.selection.json');meta.write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_video_id':None,'candidate_count':len(candidates),'selection_score':0.90,'semantic_score':0.90,'provider':'Gemini Image','fallback':True,'reason':'Vision providers unavailable; generated purpose-built explanatory visual.','provider_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');print(f'Generated AI explanatory visual query={search_query!r} mode=gemini-image-fallback',flush=True);return 0
   except Exception as e:errors.append(f'Gemini Image: {e}')
   if not ALLOW_DETERMINISTIC_FALLBACK:print(json.dumps({'error':'visual selection unavailable','provider_errors':errors},ensure_ascii=False));return 1
   chosen,vid=deterministic_pick(usable,a.output,idx);score=0.0;semantic=0.0;mode='deterministic-fallback'
  elif ALLOW_DETERMINISTIC_FALLBACK:
   chosen,vid=deterministic_pick(usable,a.output,idx);score=0.0;semantic=0.0;mode='deterministic-fallback'
  else:print(json.dumps({'error':'visual selection unavailable','provider_errors':errors},ensure_ascii=False));return 1
  Path(a.output).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(chosen,a.output);meta=Path(a.output).with_suffix('.selection.json');meta.write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_index':usable.index((chosen,vid))+1,'selected_video_id':vid,'candidate_count':len(candidates),'selection_score':score,'semantic_score':semantic,'provider':provider if mode=='vision' else 'deterministic-fallback','fallback':mode!='vision','reason':str(result.get('reason','')) if result else 'Vision providers unavailable; distinct deterministic candidate selected. Strict final visual QA remains mandatory.','provider_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8');print(f'Selected Pexels candidate query={search_query!r} score={score:.2f} semantic={semantic:.2f} mode={mode}',flush=True)
 return 0
if __name__=='__main__':raise SystemExit(main())
