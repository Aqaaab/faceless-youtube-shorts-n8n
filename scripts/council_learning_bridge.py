#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
RUN=Path(os.environ.get('RUN_DIR','data/daily-production'))
LEARNING=Path(os.environ.get('LEARNING_DIR','learning'))
OUT=RUN/'council_learning.json'

def load(p):
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

def main():
    LEARNING.mkdir(parents=True,exist_ok=True); RUN.mkdir(parents=True,exist_ok=True)
    sources=[LEARNING/'performance.json',LEARNING/'youtube_performance.json',RUN/'performance.json',LEARNING/'metrics.json']
    records=[]
    for p in sources:
        d=load(p)
        if isinstance(d,dict): records.extend(d.get('records',d.get('items',[])) if isinstance(d.get('records',d.get('items',[])),list) else [])
    profiles={}
    for r in records:
        cat=str(r.get('category',r.get('topic','unknown'))).lower()
        x=profiles.setdefault(cat,{'n':0,'ctr':[],'retention':[],'avd':[],'velocity':[],'shorts':[]})
        x['n']+=1
        for k, aliases in {'ctr':['ctr','click_through_rate'],'retention':['retention','avg_retention'],'avd':['avd','average_view_duration'],'velocity':['views_velocity','velocity'],'shorts':['shorts_score','short_performance']}.items():
            for a in aliases:
                if r.get(a) is not None:
                    try:x[k].append(float(r[a]));break
                    except:pass
    def avg(v): return round(sum(v)/len(v),3) if v else None
    for x in profiles.values():
        for k in ('ctr','retention','avd','velocity','shorts'): x[k]=avg(x[k])
    # These are learning signals, not direct model claims. The council can use them as priors.
    priors=[]
    for cat,x in profiles.items():
        vals=[v for v in (x['ctr'],x['retention'],x['velocity'],x['shorts']) if v is not None]
        priors.append({'category':cat,'sample_size':x['n'],'performance_prior':round(sum(vals)/len(vals),3) if vals else 0,'metrics':x})
    priors.sort(key=lambda z:z['performance_prior'],reverse=True)
    payload={'schema_version':'1.0','records_seen':len(records),'category_priors':priors,'usage':'Use as a prior for council scoring; never replace fresh trend evidence.','source_files':[str(p) for p in sources if p.exists()]}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'COUNCIL_LEARNING=PASS records={len(records)} categories={len(priors)}')
if __name__=='__main__': main()
