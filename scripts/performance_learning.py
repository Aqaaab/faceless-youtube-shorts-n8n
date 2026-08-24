#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
LEARNING = Path(os.getenv("LEARNING_DIR", ROOT / "learning"))
HISTORY = LEARNING / "performance.json"
CONTEXT = LEARNING / "context.txt"
RUN = Path(os.getenv("RUN_DIR", "data/run"))


def load():
    if not HISTORY.is_file():
        return {"videos": []}
    try:
        d = json.loads(HISTORY.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("videos"), list) else {"videos": []}
    except Exception as exc:
        print(f"History reset: {exc}")
        return {"videos": []}


def save(d):
    LEARNING.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def client():
    # Public video statistics do not require the OAuth refresh token. Prefer the
    # Data API key so learning cannot fail because a refresh token was minted
    # without youtube.readonly scope.
    api_key = os.environ.get("YOUTUBE_DATA_API_KEY", "").strip()
    if api_key:
        return build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    # OAuth remains a fallback for installations that do not provide a Data API key.
    required = ["YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET"]
    if not all(os.environ.get(name, "").strip() for name in required):
        raise RuntimeError("YouTube performance learning requires YOUTUBE_DATA_API_KEY or complete OAuth credentials")
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def num(x):
    try:
        return int(x or 0)
    except Exception:
        return 0


def score(v):
    try:
        age = max(
            (datetime.now(timezone.utc) - datetime.fromisoformat(v.get("created_at", "").replace("Z", "+00:00"))).total_seconds() / 86400,
            0.25,
        )
    except Exception:
        age = 1
    views = num(v.get("views"))
    likes = num(v.get("likes"))
    comments = num(v.get("comments"))
    return (views / age) * (1 + min((((likes * 2) + (comments * 3)) / max(views, 1)) * 25, 2))


def update(d):
    ids = [str(v.get("video_id", "")) for v in d["videos"] if v.get("video_id")]
    if not ids:
        return False

    y = client()
    changed = False
    for i in range(0, len(ids), 50):
        response = y.videos().list(part="statistics", id=",".join(ids[i : i + 50])).execute()
        items = {x["id"]: x for x in response.get("items", [])}
        for video in d["videos"]:
            item = items.get(video.get("video_id"))
            if not item:
                continue
            stats = item.get("statistics") or {}
            new_values = {
                "views": num(stats.get("viewCount")),
                "likes": num(stats.get("likeCount")),
                "comments": num(stats.get("commentCount")),
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }
            if any(video.get(key) != value for key, value in new_values.items()):
                changed = True
            video.update(new_values)
            video["score"] = round(score(video), 2)
    return changed


def record(d):
    log = RUN / "upload.log"
    job = RUN / "job.json"
    if not log.is_file():
        return False
    match = re.search(r"VIDEO_ID=([A-Za-z0-9_-]+)", log.read_text(encoding="utf-8", errors="replace"))
    if not match:
        return False

    data = json.loads(job.read_text(encoding="utf-8")) if job.is_file() else {}
    video_id = match.group(1)
    old = next((v for v in d["videos"] if v.get("video_id") == video_id), None)
    video = old or {
        "video_id": video_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "views": 0,
        "likes": 0,
        "comments": 0,
    }
    video.update(
        {
            "title": str(data.get("title", "")),
            "topic": str(data.get("topic", "")),
            "category": str(data.get("category", "")),
            "hook": str(data.get("hook", "")),
            "provider": str(data.get("provider", "")),
        }
    )
    if not old:
        d["videos"].append(video)
    video["score"] = round(score(video), 2)
    return True


def context(d):
    videos = d.get("videos", [])
    top = sorted(videos, key=score, reverse=True)[:8]
    low = sorted(videos, key=score)[:5]
    out = [
        "Use these observations only to improve structure/topic selection.",
        "Views/likes/comments are channel-level proxy signals; retention is not inferred.",
        "",
    ]
    if top:
        out += ["TOP PERFORMERS:"] + [
            f"- topic={v.get('topic','')} | score={v.get('score',0)} | views={v.get('views',0)} | likes={v.get('likes',0)} | hook={v.get('hook','')[:180]}"
            for v in top
        ]
    if low:
        out += ["", "LOWER PERFORMERS:"] + [
            f"- topic={v.get('topic','')} | score={v.get('score',0)} | views={v.get('views',0)} | hook={v.get('hook','')[:180]}"
            for v in low
        ]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--record-upload", action="store_true")
    parser.add_argument("--write-context", action="store_true")
    args = parser.parse_args()

    data = load()
    changed = False

    if args.update:
        try:
            changed = update(data) or changed
            print("Performance stats updated")
        except Exception as exc:
            print(f"Performance update skipped: {exc}")

    if args.record_upload:
        changed = record(data) or changed

    if changed:
        save(data)

    if args.write_context:
        LEARNING.mkdir(parents=True, exist_ok=True)
        CONTEXT.write_text(context(data), encoding="utf-8")
        if not HISTORY.is_file():
            save(data)
        print("Learning context written")


if __name__ == "__main__":
    main()
