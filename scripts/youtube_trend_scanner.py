#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
OUT=RUN_DIR/'trend_candidates.json'
QUERIES=[
    'mystery true story explained', 'strange historical mystery', 'unsolved discovery story',
    'hidden history true story', 'scientific mystery explained', 'disappearance mystery explained',
    'engineering disaster story', 'lost place discovered', 'weird true story', 'unknown discovery'
]

def clean(s): return re.sub(r'\s+',' ',str(s or '')).strip()

def search(query):
    cmd=['yt-dlp','--flat-playlist','--dump-single-json',f'ytsearch12:{query}']
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=90)
    if p.returncode!=0: return []
    try: data=json.loads(p.stdout)
    except Exception: return []
    out=[]
    for e in data.get('entries',[]) or []:
        if not e: continue
        title=clean(e.get('title'))
        if not title: continue
        out.append({'id':e.get('id'),'title':title,'channel':clean(e.get('channel') or e.get('uploader')),'url':e.get('webpage_url') or (f"https://www.youtube.com/watch?v={e.get('id')}" if e.get('id') else ''),'query':query})
    return out

def fallback():
    return [{'id':'seed-'+str(i+1),'title':t,'channel':'seed','url':'','query':'fallback'} for i,t in enumerate([
        'The Mystery That Changed What We Know About a Lost Place',
        'The Strange Discovery Nobody Could Explain',
        'The True Story Behind an Impossible Disappearance',
        'The Hidden Evidence Found Years Later',
        'The Scientific Mystery That Took Decades to Solve',
        'The Disaster That Should Have Been Impossible'
    ])]

def main():
    seen=set(); items=[]
    for q in QUERIES:
        try:
            for x in search(q):
                key=x.get('id') or x['title'].lower()
                if key not in seen: seen.add(key); items.append(x)
        except Exception as exc:
            print(f'WARN trend query failed: {q}: {exc}', file=sys.stderr)
    if not items: items=fallback(); source='fallback'
    else: source='youtube_yt_dlp_search'
    for i,x in enumerate(items):
        title=x['title'].lower();
        curiosity=sum(k in title for k in ['mystery','secret','hidden','unknown','strange','disappear','discovery','impossible','lost'])
        specificity=sum(k in title for k in ['true','story','explained','history','scientific','evidence'])
        x['trend_score']=round(min(100,45+curiosity*7+specificity*3-max(0,len(title)-90)*0.15),2)
    items.sort(key=lambda x:x['trend_score'],reverse=True)
    payload={'schema_version':'1.0','generated_at':datetime.now(timezone.utc).isoformat(),'source':source,'queries':QUERIES,'candidate_count':len(items),'candidates':items[:60],'note':'Trend score is a ranking signal, not a forecast or a guarantee of virality.'}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
