#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re,subprocess
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
try: from json_repair import repair_json
except Exception: repair_json=None
STRICT=float(os.environ.get('VISION_MIN_SCORE','0.88')); MIN_SEMANTIC=float(os.environ.get('VISION_MIN_SEMANTIC_SCORE','0.85')); MIN_DIVERSITY=float(os.environ.get('VISION_MIN_DIVERSITY','0.18'))
MIN_SCENES=int(os.environ.get('MIN_SCENES','5')); MAX_SCENES=int(os.environ.get('MAX_SCENES','10'))
def extract(t):
 raw=(t or '').strip().replace('\ufeff','');a,b=raw.find('{'),raw.rfind('}')
 if a<0 or b<=a:raise RuntimeError('model returned no JSON')
 raw=raw[a:b+1]
 try:x=json.loads(raw);return x if isinstance(x,dict) else None
 except Exception:pass
 if repair_json:
  x=repair_json(raw,return_objects=True)
  if isinstance(x,dict):return x
 raise RuntimeError('invalid model JSON')
def duration(p):return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],text=True).strip())
def frame(video,out,ratio):
 d=duration(video);t=max(.05,min(d-.05,d*ratio));subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',str(video),'-frames:v','1','-q:v','6',str(out)],check=True)
def contact_sheet(video,out):
 imgs=[]
 for n,r in enumerate((.12,.30,.48,.68,.88),1):
  p=out.parent/f'{out.stem}_{n}.jpg';frame(video,p,r);imgs.append(p)
 args=['ffmpeg','-hide_banner','-loglevel','error','-y']
 for p in imgs:args+=['-i',str(p)]
 args+=['-filter_complex','[0:v]scale=324:576[a];[1:v]scale=324:576[b];[2:v]scale=324:576[c];[3:v]scale=324:576[d];[4:v]scale=324:576[e];[a][b][c][d][e]hstack=inputs=5','-frames:v','1',str(out)]
 subprocess.run(args,check=True)
def ahash(path):
 try:
  raw=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-ss','0.45','-i',str(path),'-frames:v','1','-vf','scale=16:16,format=gray','-f','rawvideo','-'],timeout=20,stderr=subprocess.DEVNULL)
  if len(raw)<256:return None
  vals=list(raw[:256]);m=sum(vals)/256;return tuple(v>=m for v in vals)
 except Exception:return None
def diversity(paths):
 hs=[ahash(p) for p in paths]
 if len(hs)<2 or any(h is None for h in hs):return 0.0
 vals=[sum(x!=y for x,y in zip(hs[i],hs[j]))/256 for i in range(len(hs)) for j in range(i+1,len(hs))]
 return min(vals) if vals else 0.0
def vision(prompt,image):
 from vision_agent import evaluate
 return evaluate(prompt,[image],'final-qa')
