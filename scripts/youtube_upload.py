from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
STATE = RUN / "youtube_upload_state.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
UPLOAD_RETRIES = max(1, int(os.getenv("YOUTUBE_UPLOAD_RETRIES", "3")))
CHUNK_SIZE = 8 * 1024 * 1024
FINGERPRINT_PREFIX = "<!-- production-fingerprint:"


def _env(*names: str, required: bool = True) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    if required:
        raise RuntimeError(f"Missing YouTube credential: {' or '.join(names)}")
    return ""


def _credentials() -> Credentials:
    client_id = _env("YOUTUBE_CLIENT_ID")
    client_secret = _env("YOUTUBE_CLIENT_SECRET")
    refresh_token = _env("YOUTUBE_REFRESH_TOKEN")
    if client_id.startswith("{") or client_secret.startswith("{"):
        raise RuntimeError("YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be the OAuth client values, not JSON blobs")
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )


def _load_state() -> dict[str, Any]:
    if STATE.is_file():
        try:
            value = json.loads(STATE.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    return {"files": {}}


def _save_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _metadata() -> dict[str, Any]:
    path = RUN / "metadata.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    story = json.loads((RUN / "long_story.json").read_text(encoding="utf-8"))
    title = str(story.get("title", "")).strip() or "The Hidden Story Behind a Surprising Event"
    description = str(story.get("description", "")).strip() or f"Discover the hidden story behind {title}."
    tags = story.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {"title": title, "description": description, "tags": tags}


def _preflight(youtube: Any) -> None:
    try:
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
    except RefreshError as exc:
        raise RuntimeError("YouTube OAuth refresh failed. Check YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN; the refresh token must belong to the same OAuth client and include youtube.upload scope.") from exc
    except HttpError as exc:
        detail = getattr(exc, "content", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise RuntimeError(f"YouTube API preflight failed: HTTP {exc.resp.status}: {str(detail)[:1000]}") from exc
    channels = response.get("items", [])
    if not channels:
        raise RuntimeError("YouTube OAuth succeeded but no channel is accessible for the authenticated account")
    print(f"YOUTUBE_AUTH=PASS channel_id={channels[0].get('id', 'unknown')}")


def _description_with_fingerprint(description: str, fingerprint: str) -> str:
    marker = f"{FINGERPRINT_PREFIX} {fingerprint} -->"
    return (description[: 5000 - len(marker) - 2].rstrip() + "\n\n" + marker)[:5000]


def _find_existing(youtube: Any, channel_id: str, title: str, fingerprint: str) -> str | None:
    """Find a previous upload from any earlier run using a hidden deterministic marker."""
    try:
        response = youtube.search().list(
            part="id",
            channelId=channel_id,
            q=title[:100],
            type="video",
            maxResults=10,
        ).execute()
        ids = [str(item.get("id", {}).get("videoId", "")) for item in response.get("items", [])]
        ids = [video_id for video_id in ids if video_id]
        if not ids:
            return None
        videos = youtube.videos().list(part="snippet", id=",".join(ids)).execute()
        marker = f"{FINGERPRINT_PREFIX} {fingerprint} -->"
        for item in videos.get("items", []):
            if marker in str(item.get("snippet", {}).get("description", "")):
                return str(item["id"])
    except HttpError as exc:
        detail = getattr(exc, "content", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise RuntimeError(f"YouTube duplicate check failed: HTTP {exc.resp.status}: {str(detail)[:1000]}") from exc
    return None


def _upload(youtube: Any, path: Path, title: str, description: str, tags: list[str], privacy: str) -> str:
    last: Exception | None = None
    for attempt in range(1, UPLOAD_RETRIES + 1):
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": [str(t) for t in tags[:500]],
                    "categoryId": "24",
                },
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
            },
            media_body=MediaFileUpload(str(path), mimetype="video/mp4", chunksize=CHUNK_SIZE, resumable=True),
        )
        try:
            response = None
            while response is None:
                _, response = request.next_chunk()
            return str(response["id"])
        except RefreshError as exc:
            raise RuntimeError("YouTube OAuth refresh failed during upload; refresh token/client pair is invalid or expired") from exc
        except HttpError as exc:
            detail = getattr(exc, "content", b"")
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", "replace")
            last = RuntimeError(f"YouTube upload HTTP {exc.resp.status}: {str(detail)[:1200]}")
        except (OSError, TimeoutError, ConnectionError) as exc:
            last = exc
        if attempt < UPLOAD_RETRIES:
            wait = min(15, 2 ** (attempt - 1))
            print(f"YOUTUBE_UPLOAD_RETRY attempt={attempt + 1}/{UPLOAD_RETRIES} wait={wait}s reason={last}")
            time.sleep(wait)
    raise RuntimeError(f"YouTube upload failed after {UPLOAD_RETRIES} attempts: {last}") from last


