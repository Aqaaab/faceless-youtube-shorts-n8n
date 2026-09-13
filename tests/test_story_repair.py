from __future__ import annotations

import json

from app.core import _deterministic_structure_repair
from app.pipeline import generate_story_resilient
from app.validator import validate_story_data


def _scene(i: int) -> dict:
    return {
        "id": i,
        "narration": "هذه سيارة حديثة تجمع بين التصميم والتقنية والأداء مع تفاصيل واضحة تساعد على فهم الطراز وتجربة القيادة بشكل متوازن ودقيق دون مبالغة في المعلومات المعروضة",
        "visual_intent": f"لقطة سيارة أمامية مع تكوين سينمائي وتفصيل بصري للمشهد {i}",
        "layout": ["hero", "technical", "spec", "comparison", "diagram", "timeline"][i % 6],
        "callouts": ["أداء متوازن", "رقم 999 غير مدعوم"],
        "duration": 50.0,
    }


def _strong_story_payload() -> dict:
    scenes = [_scene(i) for i in range(1, 26)]
    for scene in scenes:
        scene["duration"] = 18.0
        scene["callouts"] = ["أداء متوازن"]
    return {
        "topic": "موضوع سيارة",
        "title": "السيارة الحديثة بالتفصيل: التصميم والتقنية والأداء",
        "description": "تحليل عربي منظم يشرح التصميم والتقنيات والأداء وتجربة الاستخدام عبر مشاهد مترابطة ومعلومات واضحة دون مبالغة.",
        "tags": ["سيارات", "تقنية", "أداء", "تصميم", "مراجعة"],
        "short_titles": [
            "لماذا يلفت تصميم هذه السيارة الانتباه؟",
            "ما الذي يميز أداء السيارة في الاستخدام اليومي؟",
            "التقنية التي تجعل تجربة القيادة أكثر وضوحاً",
            "هل تجمع السيارة بين الأداء والتصميم بشكل متوازن؟",
        ],
        "narration": " ".join(scene["narration"] for scene in scenes),
        "scenes": scenes,
    }


def test_deterministic_repair_normalizes_timing_and_removes_unsupported_callouts():
    data = {
        "title": "السيارة الحديثة بالتفصيل: التصميم والتقنية والأداء",
        "description": "تحليل عربي منظم يشرح التصميم والتقنيات والأداء وتجربة الاستخدام عبر مشاهد مترابطة ومعلومات واضحة دون مبالغة.",
        "tags": ["سيارات", "تقنية", "أداء", "تصميم", "مراجعة"],
        "scenes": [_scene(i) for i in range(1, 26)],
    }
    repaired = _deterministic_structure_repair(data)
    assert all(scene["duration"] == 18.0 for scene in repaired["scenes"])
    assert all("999" not in scene["callouts"] for scene in repaired["scenes"])
    assert len(repaired["short_titles"]) == 4
    assert [sum(repaired["scenes"][i - 1]["duration"] for i in pair) for pair in ((1, 2), (7, 8), (13, 14), (19, 20))] == [36.0] * 4
    assert validate_story_data(repaired) is True


def test_repair_preserves_invalid_semantic_content_for_llm_repair():
    data = {"scenes": [_scene(i) for i in range(1, 25)]}
    repaired = _deterministic_structure_repair(data)
    assert len(repaired["scenes"]) == 24
    assert all(scene["duration"] == 50.0 for scene in repaired["scenes"])


def test_resilient_story_generation_recovers_from_non_list_scenes(monkeypatch):
    good = _strong_story_payload()
    calls = []

    def fake_ask(system, user, *, timeout=None, max_attempts=None):
        calls.append((system, user, timeout, max_attempts))
        if len(calls) == 1:
            return {"title": good["title"], "description": good["description"], "tags": good["tags"], "short_titles": good["short_titles"], "scenes": {"1": {"narration": "not a valid scene list"}}}
        return good

    monkeypatch.setattr("app.pipeline.ask_odysseus", fake_ask)
    story = generate_story_resilient("موضوع سيارة")

    assert len(story.scenes) == 25
    assert calls[0][2] >= 60
    assert any("top-level scenes array" in system for system, *_ in calls[1:])


def test_resilient_story_generation_retries_repair_after_timeout(monkeypatch):
    good = _strong_story_payload()
    calls = []

    def fake_ask(system, user, *, timeout=None, max_attempts=None):
        calls.append((system, user, timeout, max_attempts))
        if len(calls) == 1:
            return {"scenes": "broken"}
        if len(calls) == 2:
            raise RuntimeError("network timeout")
        return good

    monkeypatch.setattr("app.pipeline.ask_odysseus", fake_ask)
    story = generate_story_resilient("موضوع سيارة")

    assert len(story.scenes) == 25
    assert calls[1][2] >= 60
    assert calls[1][3] is None


def test_resilient_story_payload_is_bounded(monkeypatch):
    good = _strong_story_payload()
    captured = []

    def fake_ask(system, user, *, timeout=None, max_attempts=None):
        captured.append(user)
        if len(captured) == 1:
            return {**good, "scenes": []}
        return good

    monkeypatch.setattr("app.pipeline.ask_odysseus", fake_ask)
    generate_story_resilient("موضوع سيارة")
    assert all(len(payload) < 30000 for payload in captured)
    assert all("Return JSON only" not in payload for payload in captured)
