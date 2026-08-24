#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re
from datetime import datetime,timezone
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT=Path(__file__).resolve().parents[1]
LEARNING=Path(os.getenv('LEARNING_DIR',ROOT/'learning')); HISTORY=LEARNING/'performance.json'; CONTEXT=LEARNING/'context.txt'; RUN=Path(os.getenv('RUN_DIR','data/run'))

def load():
    if not HISTORY.is_file(): return {'videos':[]}
    try:
        d=json.loads(HISTORY.read_text(encoding='utf-8'))
        return d if isinstance(d,dict) and isinstance(d.get('videos'),list) else {'videos':[]}
    except Exception as e:
        print(f'History reset: {e}'); return {'videos':[]}
def save(d):
    LEARNING.mkdir(parents=True,exist_ok=True); HISTORY.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def client():
    c=Credentials(token=None,refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'].strip(),token_uri='https://oauth2.googleapis.com/token',client_id=os.environ['YOUTUBE_CLIENT_ID'].strip(),client_secret=os.environ['YOUTUBE_CLIENT_SECRET'].strip(),scopes=['https://www.googleapis.com/auth/youtube.readonly'])
    c.refresh(Request()); return build('youtube','v3',credentials=c,cache_discovery=False)
def num(x):
    try:return int(x or 0)
    except:return 0
def score(v):
    try: age=max((datetime.now(timezone.utc)-datetime.fromisoformat(v.get('created_at','').replace('Z','+00:00'))).total_seconds()/86400,.25)
    except: age=1
    views=num(v.get('views')); likes=num(v.get('likes')); comments=num(v.get('comments'))
    return (views/age)*(1+min((((likes*2)+(comments*3))/max(views,1))*25,2))
def update(d):
    ids=[str(v.get('video_id','')) for v in d['videos'] if v.get('video_id')]
    if not ids:return False
    y=client(); changed=False
    for i in range(0,len(ids),50):
        items={x['id']:x for x in y.videos().list(part='statistics',id=','.join(ids[i:i+50])).execute().get('items',[])}
        for v in d['videos']:
            x=items.get(v.get('video_id'))
            if not x:continue
            s=x.get('statistics') or {}
            nv={'views':num(s.get('viewCount')),'likes':num(s.get('likeCount')),'comments':num(s.get('commentCount')),'last_checked_at':datetime.now(timezone.utc).isoformat()}
            if any(v.get(k)!=val for k,val in nv.items()): changed=True
            v.update(nv); v['score']=round(score(v),2)
    return changed
def record(d):
    log=RUN/'upload.log'; job=RUN/'job.json'
    if not log.is_file(): return False
    m=re.search(r'VIDEO_ID=([A-Za-z0-9_-]+)',log.read_text(encoding='utf-8',errors='replace'))
    if not m:return False
    data=json.loads(job.read_text(encoding='utf-8')) if job.is_file() else {}
    vid=m.group(1); old=next((v for v in d['videos'] if v.get('video_id')==vid),None)
    v=old or {'video_id':vid,'created_at':datetime.now(timezone.utc).isoformat(),'views':0,'likes':0,'comments':0}
    v.update({'title':str(data.get('title','')),'topic':str(data.get('topic','')),'category':str(data.get('category','')),'hook':str(data.get('hook','')),'provider':str(data.get('provider',''))})
    if not old:d['videos'].append(v)
    v['score']=round(score(v),2); return True
def context(d):
    vs=d.get('videos',[]); top=sorted(vs,key=score,reverse=True)[:8]; low=sorted(vs,key=score)[:5]
    out=['Use these observations only to improve structure/topic selection.','Views/likes/comments are channel-level proxy signals; retention is not inferred.','']
    if top:
        out+=['TOP PERFORMERS:']+[f"- topic={v.get('topic','')} | score={v.get('score',0)} | views={v.get('views',0)} | likes={v.get('likes',0)} | hook={v.get('hook','')[:180]}" for v in top]
    if low:
        out+=['','LOWER PERFORMERS:']+[f"- topic={v.get('topic','')} | score={v.get('score',0)} | views={v.get('views',0)} | hook={v.get('hook','')[:180]}" for v in low]
    return '\n'.join(out)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--update',action='store_true'); ap.add_argument('--record-upload',action='store_true'); ap.add_argument('--write-context',action='store_true'); a=ap.parse_args()
    d=load(); changed=False
    if a.update:
        try: changed=update(d) or changed; print('Performance stats updated')
        except Exception as e: print(f'Performance update skipped: {e}')
    if a.record_upload: changed=record(d) or changed
    if changed: save(d)
    if a.write_context:
        LEARNING.mkdir(parents=True,exist_ok=True); CONTEXT.write_text(context(d),encoding='utf-8');
        if not HISTORY.is_file():save(d)
        print('Learning context written')
if __name__=='__main__': main()
