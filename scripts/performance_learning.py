#!/usr/bin/env python3
"""Collect lightweight YouTube performance signals and build model context.

Uses YouTube Data API statistics as a robust proxy. Average view duration and
retention are intentionally not inferred because they require YouTube Analytics
scope and are not available from this Data API call.
"""
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
LEARNING_DIR = Path(os.environ.get("LEARNING_DIR", ROOT / "learning"))
HISTORY_FILE = LEARNING_DIR / "performance.json"
CONTEXT_FILE = LEARNING_DIR / "context.txt"
RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def load_history() -> dict:
    if not HISTORY_FILE.is_file():
        return {"videos": []}
    try:
        value = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("videos"), list):
            return value
    except Exception as exc:  # noqa: BLE001
        print(f"Performance history unreadable; starting fresh: {exc}")
    return {"videos": []}


def save_history(history: dict) -> None:
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def youtube_client():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError("Missing YouTube credentials: " + ", ".join(missing))
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def age_days(created: str) -> float:
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return max((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 0.25)
    except Exception:
        return 1.0


def score(video: dict) -> float:
    views = safe_int(video.get("views"))
    likes = safe_int(video.get("likes"))
    comments = safe_int(video.get("comments"))
    days = age_days(str(video.get("created_at", "")))
    velocity = views / days
    engagement = ((likes * 2.0) + (comments * 3.0)) / max(views, 1)
    return velocity * (1.0 + min(engagement * 25.0, 2.0))


def refresh_stats(history: dict) -> bool:
    ids = [str(v.get("video_id", "")).strip() for v in history["videos"] if str(v.get("video_id", "")).strip()]
    if not ids:
        return False
    youtube = youtube_client()
    changed = False
    for start in range(0, len(ids), 50):
        response = youtube.videos().list(part="snippet,statistics", id=','.join(ids[start:start + 50])).execute()
        returned = {item["id"]: item for item in response.get("items", [])}
        for record in history["videos"]:
            item = returned.get(record.get("video_id"))
            if not item:
                continue
            statistics = item.get("statistics") or {}
            new_values = {
                "views": safe_int(statistics.get("viewCount")),
                "likes": safe_int(statistics.get("likeCount")),
                "comments": safe_int(statistics.get("commentCount")),
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }
            for key, value in new_values.items():
                if record.get(key) != value:
                    record[key] = value
                    changed = True
    for record in history["videos"]:
        record["score"] = round(score(record), 2)
    return changed


def record_upload(history: dict) -> bool:
    log_file = RUN_DIR / "upload.log"
    if not log_file.is_file():
        print("No upload.log found; nothing to record")
        return False
    text = log_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"VIDEO_ID=([A-Za-z0-9_-]+)", text)
    if not match:
        print("No VIDEO_ID found in upload log; nothing recorded")
        return False
    video_id = match.group(1)
    job_file = RUN_DIR / "job.json"
    job = json.loads(job_file.read_text(encoding="utf-8")) if job_file.is_file() else {}
    existing = next((v for v in history["videos"] if v.get("video_id") == video_id), None)
    record = existing or {
        "video_id": video_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "views": 0,
        "likes": 0,
        "comments": 0,
    }
    record.update({
        "title": str(job.get("title", "")),
        "topic": str(job.get("topic", "")),
        "category": str(job.get("category", "")),
        "hook": str(job.get("hook", "")),
        "provider": str(job.get("provider", "")),
        "duration_target": "30-60",
    })
    if not existing:
        history["videos"].append(record)
    record["score"] = round(score(record), 2)
    return True


def build_context(history: dict) -> str:
    videos = history.get("videos", [])
    ranked = sorted(videos, key=score, reverse=True)
    top = ranked[:8]
    bottom = sorted(videos, key=score)[:5]
    lines = [
        "Use these observations only to improve structure and topic selection.",
        "Views, likes, comments are observed channel statistics; they are not guaranteed predictions.",
        "Retention/average view duration is not available in this lightweight data-only loop.",
        "",
    ]
    if top:
        lines.append("TOP PERFORMERS:")
        for item in top:
            lines.append(
                f"- topic={item.get('topic','')} | score={item.get('score',0)} | views={item.get('views',0)} | likes={item.get('likes',0)} | comments={item.get('comments',0)} | hook={item.get('hook','')[:180]}"
            )
    if bottom:
        lines.append("\nLOWER PERFORMERS:")
        for item in bottom:
            lines.append(
                f"- topic={item.get('topic','')} | score={item.get('score',0)} | views={item.get('views',0)} | hook={item.get('hook','')[:180]}"
            )
    topic_counts = {}
    for item in videos:
        topic = str(item.get("category") or item.get("topic") or "").strip().lower()
        if topic:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    if topic_counts:
        lines.append("\nTOPIC FREQUENCY:")
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:8]:
            lines.append(f"- {topic}: {count} videos")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--record-upload", action="store_true")
    parser.add_argument("--write-context", action="store_true")
    args = parser.parse_args()

    history = load_history()
    changed = False
    if args.update:
        try:
            changed = refresh_stats(history) or changed
            print("Updated YouTube performance statistics")
        except Exception as exc:  # graceful degradation: never block content production
            print(f"Performance update skipped: {exc}")
            print("This can happen when the current refresh token was created without YouTube read-only scope.")
    if args.record_upload:
        changed = record_upload(history) or changed
    if changed:
        save_history(history)
    if args.write_context:
        LEARNING_DIR.mkdir(parents=True, exist_ok=True)
        CONTEXT_FILE.write_text(build_context(history), encoding="utf-8")
        print(f"Wrote {CONTEXT_FILE}")
        if not HISTORY_FILE.is_file():
            save_history(history)


if __name__ == "__main__":
    main()
