#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); RUN_DIR.mkdir(parents=True,exist_ok=True)
ROOT=Path(__file__).resolve().parents[1]
OUT=RUN_DIR/'trend_candidates.json'
QUERIES=[
    'mystery true story explained','strange historical mystery','unsolved discovery story',
    'hidden history true story','scientific mystery explained','disappearance mystery explained',
    'engineering disaster story','lost place discovered','weird true story','unknown discovery'
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
        out.append({'id':e.get('id'),'title':title,'channel':clean(e.get('channel') or e.get('uploader')),
                    'url':e.get('webpage_url') or (f"https://www.youtube.com/watch?v={e.get('id')}" if e.get('id') else ''),'query':query})
    return out

def cached_candidates():
    for path in (ROOT/'learning'/'trends.json', RUN_DIR/'previous_trends.json'):
        if not path.exists(): continue
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            candidates=data.get('candidates') if isinstance(data,dict) else data
            if isinstance(candidates,list):
                clean_items=[]
                for x in candidates:
                    if isinstance(x,dict) and clean(x.get('title')):
                        y=dict(x); y.setdefault('query','cached'); y.setdefault('channel','cached'); y.setdefault('url','')
                        clean_items.append(y)
                if clean_items: return clean_items[:60], str(path)
        except Exception as exc:
            print(f'WARN cached trend data invalid: {path}: {exc}',file=sys.stderr)
    return [], ''

def main():
    seen=set(); items=[]
    for q in QUERIES:
        try:
            for x in search(q):
                key=x.get('id') or x['title'].lower()
                if key not in seen: seen.add(key); items.append(x)
        except Exception as exc:
            print(f'WARN trend query failed: {q}: {exc}', file=sys.stderr)
    source='youtube_yt_dlp_search'
    if not items:
        items,cache_source=cached_candidates()
        source=f'cached:{cache_source}' if items else 'unavailable'
    if not items:
        raise SystemExit('Trend research unavailable: live YouTube search failed and no cached candidates exist')
    for x in items:
        title=x['title'].lower()
        curiosity=sum(k in title for k in ['mystery','secret','hidden','unknown','strange','disappear','discovery','impossible','lost'])
        specificity=sum(k in title for k in ['true','story','explained','history','scientific','evidence'])
        x['trend_score']=round(min(100,45+curiosity*7+specificity*3-max(0,len(title)-90)*0.15),2)
    items.sort(key=lambda x:x['trend_score'],reverse=True)
    payload={'schema_version':'1.1','generated_at':datetime.now(timezone.utc).isoformat(),'source':source,
             'queries':QUERIES,'candidate_count':len(items),'candidates':items[:60],
             'note':'Trend score is a ranking signal, not a forecast or guarantee of virality.'}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
