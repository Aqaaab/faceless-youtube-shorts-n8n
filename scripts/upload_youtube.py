#!/usr/bin/env python3
"""Upload the rendered Short to YouTube using an OAuth refresh token."""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
job = json.loads((RUN_DIR / "job.json").read_text(encoding="utf-8"))
video = RUN_DIR / "video.mp4"
if not video.is_file() or video.stat().st_size == 0:
    raise SystemExit(f"Missing rendered video: {video}")

required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
missing = [name for name in required if not os.environ.get(name, "").strip()]
if missing:
    raise SystemExit("Missing YouTube secrets: " + ", ".join(missing))

creds = Credentials(
    token=None,
    refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
    client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
    scopes=["https://www.googleapis.com/auth/youtube.upload"],
)
creds.refresh(Request())
youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

# Public is now the explicit workflow default; the environment variable can still
# override it with private or unlisted when intentionally requested.
privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "public").strip().lower()
if privacy not in {"private", "unlisted", "public"}:
    privacy = "public"

title = str(job.get("title", "Did You Know? #Shorts"))[:100]
description = str(job.get("description", ""))
tags = [str(tag).strip().lower() for tag in job.get("tags", []) if str(tag).strip()]

body = {
    "snippet": {
        "title": title,
        "description": description,
        "tags": tags[:15],
        "categoryId": "27",
    },
    "status": {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    },
}

media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"YouTube upload: {int(status.progress() * 100)}%")

print("YouTube upload complete")
print("VIDEO_ID=" + response["id"])
print("VIDEO_URL=https://www.youtube.com/shorts/" + response["id"])
