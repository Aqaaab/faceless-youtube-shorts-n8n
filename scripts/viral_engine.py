#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True); OUT=RUN_DIR/'viral_plan.json'
STOP={'the','and','that','this','with','from','they','were','have','into','about','there','their','which','when','then','than','what','your','will','could','would','because','while','where','after','before','over','under','some','more','most','very','just'}
def tokens(s): return [x for x in re.findall(r'[a-z0-9]+',str(s).lower()) if x not in STOP]
def score(text,beat,idx):
    low=str(text).lower(); w=tokens(text); curiosity=sum(k in low for k in ['mystery','secret','hidden','unknown','strange','discovered','why','how','but','until','revealed','nobody']); surprise=sum(k in low for k in ['first','unexpected','rare','suddenly','instead','actually','surprising','only']); specificity=min(10,len(set(w))/5); escalation=10 if beat in {'mystery','escalation','reveal'} else 5 if beat in {'evidence','payoff'} else 0; length=max(0,10-abs(len(w)-65)/8); return round(min(100,25+curiosity*5+surprise*4+specificity+escalation+length),2)
def build():
    story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8')); scenes=story['scenes']; candidates=[]
    for i,s in enumerate(scenes):
        end=min(i+2,len(scenes)-1); text=' '.join(str(scenes[j].get('text_en','')).strip() for j in range(i,end+1));
        candidates.append({'scene_start':i+1,'scene_end':end+1,'score':score(text,s.get('beat',''),i),'hook':s.get('text_en','').strip(),'text_en':text,'visual_subjects':[scenes[j].get('visual_subject','') for j in range(i,end+1)],'pexels_queries':[scenes[j].get('pexels_query','') for j in range(i,end+1)],'source':'long_video'})
    candidates.sort(key=lambda x:x['score'],reverse=True); shortlist=[]; used=set()
    for c in candidates:
        if any(abs(c['scene_start']-u)<=1 for u in used): continue
        shortlist.append(c); used.add(c['scene_start'])
        if len(shortlist)==12: break
    if len(shortlist)<12: raise SystemExit(f'EXPECTED_12_SHORT_CANDIDATES_GOT_{len(shortlist)}')
    selected=shortlist[:4]
    for n,c in enumerate(selected,1):
        c['short_number']=n; c['title']=f"{story.get('topic','Story')} — Part {n} #Shorts"[:85]; c['description']=f"A key moment from the long-form story about {story.get('topic','this story')}. Watch the full video for the complete context. #Shorts #Story #Facts #Explained #YouTube"; c['status']='selected'; c['source_video']='video.mp4'; c['related_video_required']=True
    plan={'schema_version':'2.0','source_story':{'topic':story.get('topic'),'title':story.get('title'),'format':story.get('format'),'duration_target_minutes':story.get('duration_target_minutes'),'source_file':'video.mp4'},'engine':'internal','external_assistant':'disabled','shorts_per_day':4,'candidate_count':12,'candidates':shortlist,'shorts':selected,'selection':{'method':'heuristic_v2','candidate_count':12,'selected_count':4,'source':'long_video','requires_distinct_source_ranges':True},'scoring':{'method':'heuristic_v2','range':[0,100],'note':'Ranking signal only; publication remains gated by QA.'}}
    OUT.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print('SHORT_CANDIDATES=12'); print('SHORT_SELECTION=4_FROM_LONG_VIDEO')
if __name__=='__main__': build()
