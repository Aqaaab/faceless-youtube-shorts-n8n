#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/daily-production'))
SOURCE = RUN_DIR / 'video.mp4'
MANIFEST = RUN_DIR / 'short_factory_manifest.json'


def youtube_client():
    required = ['YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN']
    missing = [x for x in required if not os.environ.get(x, '').strip()]
    if missing:
        raise SystemExit('Missing YouTube secrets: ' + ', '.join(missing))
    creds = Credentials(
        token=None,
        refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'].strip(),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.environ['YOUTUBE_CLIENT_ID'].strip(),
        client_secret=os.environ['YOUTUBE_CLIENT_SECRET'].strip(),
        scopes=['https://www.googleapis.com/auth/youtube.upload'],
    )
    creds.refresh(Request())
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def upload(youtube, path: Path, title: str, description: str, tags: list[str], privacy: str) -> str:
    body = {
        'snippet': {
            'title': title[:100],
            'description': description,
            'tags': tags[:15],
            'categoryId': '27',
        },
        'status': {
            'privacyStatus': privacy,
            'selfDeclaredMadeForKids': False,
        },
    }
    media = MediaFileUpload(str(path), mimetype='video/mp4', resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f'YouTube upload {path.name}: {int(status.progress() * 100)}%')
    return response['id']


def main():
    if not SOURCE.is_file() or SOURCE.stat().st_size == 0:
        raise SystemExit('LONG_VIDEO_MISSING')
    if not MANIFEST.is_file():
        raise SystemExit('SHORT_FACTORY_MANIFEST_MISSING')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    shorts = manifest.get('shorts', [])
    if len(shorts) != 4:
        raise SystemExit(f'EXPECTED_4_SHORTS_GOT_{len(shorts)}')

    story = {}
    job = RUN_DIR / 'job.json'
    long_story = RUN_DIR / 'long_story.json'
    if job.is_file():
        story = json.loads(job.read_text(encoding='utf-8'))
    elif long_story.is_file():
        story = json.loads(long_story.read_text(encoding='utf-8'))

    privacy = os.environ.get('YOUTUBE_PRIVACY_STATUS', 'public').strip().lower()
    if privacy not in {'private', 'unlisted', 'public'}:
        privacy = 'public'
    youtube = youtube_client()
    results = {'privacy': privacy, 'long_video': None, 'shorts': []}

    long_title = str(story.get('title', 'Full Story'))[:100]
    long_desc = str(story.get('description', ''))
    long_tags = [str(x).lower() for x in story.get('tags', []) if str(x).strip()]
    long_id = upload(youtube, SOURCE, long_title, long_desc, long_tags, privacy)
    results['long_video'] = {'video_id': long_id, 'video_url': f'https://www.youtube.com/watch?v={long_id}', 'title': long_title}

    for item in sorted(shorts, key=lambda x: int(x.get('short_number', 0))):
        path = Path(item['path'])
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            alt = RUN_DIR / 'shorts' / path.name
            if alt.is_file(): path = alt
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f'SHORT_FILE_MISSING: {item.get("short_number")}')
        title = str(item.get('title') or f"{story.get('topic', 'Story')} — Part {item.get('short_number')} #Shorts")
        desc = str(item.get('description') or '')
        tags = ['shorts', 'story', 'facts', 'explained', 'education']
        sid = upload(youtube, path, title, desc, tags, privacy)
        results['shorts'].append({'short_number': item.get('short_number'), 'video_id': sid, 'video_url': f'https://www.youtube.com/shorts/{sid}', 'title': title})
        print(f'Published Short {item.get("short_number")}: {sid}')

    (RUN_DIR / 'youtube_publish.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('YOUTUBE_LONGFORM_PLUS_4_SHORTS=PASS')


if __name__ == '__main__':
    main()
