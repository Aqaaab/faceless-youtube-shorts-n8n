#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, re
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'viral_plan.json'

STOP={'the','and','that','this','with','from','they','were','have','into','about','there','their','which','when','then','than','what','your','will','could','would','because','while','where','after','before','over','under','into','some','more','most','very','just'}

def tokens(s): return [x for x in re.findall(r'[a-z0-9]+',str(s).lower()) if x not in STOP]
def score(text, beat, idx, total):
    t=str(text); low=t.lower(); w=tokens(t)
    curiosity=sum(k in low for k in ['mystery','secret','hidden','unknown','strange','discovered','why','how','but','until','revealed','nobody'])
    surprise=sum(k in low for k in ['first','unexpected','rare','suddenly','instead','actually','surprising','only'])
    specificity=min(10, len(set(w))/5)
    hook=15 if idx==0 else 0
    escalation=10 if beat in {'mystery','escalation','reveal'} else 5 if beat in {'evidence','payoff'} else 0
    length=max(0,10-abs(len(w)-65)/8)
    return round(min(100,25+curiosity*5+surprise*4+specificity+hook+escalation+length),2)

def build():
    story=json.loads((RUN_DIR/'long_story.json').read_text(encoding='utf-8'))
    scenes=story['scenes']; candidates=[]
    for i,s in enumerate(scenes):
        if i+1 < len(scenes):
            text=(s.get('text_en','')+' '+scenes[i+1].get('text_en','')).strip()
        else: text=s.get('text_en','').strip()
        sc=score(text,s.get('beat',''),i,len(scenes))
        candidates.append({'scene_start':i+1,'scene_end':min(i+2,len(scenes)),'score':sc,'hook':s.get('text_en','').strip(),'text_en':text,'visual_subjects':[s.get('visual_subject',''),scenes[min(i+1,len(scenes)-1)].get('visual_subject','')],'pexels_queries':[s.get('pexels_query',''),scenes[min(i+1,len(scenes)-1)].get('pexels_query','')]})
    candidates.sort(key=lambda x:x['score'],reverse=True)
    selected=[]
    used=set()
    for c in candidates:
        if any(abs(c['scene_start']-u)<=1 for u in used): continue
        selected.append(c); used.add(c['scene_start'])
        if len(selected)==4: break
    if len(selected)<4: raise SystemExit('Unable to select four distinct Shorts')
    for n,c in enumerate(selected,1):
        c['short_number']=n; c['title']=f"{story.get('topic','Story')} — Part {n} #Shorts"[:85]
        c['description']=f"A key moment from the story about {story.get('topic','this story')}. Watch the full story for the complete context. #Shorts #Story #Facts #Explained #YouTube"
        c['status']='candidate'
    plan={'schema_version':'1.0','source_story':{'topic':story.get('topic'),'title':story.get('title'),'format':story.get('format'),'duration_target_minutes':story.get('duration_target_minutes')},'engine':'internal','external_assistant':'disabled','shorts_per_day':4,'shorts':selected,'scoring':{'method':'heuristic_v1','range':[0,100],'note':'Score is a ranking signal, not a prediction guarantee.'}}
    OUT.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(plan,ensure_ascii=False,indent=2))

if __name__=='__main__': build()
