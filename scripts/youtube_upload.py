from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
STATE = RUN / "youtube_upload_state.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _env(*names: str, required: bool = True) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    if required:
        raise RuntimeError(f"Missing YouTube credential: {' or '.join(names)}")
    return ""


def _credentials() -> Credentials:
    client_id = _env("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_ID_JSON")
    client_secret = _env("YOUTUBE_CLIENT_SECRET", "YOUTUBE_CLIENT_SECRET_JSON")
    refresh_token = _env("YOUTUBE_REFRESH_TOKEN")
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
        return json.loads(STATE.read_text(encoding="utf-8"))
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
    return {
        "title": story.get("title", "Untitled Story"),
        "description": story.get("description", ""),
        "tags": story.get("tags", []),
    }


def _upload(youtube: Any, path: Path, title: str, description: str, tags: list[str], privacy: str) -> str:
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
        media_body=MediaFileUpload(str(path), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return str(response["id"])


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
    privacy = os.getenv("YOUTUBE_PRIVACY_STATUS", "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public")

    state = _load_state()
    files = state.setdefault("files", {})
    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)

    long_fp = _fingerprint(video)
    if long_fp not in files:
        video_id = _upload(
            youtube,
            video,
            str(meta.get("title", "Untitled Story")),
            str(meta.get("description", "")),
            list(meta.get("tags", [])),
            privacy,
        )
        files[long_fp] = {"type": "long", "id": video_id, "path": str(video)}
        _save_state(state)
        print(f"YOUTUBE_LONG_UPLOAD=PASS id={video_id}")
    else:
        print(f"YOUTUBE_LONG_UPLOAD=SKIP id={files[long_fp]['id']}")

    for i, path in enumerate(short_paths, 1):
        fp = _fingerprint(path)
        if fp in files:
            print(f"YOUTUBE_SHORT_{i}=SKIP id={files[fp]['id']}")
            continue
        title = f"{meta.get('title', 'Story')} — Short {i}"
        description = f"A short excerpt from: {meta.get('title', 'Story')}\n\n{meta.get('description', '')}"[:5000]
        short_id = _upload(youtube, path, title, description, list(meta.get("tags", [])), privacy)
        files[fp] = {"type": "short", "number": i, "id": short_id, "path": str(path)}
        _save_state(state)
        print(f"YOUTUBE_SHORT_{i}_UPLOAD=PASS id={short_id}")

    print("YOUTUBE_UPLOAD=PASS long=1 shorts=4")


if __name__ == "__main__":
    main()