def main() -> None:
    video = RUN / "video.mp4"
    shorts_dir = RUN / "shorts"
    if not video.is_file() or video.stat().st_size == 0:
        raise FileNotFoundError("video.mp4 is missing or empty")
    short_paths = [shorts_dir / f"short-{i}.mp4" for i in range(1, 5)]
    missing = [str(p) for p in short_paths if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Missing shorts: " + ", ".join(missing))

    meta = _metadata()
    privacy = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public")

    state = _load_state()
    files = state.setdefault("files", {})
    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    _preflight(youtube)
    channel = youtube.channels().list(part="id", mine=True).execute().get("items", [])
    channel_id = str(channel[0]["id"])

    long_fp = _fingerprint(video)
    long_title = str(meta.get("title", "The Hidden Story Behind a Surprising Event"))
    long_description = _description_with_fingerprint(str(meta.get("description", "")), long_fp)
    if long_fp not in files:
        existing_id = _find_existing(youtube, channel_id, long_title, long_fp)
        if existing_id:
            files[long_fp] = {"type": "long", "id": existing_id, "path": str(video), "privacy": privacy, "source": "youtube-existing"}
            _save_state(state)
            print(f"YOUTUBE_LONG_UPLOAD=SKIP_EXISTING id={existing_id}")
        else:
            video_id = _upload(youtube, video, long_title, long_description, list(meta.get("tags", [])), privacy)
            files[long_fp] = {"type": "long", "id": video_id, "path": str(video), "privacy": privacy}
            _save_state(state)
            print(f"YOUTUBE_LONG_UPLOAD=PASS id={video_id} privacy={privacy}")
    else:
        print(f"YOUTUBE_LONG_UPLOAD=SKIP id={files[long_fp]['id']}")

    for i, path in enumerate(short_paths, 1):
        fp = _fingerprint(path)
        title = f"{long_title} — Part {i}"
        description = _description_with_fingerprint(f"{title}\n\n{meta.get('description', '')}", fp)
        if fp in files:
            print(f"YOUTUBE_SHORT_{i}=SKIP id={files[fp]['id']}")
            continue
        existing_id = _find_existing(youtube, channel_id, title, fp)
        if existing_id:
            files[fp] = {"type": "short", "number": i, "id": existing_id, "privacy": privacy, "source": "youtube-existing"}
            _save_state(state)
            print(f"YOUTUBE_SHORT_{i}=SKIP_EXISTING id={existing_id}")
            continue
        short_id = _upload(youtube, path, title, description, list(meta.get("tags", [])), privacy)
        files[fp] = {"type": "short", "number": i, "id": short_id, "privacy": privacy}
        _save_state(state)
        print(f"YOUTUBE_SHORT_{i}_UPLOAD=PASS id={short_id} privacy={privacy}")

    print(f"YOUTUBE_UPLOAD=PASS long=1 shorts=4 privacy={privacy}")


if __name__ == "__main__":
    main()
