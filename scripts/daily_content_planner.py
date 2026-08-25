#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'daily_plan.json'

def clean(s): return re.sub(r'\s+',' ',str(s or '')).strip()

def build_plan():
    trend={}
    tp=RUN_DIR/'trend_candidates.json'
    pp=RUN_DIR/'story_pattern.json'
    if tp.exists():
        try: trend=json.loads(tp.read_text(encoding='utf-8'))
        except Exception: trend={}
    pattern={}
    if pp.exists():
        try: pattern=json.loads(pp.read_text(encoding='utf-8'))
        except Exception: pattern={}
    reference=pattern.get('best_reference',{})
    topic=clean(os.environ.get('DAILY_TOPIC','')) or clean(os.environ.get('TREND_TOPIC','')) or clean(reference.get('title',''))
    if not topic: topic='An unexplained mystery that becomes stranger with every discovery'
    category=clean(os.environ.get('DAILY_CATEGORY','Stories')) or 'Stories'
    plan={
      'schema_version':'2.0','content_date':os.environ.get('CONTENT_DATE',''),
      'trend_research':{'enabled':True,'source':trend.get('source','unavailable'),'candidate_count':trend.get('candidate_count',0),'reference_pattern':reference.get('patterns',[])},
      'daily_long_video':{'count':1,'duration_min':7,'duration_max':15,'format':'patent','topic':topic,'category':category,'originality_required':True},
      'daily_shorts':{'count':4,'source':'daily_long_video','independent_hooks':True,'target_duration_sec':[28,59]},
      'viral_engine':{'enabled':True,'provider':'internal','external_assistant':'optional_later','score_range':[0,100]},
      'publishing':{'long_video_per_day':1,'shorts_per_day':4,'short_spacing_hours':4},
      'contracts':{'no_deterministic_fallback':True,'require_visual_qa':True,'require_metadata':True,'require_original_story':True},
      'github_assistants':{'enabled':True,'mode':'research_helpers','external_production_dependency':False}
    }
    OUT.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(plan,ensure_ascii=False,indent=2))
if __name__=='__main__': build_plan()
