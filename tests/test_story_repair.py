from __future__ import annotations

from app.core import _deterministic_structure_repair
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
