#!/usr/bin/env python3
from __future__ import annotations
import json,os,re,subprocess,sys
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
BASE_GENERATOR=Path(__file__).with_name('generate_job.py')
GENERIC_QUERY={'nature','countryside','landscape','background','abstract','object','thing','scene','person','people','random'}
GENERIC_META={'english','general','shorts','unknown','miscellaneous',''}
def tokens(s): return re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)?',s.lower())
def normalize(d):
 sc=d.get('scenes') or []
 if len(sc)!=5: raise SystemExit('job.json must contain exactly 5 scenes')
 core=tokens(d.get('query',''))[:1]
 for i,s in enumerate(sc,1):
  en=str(s.get('text_en','')).strip(); ar=str(s.get('text_ar','')).strip(); vs=str(s.get('visual_subject','')).strip()
  if not en or not ar or not vs: raise SystemExit(f'scene {i} missing narration, Arabic, or visual_subject')
  q=tokens(s.get('pexels_query',''))
  q=[x for x in q if x not in GENERIC_QUERY]
  if not q: q=tokens(vs)[:2] or core or tokens(en)[:1]
  if core and core[0] not in q: q=[core[0]]+q
  s['pexels_query']=' '.join(q[:3])
  if 'chameleon' in en.lower() and ('حرباء' not in ar or 'القمل' in ar): raise SystemExit(f'unsafe Arabic translation in scene {i}')
 d['script']=' '.join(s['text_en'].strip() for s in sc); d['narration']=d['script']; d['subtitle_ar']=' '.join(s['text_ar'].strip() for s in sc); d['hook']=sc[0]['text_en'].strip(); d['pexels_query']=sc[0]['pexels_query']; d['provider']=d.get('provider','baseline-fallback')
 if str(d.get('topic','')).strip().lower() in GENERIC_META: d['topic']=(d.get('query') or sc[0]['visual_subject']).strip().title()
 if str(d.get('category','')).strip().lower() in GENERIC_META: d['category']='Science'
 title=str(d.get('title','')).strip()
 if len(title)>85 or not title.endswith('#Shorts'): d['title']=f"{d['topic']} — The Fact You Didn't Expect #Shorts"
 return d
def main():
 if not BASE_GENERATOR.is_file(): raise SystemExit(f'Missing baseline generator: {BASE_GENERATOR}')
 if subprocess.run([sys.executable,str(BASE_GENERATOR)],env=os.environ.copy()).returncode: raise SystemExit(1)
 p=RUN_DIR/'job.json'
 if not p.is_file() or not p.stat().st_size: raise SystemExit('Baseline generator did not create job.json')
 d=normalize(json.loads(p.read_text(encoding='utf-8'))); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Growth generation completed: hook + pacing + visual plan + Arabic QA schema')
if __name__=='__main__': main()
