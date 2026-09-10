import hashlib
import json
import os
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 5000


def service():
    credentials = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _clean_text(value, limit):
    text = str(value or "")
    # YouTube rejects C0 control characters. Preserve normal Unicode/Arabic text.
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()[:limit]


def _marker(path):
    return " [ACE:" + fingerprint(path)[:12] + "]"


def _final_title(title, marker):
    base = _clean_text(title, MAX_TITLE_CHARS)
    if len(base) + len(marker) <= MAX_TITLE_CHARS:
        return base + marker
    return base[: MAX_TITLE_CHARS - len(marker)].rstrip() + marker


def existing_titles(svc, marker):
    channels = svc.channels().list(part="id", mine=True).execute().get("items", [])
    if not channels:
        raise RuntimeError("YouTube OAuth succeeded but no channel is accessible to this token")
    channel_id = channels[0]["id"]
    out = []
    token = None
    while True:
        data = svc.search().list(
            part="snippet",
            channelId=channel_id,
            forMine=True,
            type="video",
            maxResults=50,
            pageToken=token or "",
        ).execute()
        out.extend(x["snippet"]["title"] for x in data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            break
    return any(marker in title for title in out)


def upload(path, title, description, tags, svc):
    privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "public").strip().lower()
    if privacy not in {"public", "private", "unlisted"}:
        raise ValueError("YOUTUBE_PRIVACY_STATUS must be public, private or unlisted")

    marker = _marker(path)
    final_title = _final_title(title, marker)
    if existing_titles(svc, marker):
        return "SKIPPED_DUPLICATE"

    clean_description = _clean_text(description, MAX_DESCRIPTION_CHARS)
    clean_tags = []
    for tag in tags or []:
        clean = _clean_text(tag, 500)
        if clean:
            clean_tags.append(clean)

    body = {
        "snippet": {
            "title": final_title,
            "description": clean_description,
            "tags": clean_tags[:500],
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    request = svc.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(path), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def main():
    root = Path("work")
    state_file = root / "uploaded.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    story = json.loads((root / "story.json").read_text(encoding="utf-8"))
    svc = service()

    items = [("master_final.mp4", story["title"], "long")]
    items += [
        (f"shorts/short_{i}.mp4", f"{story['title']} — Short {i}", f"short_{i}")
        for i in range(1, 5)
    ]

    for rel, title, kind in items:
        path = root / rel
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError(f"Missing upload artifact: {path}")
        fp = fingerprint(path)
        if state.get(kind, {}).get("fingerprint") == fp:
            continue
        video_id = upload(path, title, story["description"], story.get("tags", []), svc)
        state[kind] = {"fingerprint": fp, "video_id": video_id}
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