def positive_translation(reason,ar):
 r=str(reason or '').lower();return bool(re.search(r'[\u0600-\u06ff]',ar)) and any(x in r for x in ('faithful','accurate','correct','fluent','faithfully'))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('run_dir');run=Path(ap.parse_args().run_dir);job=json.loads((run/'job.json').read_text(encoding='utf-8'));scenes=job.get('scenes') or [];failures=[];reports=[];sheets=[]
 long_form=str(job.get('format','')).lower() in {'patent','long_form'}
 min_s=int(os.environ.get('MIN_SCENES','18' if long_form else str(MIN_SCENES)))
 max_s=int(os.environ.get('MAX_SCENES','30' if long_form else str(MAX_SCENES)))
 if not min_s<=len(scenes)<=max_s:failures.append({'type':'scene_count','reason':f'expected {min_s}-{max_s} scenes, got {len(scenes)}'})
 contract=run/'render_contract.json';ass=run/'subtitles'/'subtitles.ass'
 if not contract.exists():failures.append({'type':'render_contract','reason':'missing render contract'})
 else:
  c=json.loads(contract.read_text())
  if c.get('english_overlay') is not False or c.get('arabic_overlay') is not True:failures.append({'type':'render_contract','reason':'Arabic-only overlay contract violated'})
 if not ass.exists():failures.append({'type':'subtitle_file','reason':'missing subtitles.ass'})
 else:
  t=ass.read_text(encoding='utf-8')
  if 'Style: EN' in t or re.search(r'Dialogue:.*?,EN,',t):failures.append({'type':'subtitle_file','reason':'English subtitle layer found'})
  if 'Style: AR' not in t or not re.search(r'Dialogue:.*?,AR,',t):failures.append({'type':'subtitle_file','reason':'Arabic subtitle layer missing'})
 for i,s in enumerate(scenes,1):
  en=str(s.get('text_en','')).strip();ar=str(s.get('text_ar','')).strip();sub=str(s.get('visual_subject','')).strip();q=str(s.get('pexels_query','')).strip();r={'scene':i,'text_en':en,'text_ar':ar,'visual_subject':sub,'pexels_query':q,'translation_ok':bool(re.search(r'[\u0600-\u06ff]',ar)),'passed':False}
  meta=run/'downloads'/f'source_{i}.selection.json'
  if meta.exists():
   try:r['candidate_selection']=json.loads(meta.read_text())
   except Exception:r['candidate_selection']={'error':'invalid selection metadata'}
  source=run/'downloads'/f'source_{i}.mp4';rendered=run/'scenes'/f'scene_{i}.mp4'
  if not source.exists() or not rendered.exists() or source.stat().st_size<100000:
   r['reason']='missing or suspicious footage';failures.append({'scene':i,'type':'qa','reason':r['reason']});reports.append(r);continue
  p=run/'visual_qa'/f'scene_{i}_sheet.jpg';p.parent.mkdir(parents=True,exist_ok=True)
  try:contact_sheet(rendered,p);sheets.append(p)
  except Exception as e:r['reason']=f'frame extraction failed: {e}';failures.append({'scene':i,'type':'qa','reason':r['reason']})
  reports.append(r)
 scene_paths=[run/'scenes'/f'scene_{i}.mp4' for i in range(1,len(scenes)+1)];measured=diversity(scene_paths) if scenes and all(p.exists() for p in scene_paths) else 0.0
 provider_errors=[];model='none'
 if len(sheets)==len(scenes) and min_s<=len(scenes)<=max_s:
  combined=run/'visual_qa'/'all_scenes_sheet.jpg'
  args=['ffmpeg','-hide_banner','-loglevel','error','-y']
  for p in sheets:args+=['-i',str(p)]
  filters=''.join(f'[{i}:v]scale=324:576[s{i}];' for i in range(len(sheets)))+''.join(f'[s{i}]' for i in range(len(sheets)))+f'hstack=inputs={len(sheets)}'
  try:
   subprocess.run(args+['-filter_complex',filters,'-frames:v','1',str(combined)],check=True)
   prompt=f'''Strict visual publication gate. The single attached image is a contact sheet containing {len(scenes)} scene panels in order from left to right. Judge actual footage against the exact narration, not merely related objects. Generic object presence is insufficient when narration describes a mechanism or action. Return ONLY JSON: {{"scenes":[{{"scene":1,"visual_match":true,"visual_score":0.95,"semantic_score":0.92,"translation_ok":true,"reason":"...","translation_reason":"..."}}],"diversity_score":0.30,"overall_pass":true}}. Exactly {len(scenes)} assessments.'''
   for i,s in enumerate(scenes,1):prompt+=f"\nSCENE {i}: SUBJECT={s.get('visual_subject','')} | EN={s.get('text_en','')} | AR={s.get('text_ar','')} | QUERY={s.get('pexels_query','')}"
   try:result=vision(prompt,combined);model='vision-agent'
   except Exception as e:result=None;provider_errors=[str(e)]
  except Exception as e:result=None;provider_errors=[f'contact sheet: {e}']
  if not result:failures.append({'type':'vision_provider','reason':'strict vision QA unavailable; publication must fail closed','providers':provider_errors})
  else:
   items=result.get('scenes') if isinstance(result,dict) else [];model_div=float(result.get('diversity_score',0) or 0);final_div=min(measured,model_div) if model_div>0 else measured
   if not isinstance(items,list) or len(items)!=len(scenes):failures.append({'type':'vision_output','reason':f'invalid {len(scenes)}-scene vision assessment'});items=[]
   if final_div<MIN_DIVERSITY:failures.append({'type':'diversity','reason':'visual scenes are too similar','diversity_score':final_div,'minimum':MIN_DIVERSITY})
   by={int(x.get('scene')):x for x in items if str(x.get('scene','')).isdigit()}
   for i,r in enumerate(reports,1):
    x=by.get(i,{});vs=float(x.get('visual_score',0) or 0);ss=float(x.get('semantic_score',0) or 0);vm=bool(x.get('visual_match'));tr=bool(x.get('translation_ok')) and r['translation_ok'];reason=str(x.get('reason',''));treason=str(x.get('translation_reason',''))
    if not tr and positive_translation(treason,r['text_ar']):tr=True
    ok=vm and vs>=STRICT and ss>=MIN_SEMANTIC and tr and final_div>=MIN_DIVERSITY;r.update({'visual_match':vm,'visual_score':vs,'semantic_score':ss,'translation_ok':tr,'diversity_score':final_div,'reason':reason,'translation_reason':treason,'passed':ok})
    if not(vm and vs>=STRICT and ss>=MIN_SEMANTIC):failures.append({'scene':i,'type':'semantic_visual','visual_score':vs,'semantic_score':ss,'reason':reason})
    if not tr:failures.append({'scene':i,'type':'translation','reason':treason})
 else:
  for r in reports:r.update({'visual_match':False,'visual_score':0.0,'semantic_score':0.0,'diversity_score':measured,'passed':False})
 final={'passed':not failures,'model':model,'provider_errors':provider_errors,'diversity_score':measured,'failures':failures,'scenes':reports,'thresholds':{'visual_score':STRICT,'semantic_score':MIN_SEMANTIC,'diversity_score':MIN_DIVERSITY,'scene_count':{'min':min_s,'max':max_s}}}
 out=run/'visual_qa'/'report.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(final,ensure_ascii=False));return 0 if final['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
