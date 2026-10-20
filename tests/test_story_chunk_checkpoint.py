from __future__ import annotations

import json
import re

import pytest

from app import pipeline


def _story_chunk(start: int, end: int, *, include_metadata: bool) -> dict:
    scenes = []
    layouts = ("hero", "technical", "spec", "comparison", "diagram")
    for scene_id in range(start, end + 1):
        narration = " ".join(["سيارة"] * 32)
        scenes.append({
            "id": scene_id,
            "narration": narration,
            "visual_intent": f"لقطة سينمائية مختلفة للسيارة والمشهد رقم {scene_id}",
            "layout": layouts[(scene_id - 1) % len(layouts)],
            "callouts": [],
            "duration": 18.0,
        })
    result = {"scenes": scenes}
    if include_metadata:
        result.update({
            "title": "عنوان تجريبي لفيديو سيارات فاخر",
            "description": "وصف تفصيلي للحلقة التجريبية يشرح التصميم والتقنية وتجربة القيادة. " * 4,
            "tags": ["سيارات", "تصميم", "تقنية", "قيادة", "مقارنة"],
            "short_titles": ["العنوان القصير الأول", "العنوان القصير الثاني", "العنوان القصير الثالث", "العنوان القصير الرابع"],
            "fact_brief": "استخدم المعلومات الواردة في النص فقط ولا تضف أرقاماً غير مدعومة.",
        })
    return result


def test_story_chunks_resume_after_rate_limit_without_regenerating_saved_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_SCENE_CHUNK_SIZE", "5")
    monkeypatch.setenv("STORY_CHUNK_ATTEMPTS", "3")
    monkeypatch.setenv("ACE_STORY_CHECKPOINT_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("AUTOMOTIVE_PROFILE", "premium_coupe")
    monkeypatch.setattr(pipeline, "_story_chunk_system", lambda *_args: "system")
    monkeypatch.setattr(pipeline, "_normalize_for_validation", lambda value: value)
    monkeypatch.setattr(pipeline, "_deterministic_structure_repair", lambda value: value)
    monkeypatch.setattr(pipeline, "validate_story_data", lambda _value: None)
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)

    calls: list[tuple[int, int]] = []
    fail_middle_chunk = True

    def ask(_system, user, *, timeout=None, max_attempts=None):
        nonlocal fail_middle_chunk
        match = re.search(r"Chunk ids: (\d+)-(\d+)", user)
        assert match
        start, end = int(match.group(1)), int(match.group(2))
        calls.append((start, end))
        if start == 11 and fail_middle_chunk:
            raise RuntimeError("HTTP 429 upstream quota exhausted")
        return _story_chunk(start, end, include_metadata=(start == 1))

    monkeypatch.setattr(pipeline, "ask_odysseus", ask)

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        pipeline._generate_story_chunks("موضوع اختبار الاستئناف")

    checkpoint_path = pipeline._story_chunk_checkpoint_path("موضوع اختبار الاستئناف", 5)
    saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert len(saved["chunks"]) == 10
    assert [scene["id"] for scene in saved["chunks"]] == list(range(1, 11))

    calls.clear()
    fail_middle_chunk = False
    result = pipeline._generate_story_chunks("موضوع اختبار الاستئناف")

    assert [start for start, _end in calls] == [11, 16, 21]
    assert [scene["id"] for scene in result["scenes"]] == list(range(1, 26))
    complete = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert complete["complete"] is True
    assert len(complete["chunks"]) == 25


def test_story_checkpoint_does_not_cross_topic_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_STORY_CHECKPOINT_DIR", str(tmp_path))
    a = pipeline._story_chunk_checkpoint_path("topic A", 5)
    b = pipeline._story_chunk_checkpoint_path("topic B", 5)
    assert a != b


def test_malformed_story_checkpoint_metadata_is_invalidated_safely(tmp_path, monkeypatch):
    monkeypatch.setenv("ACE_STORY_CHECKPOINT_DIR", str(tmp_path))
    topic = "موضوع checkpoint غير صالح"
    path = pipeline._story_chunk_checkpoint_path(topic, 5)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": pipeline.STORY_CHUNK_CHECKPOINT_VERSION,
        "topic": topic,
        "chunk_size": 5,
        "chunks": [{"id": 1}],
        "metadata": None,
        "fact_brief": "",
        "invalidated": False,
    }), encoding="utf-8")

    _loaded_path, state = pipeline._load_story_chunk_checkpoint(topic, 5)

    assert state["invalidated"] is True
    assert state["chunks"] == []
