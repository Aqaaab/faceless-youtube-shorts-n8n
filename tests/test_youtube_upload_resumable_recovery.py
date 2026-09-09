from __future__ import annotations

from pathlib import Path

from googleapiclient.errors import HttpError

from youtube_upload import _upload


class _Response:
    status = 500
    reason = "Internal Server Error"


class _Request:
    def __init__(self) -> None:
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        if self.calls == 1:
            raise HttpError(_Response(), b'{"error":{"message":"transient"}}')
        return None, {"id": "recovered-video-id"}


class _Videos:
    def __init__(self) -> None:
        self.insert_calls = 0
        self.request = _Request()

    def insert(self, **kwargs):
        self.insert_calls += 1
        return self.request


class _YouTube:
    def __init__(self) -> None:
        self.videos_api = _Videos()

    def videos(self):
        return self.videos_api


def test_upload_recovers_without_creating_duplicate_insert(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"test-video")
    youtube = _YouTube()
    monkeypatch.setattr("youtube_upload.UPLOAD_RETRIES", 2)
    monkeypatch.setattr("youtube_upload.time.sleep", lambda _seconds: None)

    video_id = _upload(
        youtube,
        source,
        "Recovery test",
        "A valid recovery test description.",
        ["automotive"],
        "public",
    )

    assert video_id == "recovered-video-id"
    assert youtube.videos_api.insert_calls == 1
    assert youtube.videos_api.request.calls == 2
