from __future__ import annotations

import hashlib
import json
import os
import time
import unicodedata
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
SCOPES = ["https://www.googleapis.com/auth/youtube"]
UPLOAD_RETRIES = max(1, int(os.getenv("YOUTUBE_UPLOAD_RETRIES", "3")))
CHUNK_SIZE = 8 * 1024 * 1024
FINGERPRINT_PREFIX = "[production-fingerprint:"


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
        raise RuntimeError("YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be OAuth client values, not JSON blobs")
    return Credentials(token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token", client_id=client_id, client_secret=client_secret, scopes=SCOPES)


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
    tags = story.get("tags", []) if isinstance(story.get("tags", []), list) else []
    return {"title": title, "description": description, "tags": tags}


def _youtube_safe_text(value: Any, limit: int = 5000) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 > limit:
        encoded = encoded[:limit * 2]
        if len(encoded) >= 2 and 0xD800 <= int.from_bytes(encoded[-2:], "little") <= 0xDBFF:
            encoded = encoded[:-2]
        text = encoded.decode("utf-16-le", errors="ignore").rstrip()
    return text


def _preflight(youtube: Any) -> None:
    try:
        response = youtube.channels().list(part="id,snippet", mine=True).execute()
    except RefreshError as exc:
        raise RuntimeError("YouTube OAuth refresh failed; check client ID/secret and refresh token scopes") from exc
    except HttpError as exc:
        detail = getattr(exc, "content", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise RuntimeError(f"YouTube API preflight failed: HTTP {exc.resp.status}: {str(detail)[:1000]}") from exc
    channels = response.get("items", [])
    if not channels:
        raise RuntimeError("YouTube OAuth succeeded but no channel is accessible")
    print(f"YOUTUBE_AUTH=PASS channel_id={channels[0].get('id', 'unknown')}")


def _description_with_fingerprint(description: str, fingerprint: str) -> str:
    marker = f"{FINGERPRINT_PREFIX}{fingerprint}]"
    base = _youtube_safe_text(description, max(0, 5000 - len(marker) - 2))
    return _youtube_safe_text(f"{base}\n\n{marker}", 5000)


def _find_existing(youtube: Any, channel_id: str, title: str, fingerprint: str) -> str | None:
    try:
        response = youtube.search().list(part="id", channelId=channel_id, q=_youtube_safe_text(title, 100), type="video", maxResults=10).execute()
        ids = [str(item.get("id", {}).get("videoId", "")) for item in response.get("items", [])]
        ids = [x for x in ids if x]
        if not ids:
            return None
        marker = f"{FINGERPRINT_PREFIX}{fingerprint}]"
        videos = youtube.videos().list(part="snippet", id=",".join(ids)).execute()
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
    safe_title = _youtube_safe_text(title, 100)
    safe_description = _youtube_safe_text(description, 5000)
    safe_tags = [_youtube_safe_text(t, 500) for t in tags[:500] if _youtube_safe_text(t, 500)]
    if not safe_title:
        raise ValueError("YouTube title is empty after sanitization")
    if not safe_description:
        safe_description = safe_title
    last: Exception | None = None
    for attempt in range(1, UPLOAD_RETRIES + 1):
        request = youtube.videos().insert(part="snippet,status", body={"snippet": {"title": safe_title, "description": safe_description, "tags": safe_tags, "categoryId": "24"}, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}, media_body=MediaFileUpload(str(path), mimetype="video/mp4", chunksize=CHUNK_SIZE, resumable=True))
        try:
            response = None
            while response is None:
                _, response = request.next_chunk()
            return str(response["id"])
        except RefreshError as exc:
            raise RuntimeError("YouTube OAuth refresh failed during upload") from exc
        except HttpError as exc:
            detail = getattr(exc, "content", b"")
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", "replace")
            status = int(getattr(exc.resp, "status", 0) or 0)
            last = RuntimeError(f"YouTube upload HTTP {status}: {str(detail)[:1200]}")
            if status < 500 and status != 429:
                raise last from exc
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

    plan_path = RUN / "shorts_plan.json"
    plan = {}
    if plan_path.is_file():
        loaded = json.loads(plan_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            plan = loaded
    plan_by_id = {int(s.get("id")): s for s in plan.get("shorts", []) if isinstance(s, dict) and str(s.get("id", "")).isdigit()}

    state = _load_state()
    files = state.setdefault("files", {})
    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    _preflight(youtube)
    channel = youtube.channels().list(part="id", mine=True).execute().get("items", [])
    channel_id = str(channel[0]["id"])

    long_fp = _fingerprint(video)
    long_title = _youtube_safe_text(meta.get("title", "The Hidden Story Behind a Surprising Event"), 100)
    long_description = _description_with_fingerprint(str(meta.get("description", "")), long_fp)
    if long_fp not in files:
        existing_id = _find_existing(youtube, channel_id, long_title, long_fp)
        if existing_id:
            files[long_fp] = {"type": "long", "id": existing_id, "privacy": privacy, "source": "youtube-existing"}
            _save_state(state)
            print(f"YOUTUBE_LONG_UPLOAD=SKIP_EXISTING id={existing_id}")
        else:
            video_id = _upload(youtube, video, long_title, long_description, list(meta.get("tags", [])), privacy)
            files[long_fp] = {"type": "long", "id": video_id, "privacy": privacy}
            _save_state(state)
            print(f"YOUTUBE_LONG_UPLOAD=PASS id={video_id} privacy={privacy}")
    else:
        print(f"YOUTUBE_LONG_UPLOAD=SKIP id={files[long_fp]['id']}")

    for i, path in enumerate(short_paths, 1):
        fp = _fingerprint(path)
        item = plan_by_id.get(i, {})
        title = _youtube_safe_text(item.get("title") or f"{long_title} — Story #{i}", 100)
        description = _description_with_fingerprint(str(item.get("description") or f"{title}\n\n{meta.get('description', '')}"), fp)
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
