#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,shutil,subprocess,tempfile,urllib.parse,urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pexels_visual_assistant import build_queries
PEXELS_URL='https://api.pexels.com/v1/videos/search'
MIN_SCORE=.88; MIN_SEMANTIC=.85
SHOT_ROLES=('detail','action','behavior','context','interaction','result','comparison','motion','environment','reveal')

def get(url,headers,timeout=120):
 req=urllib.request.Request(url,headers=headers,method='GET')
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
 params=urllib.parse.urlencode({'query':query,'orientation':'portrait','size':'large','per_page':'15'})
 data=get(f'{PEXELS_URL}?{params}',{'Authorization':key,'Accept':'application/json','User-Agent':'faceless-youtube-shorts/8.0'})
 rows=[]
 for v in data.get('videos',[]):
  files=[f for f in v.get('video_files',[]) if f.get('file_type')=='video/mp4' and f.get('link') and f.get('width') and f.get('height') and int(f['height'])>=int(f['width'])]
  if files:
   files.sort(key=lambda x:x.get('width',0)*x.get('height',0),reverse=True);rows.append((files[0]['link'],int(v.get('id',0))))
  if len(rows)>=10:break
 out=[]
 for n,(url,vid) in enumerate(rows,1):
  p=tmp/f'candidate_{n}_{vid or n}.mp4'
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'faceless-youtube-shorts/8.0'})
   with urllib.request.urlopen(req,timeout=120) as r,p.open('wb') as w:shutil.copyfileobj(r,w)
   if p.stat().st_size>=100000:out.append((p,vid))
  except Exception:pass
 return out

def evaluate(prompt,sheets):
 from vision_agent import evaluate as va
 return va(prompt,sheets,'selection')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('query');ap.add_argument('visual_subject');ap.add_argument('narration');ap.add_argument('output');a=ap.parse_args();idx=scene_index(a.output);role=role_for(idx);key=os.getenv('PEXELS_API_KEY','').strip();subject=' '.join(re.sub(r'[^A-Za-z0-9 -]',' ',a.visual_subject).lower().split())
 assistant_queries=build_queries(a.narration,subject,role,idx);errors=[]
 if not key:raise SystemExit('PEXELS_API_KEY missing')
 try:
  with tempfile.TemporaryDirectory(prefix='pexels-candidates-') as td:
   tmp=Path(td);all_candidates=[];seen=set();query_stats=[]
   for assistant_query in assistant_queries:
    try:
     found=search_candidates(assistant_query,tmp,key);added=0
     for item in found:
      if item[1] not in seen:seen.add(item[1]);all_candidates.append((item[0],item[1],assistant_query));added+=1
     query_stats.append({'query':assistant_query,'returned':len(found),'unique_added':added})
    except Exception as e:query_stats.append({'query':assistant_query,'returned':0,'unique_added':0,'error':str(e)})
   used=set()
   for meta in Path(a.output).parent.glob('source_*.selection.json'):
    try:
     v=json.loads(meta.read_text()).get('selected_video_id');used.add(int(v)) if v else None
    except Exception:pass
   candidates=[x for x in all_candidates if x[1] not in used] or all_candidates
   usable=[];sheets=[]
   for n,(video,vid,source_query) in enumerate(candidates,1):
    try:
     c=tmp/f'c{n}';candidate_frames(video,c);sheet=c/'sheet.jpg'
     if sheet.exists():usable.append((video,vid,source_query));sheets.append(sheet)
    except Exception as e:errors.append(f'candidate {n}: {e}')
   if not usable:raise RuntimeError('no usable Pexels candidates')
   prompt=f'''Select the best footage for scene {idx}. Subject: {a.visual_subject}. Narration: {a.narration}. Visual beat: {role}. Assistant queries: {assistant_queries}. The subject must be dominant AND the visible action/result must materially support the narration. Prefer a candidate that proves the causal relationship or result described by the narration, not merely a related object. Reject generic, decorative, stock-adjacent, or merely related footage. Return ONLY JSON {{"selected":1,"score":0.95,"semantic_score":0.92,"reason":"..."}}.'''
   result=evaluate(prompt,sheets);score=float(result.get('score',0));semantic=float(result.get('semantic_score',0));sel=max(0,min(int(result.get('selected',1))-1,len(usable)-1))
   if score<MIN_SCORE or semantic<MIN_SEMANTIC:raise RuntimeError(f'vision score below threshold score={score:.2f} semantic={semantic:.2f}')
   chosen,vid,source_query=usable[sel];shutil.copyfile(chosen,a.output)
   Path(a.output).with_suffix('.selection.json').write_text(json.dumps({'query':source_query,'assistant_queries':assistant_queries,'requested_query':a.query,'visual_subject':a.visual_subject,'shot_role':role,'selected_video_id':vid,'candidate_count':len(candidates),'query_stats':query_stats,'selection_score':score,'semantic_score':semantic,'provider':str(result.get('provider','vision-agent')),'fallback':False,'assistant':'pexels-visual-assistant-v1','reason':str(result.get('reason',''))},ensure_ascii=False,indent=2))
   print(f'Selected Pexels candidate provider={result.get("provider","vision-agent")} score={score:.2f} semantic={semantic:.2f}')
   return 0
 except Exception as e:
  errors.append(str(e))
 print(json.dumps({'error':'no acceptable visual provider succeeded','assistant_queries':assistant_queries,'provider_errors':errors},ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
