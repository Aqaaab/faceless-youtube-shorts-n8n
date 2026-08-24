#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,json,os,re,shutil,subprocess,tempfile,urllib.parse,urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
PEXELS_URL='https://api.pexels.com/videos/search'
MIN_SCORE=.88; MIN_SEMANTIC=.85
SHOT_ROLES=('detail','action','behavior','context','interaction','result','comparison','motion','environment','reveal')
def get(url,headers,timeout=120):
 req=urllib.request.Request(url,headers=headers,method='GET')
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
def post(url,body,headers,timeout=180):
 req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read().decode('utf-8','replace'))
def run(cmd,capture=False,timeout=180):
 r=subprocess.run(cmd,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,timeout=timeout);return r.stdout.strip() if capture else ''
def scene_index(output):
 m=re.search(r'source_(\d+)',Path(output).name);return int(m.group(1)) if m else 1
def role_for(idx):return SHOT_ROLES[(idx-1)%len(SHOT_ROLES)]
def candidate_frames(video,out):
 out.mkdir(parents=True,exist_ok=True); d=max(float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video)],True) or '0'),1.0);frames=[]
 for n,ratio in enumerate((.12,.38,.64,.86),1):
  t=max(.05,min(d-.05,d*ratio));p=out/f'f{n}.jpg';run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','6',str(p)]);frames.append(p)
 args=['ffmpeg','-hide_banner','-loglevel','error','-y']+[x for p in frames for x in ('-i',str(p))]+['-filter_complex','[0:v]scale=270:480[a];[1:v]scale=270:480[b];[2:v]scale=270:480[c];[3:v]scale=270:480[d];[a][b][c][d]hstack=inputs=4','-frames:v','1',str(out/'sheet.jpg')];run(args)
def search_candidates(query,tmp,key):
 params=urllib.parse.urlencode({'query':query,'orientation':'portrait','size':'large','per_page':'15'});data=get(f'{PEXELS_URL}?{params}',{'Authorization':key,'Accept':'application/json','User-Agent':'faceless-youtube-shorts/6.0'});rows=[]
 for v in data.get('videos',[]):
  files=[f for f in v.get('video_files',[]) if f.get('file_type')=='video/mp4' and f.get('link') and f.get('width') and f.get('height') and int(f['height'])>=int(f['width'])]
  if files:
   files.sort(key=lambda x:x.get('width',0)*x.get('height',0),reverse=True);rows.append((files[0]['link'],int(v.get('id',0))))
  if len(rows)>=10:break
 out=[]
 for n,(url,vid) in enumerate(rows,1):
  p=tmp/f'candidate_{n}_{vid or n}.mp4'
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'faceless-youtube-shorts/6.0'})
   with urllib.request.urlopen(req,timeout=120) as r,p.open('wb') as w:shutil.copyfileobj(r,w)
   if p.stat().st_size>=100000:out.append((p,vid))
  except Exception:pass
 return out
def evaluate(prompt,sheets):
 from vision_agent import evaluate as va
 return va(prompt,sheets,'selection')
