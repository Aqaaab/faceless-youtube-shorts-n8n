from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import upload as upload_module


def _fake_service(items):
    calls = []

    def channel_list(**kwargs):
        calls.append(("channels", kwargs))
        return SimpleNamespace(execute=lambda: {"items": [{"id": "channel-1"}]})

    def search_list(**kwargs):
        calls.append(("search", kwargs))
        return SimpleNamespace(execute=lambda: {"items": items})

    service = SimpleNamespace(
        channels=lambda: SimpleNamespace(list=channel_list),
        search=lambda: SimpleNamespace(list=search_list),
    )
    return service, calls


def test_existing_video_id_returns_canonical_id_for_duplicate_marker():
    service, calls = _fake_service([
        {
            "id": {"kind": "youtube#video", "videoId": "abc123"},
            "snippet": {"title": "An automotive video [ACE:deadbeef1234]"},
        }
    ])

    result = upload_module.existing_video_id(service, "[ACE:deadbeef1234]")

    assert result == "abc123"
    search_call = next(kwargs for kind, kwargs in calls if kind == "search")
    assert search_call["part"] == "id,snippet"
    assert search_call["channelId"] == "channel-1"


def test_duplicate_marker_without_video_id_fails_closed():
    service, _ = _fake_service([
        {
            "id": {"kind": "youtube#searchResult"},
            "snippet": {"title": "An automotive video [ACE:deadbeef1234]"},
        }
    ])

    with pytest.raises(RuntimeError, match="no video ID"):
        upload_module.existing_video_id(service, "[ACE:deadbeef1234]")


def test_upload_state_survives_thumbnail_failure_and_resumes_without_reupload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("work")
    (root / "shorts").mkdir(parents=True)
    story = {
        "title": "اختبار فيديو السيارات",
        "description": "وصف تجريبي طويل بما يكفي لاختبار دورة النشر.",
        "tags": ["سيارات", "اختبار"],
        "short_titles": ["مقطع واحد", "مقطع اثنان", "مقطع ثلاثة", "مقطع أربعة"],
    }
    (root / "story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
    (root / "master_final.mp4").write_bytes(b"master-video")
    (root / "thumbnail.jpg").write_bytes(b"thumbnail")
    for index in range(1, 5):
        (root / "shorts" / f"short_{index}.mp4").write_bytes(f"short-{index}".encode())

    monkeypatch.setattr(upload_module, "_require_final_qa", lambda _root: {})
    monkeypatch.setattr(upload_module, "service", lambda: object())

    uploaded_names: list[str] = []

    def fake_upload(path, _title, _description, _tags, _svc):
        uploaded_names.append(Path(path).name)
        return "video-master" if Path(path).name == "master_final.mp4" else f"video-{Path(path).stem}"

    thumbnail_attempts = 0

    def flaky_thumbnail(_svc, _video_id, _thumbnail):
        nonlocal thumbnail_attempts
        thumbnail_attempts += 1
        if thumbnail_attempts == 1:
            raise RuntimeError("temporary thumbnail failure")

    monkeypatch.setattr(upload_module, "upload", fake_upload)
    monkeypatch.setattr(upload_module, "set_thumbnail", flaky_thumbnail)

    with pytest.raises(RuntimeError, match="temporary thumbnail failure"):
        upload_module.main()

    state_path = root / "uploaded.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["long"]["video_id"] == "video-master"
    assert state["long"]["fingerprint"] == upload_module.fingerprint(root / "master_final.mp4")
    assert state["long"]["thumbnail_set"] is False

    monkeypatch.setattr(upload_module, "set_thumbnail", lambda *_args: None)
    upload_module.main()

    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert uploaded_names.count("master_final.mp4") == 1
    assert final_state["long"]["video_id"] == "video-master"
    assert final_state["long"]["thumbnail_set"] is True
    assert len([key for key in final_state if key.startswith("short_")]) == 4
