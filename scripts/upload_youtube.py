#!/usr/bin/env python3
"""Upload the rendered Short and its explanatory thumbnail to YouTube."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RUN_DIR=Path(os.environ.get('RUN_DIR','data/run')); job=json.loads((RUN_DIR/'job.json').read_text(encoding='utf-8')); video=RUN_DIR/'video.mp4'; thumb=RUN_DIR/'thumbnail.jpg'
if not video.is_file() or video.stat().st_size==0: raise SystemExit(f'Missing rendered video: {video}')
if not thumb.is_file() or thumb.stat().st_size==0: raise SystemExit(f'Missing thumbnail: {thumb}')
required=['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REFRESH_TOKEN']; missing=[x for x in required if not os.environ.get(x,'').strip()]
if missing: raise SystemExit('Missing YouTube secrets: '+', '.join(missing))
creds=Credentials(token=None,refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'].strip(),token_uri='https://oauth2.googleapis.com/token',client_id=os.environ['YOUTUBE_CLIENT_ID'].strip(),client_secret=os.environ['YOUTUBE_CLIENT_SECRET'].strip(),scopes=['https://www.googleapis.com/auth/youtube.upload'])
creds.refresh(Request()); youtube=build('youtube','v3',credentials=creds,cache_discovery=False)
privacy=os.environ.get('YOUTUBE_PRIVACY_STATUS','public').strip().lower(); privacy=privacy if privacy in {'private','unlisted','public'} else 'public'
title=str(job.get('title','Did You Know? #Shorts'))[:100]; description=str(job.get('description','')); tags=[str(t).strip().lower() for t in job.get('tags',[]) if str(t).strip()]
body={'snippet':{'title':title,'description':description,'tags':tags[:15],'categoryId':'27'},'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':False}}
media=MediaFileUpload(str(video),mimetype='video/mp4',resumable=True,chunksize=8*1024*1024); request=youtube.videos().insert(part='snippet,status',body=body,media_body=media); response=None
while response is None:
 status,response=request.next_chunk()
 if status: print(f'YouTube upload: {int(status.progress()*100)}%')
video_id=response['id']; print('YouTube upload complete'); print('VIDEO_ID='+video_id); print('VIDEO_URL=https://www.youtube.com/shorts/'+video_id)
# Thumbnail is a separate API operation; retry only transient failures.
for attempt in range(1,4):
 try:
  youtube.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(str(thumb),mimetype='image/jpeg')).execute(); print('YouTube thumbnail upload complete'); break
 except Exception as e:
  if attempt==3: raise
  delay=2**(attempt-1); print(f'Thumbnail upload retry {attempt+1}/3 after {delay}s: {e}'); time.sleep(delay)
(RUN_DIR/'youtube_publish.json').write_text(json.dumps({'video_id':video_id,'video_url':'https://www.youtube.com/shorts/'+video_id,'thumbnail_uploaded':True,'title':title,'description':description},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