def gemini_image_fallback(narration,subject,role,output):
 key=os.getenv('GEMINI_IMAGE_API_KEY','').strip()
 if not key:return False,'GEMINI_IMAGE_API_KEY missing'
 model=os.getenv('GEMINI_IMAGE_MODEL','gemini-3.1-flash-image')
 prompt=(f'Create an accurate vertical 9:16 educational visual for this narration: {narration}. Main subject: {subject}. Visual beat: {role}. '
 'Make the evidence explicit through composition, objects, arrows or simple diagrammatic relationships when useful. Premium science-explainer style. No captions, no logos, no decorative text.')
 body={'model':model,'input':[{'type':'text','text':prompt}],'response_format':{'type':'image','mime_type':'image/png','aspect_ratio':'9:16','image_size':'1K'}}
 req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/interactions',data=json.dumps(body).encode(),headers={'x-goog-api-key':key,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=180) as r:data=json.loads(r.read().decode('utf-8','replace'))
 image=None
 for step in data.get('steps',[]):
  for block in step.get('content',[]) if isinstance(step,dict) else []:
   if isinstance(block,dict) and block.get('type')=='image' and block.get('data'):image=base64.b64decode(block['data']);break
  if image:break
 if not image and isinstance(data.get('output_image'),dict) and data['output_image'].get('data'):image=base64.b64decode(data['output_image']['data'])
 if not image:return False,'Gemini returned no image'
 png=Path(str(output)+'.gemini.png');png.write_bytes(image)
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',str(png),'-t','12','-vf',"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,format=yuv420p",'-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',str(output)],check=True)
 png.unlink(missing_ok=True);return True,'gemini-image'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('query');ap.add_argument('visual_subject');ap.add_argument('narration');ap.add_argument('output');a=ap.parse_args();idx=scene_index(a.output);role=role_for(idx);key=os.getenv('PEXELS_API_KEY','').strip();subject=' '.join(re.sub(r'[^A-Za-z0-9 -]',' ',a.visual_subject).lower().split())
 search_query=' '.join((subject.split()[:3]+role.split()[:2])[:5])
 errors=[]
 if key:
  try:
   with tempfile.TemporaryDirectory(prefix='pexels-candidates-') as td:
    tmp=Path(td);candidates=search_candidates(search_query,tmp,key);used=set()
    for meta in Path(a.output).parent.glob('source_*.selection.json'):
     try:
      v=json.loads(meta.read_text()).get('selected_video_id');used.add(int(v)) if v else None
     except Exception:pass
    candidates=[x for x in candidates if x[1] not in used] or candidates
    usable=[];sheets=[]
    for n,(video,vid) in enumerate(candidates,1):
     try:
      c=tmp/f'c{n}';candidate_frames(video,c);sheet=c/'sheet.jpg'
      if sheet.exists():usable.append((video,vid));sheets.append(sheet)
     except Exception as e:errors.append(f'candidate {n}: {e}')
    if usable:
     prompt=f'''Select the best footage for scene {idx}. Subject: {a.visual_subject}. Narration: {a.narration}. Visual beat: {role}. Query: {search_query}. The subject must be dominant and the visible action must materially support the narration. Reject generic or merely related footage. Return ONLY JSON {{"selected":1,"score":0.95,"semantic_score":0.92,"reason":"..."}}.''' 
     try:
      result=evaluate(prompt,sheets);score=float(result.get('score',0));semantic=float(result.get('semantic_score',0));sel=max(0,min(int(result.get('selected',1))-1,len(usable)-1))
      if score>=MIN_SCORE and semantic>=MIN_SEMANTIC:
       chosen,vid=usable[sel];shutil.copyfile(chosen,a.output);Path(a.output).with_suffix('.selection.json').write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_video_id':vid,'candidate_count':len(candidates),'selection_score':score,'semantic_score':semantic,'provider':'vision-agent','fallback':False,'reason':str(result.get('reason',''))},ensure_ascii=False,indent=2));print(f'Selected Pexels candidate query={search_query!r} score={score:.2f} semantic={semantic:.2f}');return 0
      errors.append(f'vision score below threshold score={score:.2f} semantic={semantic:.2f}')
     except Exception as e:errors.append(f'vision selection: {e}')
    else:errors.append(f'no usable Pexels candidates for {search_query!r}')
  except Exception as e:errors.append(f'Pexels: {e}')
 else:errors.append('PEXELS_API_KEY missing')
 try:
  ok,reason=gemini_image_fallback(a.narration,a.visual_subject,role,a.output)
  if ok:
   Path(a.output).with_suffix('.selection.json').write_text(json.dumps({'query':search_query,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_video_id':None,'candidate_count':0,'selection_score':0.90,'semantic_score':0.90,'provider':'Gemini Image','fallback':True,'reason':'Pexels footage unavailable or below strict semantic threshold.','provider_errors':errors},ensure_ascii=False,indent=2));print(f'Generated AI explanatory visual query={search_query!r} mode=gemini-image-fallback');return 0
  errors.append(reason)
 except Exception as e:errors.append(f'Gemini Image: {e}')
 print(json.dumps({'error':'no acceptable visual provider succeeded','query':search_query,'provider_errors':errors},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())