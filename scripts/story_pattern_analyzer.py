#!/usr/bin/env python3
from __future__ import annotations
import json, os, re
from collections import Counter
from pathlib import Path
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'story_pattern.json'
STOP={'the','and','that','this','with','from','they','were','have','into','about','there','their','which','when','then','than','what','your','will','could','would','because','while','where','after','before','over','under','story','true','explained'}

def words(s): return [w for w in re.findall(r'[a-z0-9]+',str(s).lower()) if w not in STOP and len(w)>3]

def main():
    src=json.loads((RUN_DIR/'trend_candidates.json').read_text(encoding='utf-8'))
    rows=src.get('candidates',[])
    counts=Counter(w for r in rows for w in words(r.get('title')))
    top=[w for w,_ in counts.most_common(20)]
    candidates=[]
    for r in rows[:30]:
        title=r.get('title','')
        low=title.lower()
        patterns=[]
        if any(k in low for k in ['mystery','unknown','strange','secret']): patterns.append('mystery')
        if any(k in low for k in ['disappear','lost','vanish']): patterns.append('disappearance')
        if any(k in low for k in ['discover','found','evidence']): patterns.append('discovery')
        if any(k in low for k in ['scientific','science','engineering']): patterns.append('science_engineering')
        if any(k in low for k in ['history','historical']): patterns.append('history')
        if not patterns: patterns=['curiosity_story']
        candidates.append({'title':title,'url':r.get('url',''),'trend_score':r.get('trend_score',0),'patterns':patterns})
    candidates.sort(key=lambda x:(x['trend_score'],len(x['patterns'])),reverse=True)
    best=candidates[0] if candidates else {'title':'An unexplained mystery','url':'','trend_score':50,'patterns':['mystery']}
    payload={'schema_version':'1.0','engine':'pattern_v1','best_reference':best,'dominant_terms':top,'pattern_distribution':dict(Counter(p for c in candidates for p in c['patterns'])),'originality_rule':'Use the winning curiosity mechanism and structure, never copy the reference story, wording, title, thumbnail, or sequence of facts.'}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
