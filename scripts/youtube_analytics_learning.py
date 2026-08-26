#!/usr/bin/env python3
from __future__ import annotations
import json, os
from datetime import date, timedelta
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT=Path(__file__).resolve().parents[1]
RUN_DIR=Path(os.environ.get('RUN_DIR','data/analytics-learning'))
LEARNING_DIR=Path(os.environ.get('LEARNING_DIR','learning'))
SCOPES=['https://www.googleapis.com/auth/youtube.readonly','https://www.googleapis.com/auth/yt-analytics.readonly']

def main():
    rid=os.getenv('YOUTUBE_REFRESH_TOKEN'); cid=os.getenv('YOUTUBE_CLIENT_ID'); secret=os.getenv('YOUTUBE_CLIENT_SECRET')
    if not all([rid,cid,secret]): raise SystemExit('YOUTUBE_ANALYTICS_CREDENTIALS_MISSING')
    creds=Credentials(None,refresh_token=rid,token_uri='https://oauth2.googleapis.com/token',client_id=cid,client_secret=secret,scopes=SCOPES)
    yt=build('youtube','v3',credentials=creds,cache_discovery=False)
    ya=build('youtubeAnalytics','v2',credentials=creds,cache_discovery=False)
    ch=yt.channels().list(part='id',mine=True).execute().get('items',[])
    if not ch: raise SystemExit('YOUTUBE_CHANNEL_NOT_FOUND')
    channel_id=ch[0]['id']
    end=date.today()-timedelta(days=1); start=end-timedelta(days=6)
    resp=ya.reports().query(ids=f'channel=={channel_id}',startDate=start.isoformat(),endDate=end.isoformat(),metrics='views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained',dimensions='video',sort='-views',maxResults=200).execute()
    cols=[c['name'] for c in resp.get('columnHeaders',[])]
    rows=[]
    for row in resp.get('rows',[]): rows.append(dict(zip(cols,row)))
    RUN_DIR.mkdir(parents=True,exist_ok=True); LEARNING_DIR.mkdir(parents=True,exist_ok=True)
    payload={'schema_version':'1.0','source':'YouTube Analytics API','channel_id':channel_id,'period':{'start':start.isoformat(),'end':end.isoformat()},'rows':rows}
    (RUN_DIR/'youtube_analytics.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (LEARNING_DIR/'youtube_analytics_latest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('YOUTUBE_ANALYTICS_COLLECTION=PASS rows=%d period=%s..%s' % (len(rows),start.isoformat(),end.isoformat()))
if __name__=='__main__': main()
