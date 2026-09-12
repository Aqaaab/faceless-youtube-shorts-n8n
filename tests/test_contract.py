from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def strong_story() -> dict:
    base_narration = "السيارة الجديدة تجمع بين تصميم عملي وتقنيات حديثة وأداء متوازن يمنح السائق تجربة واضحة ومتماسكة في الاستخدام اليومي، مع تركيز على التفاصيل الهندسية التي تميز هذا الطراز ضمن فئته وتساعد على فهم نقاط القوة الأساسية دون مبالغة أو ادعاءات غير مثبتة"
    scenes = []
    layouts = ["hero", "technical", "spec", "comparison", "diagram", "timeline"]
    for sid in range(1, 26):
        narration = base_narration + f" في المشهد رقم {sid}."
        callouts = ["تصميم عملي", "تقنيات حديثة"] if sid % 2 else ["أداء متوازن", "تجربة واضحة"]
        if sid == 1:
            narration += " قوة 320 حصان."
            callouts = ["320 حصان", "أداء متوازن"]
        scenes.append({
            "id": sid,
            "narration": narration,
            "visual_intent": f"لقطة سيارة للمشهد {sid} مع تركيب بصري وتفصيل واضح للمعلومة الأساسية",
            "layout": layouts[(sid - 1) % len(layouts)],
            "callouts": callouts,
            "duration": 17.0,
        })
    return {
        "title": "السيارة الجديدة بالتفصيل: التصميم والتقنية والأداء",
        "description": "تحليل عربي منظم للسيارة الجديدة يشرح التصميم والتقنيات والأداء وتجربة الاستخدام عبر 25 مشهداً مترابطاً مع معلومات وصفية واضحة وعناوين مستقلة للمقاطع القصيرة.",
        "tags": ["سيارات", "مراجعة", "تقنية", "أداء", "تصميم"],
        "short_titles": [
            "لماذا يلفت تصميم هذه السيارة الانتباه؟",
            "ما الذي يميز أداء السيارة في الاستخدام اليومي؟",
            "التقنية التي تجعل تجربة القيادة أكثر وضوحاً",
            "هل تجمع السيارة بين الأداء والتصميم بشكل متوازن؟",
        ],
        "narration": " ".join(scene["narration"] for scene in scenes),
        "scenes": scenes,
    }


def test_source_has_no_removed_stock_references():
    p1 = "pex" + "els"
    p2 = "render_" + "manifest.json"
    p3 = "generated_" + "still_first"
    p4 = "stock-" + "video"
    forbidden = [p1, p2, p3, p4]
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in {".py", ".yml", ".yaml", ".md", ".json", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in forbidden:
            if path == ROOT / "tests" / "test_contract.py":
                continue
            assert token not in text, f"forbidden legacy reference in {path}: {token}"


def test_extract_json_accepts_exact_fenced_and_embedded_objects():
    from app.core import _extract_json

    payload = {"ok": True, "scenes": []}
    raw = json.dumps(payload)
    assert _extract_json(raw) == payload
    assert _extract_json(f"```json\n{raw}\n```") == payload
    assert _extract_json(f"Here is the object:\n{raw}\nDone.") == payload


def test_extract_json_rejects_non_object():
    from app.core import _extract_json

    with pytest.raises(RuntimeError, match="invalid story JSON"):
        _extract_json("not json")


def test_story_shape_normalizes_nested_and_common_scene_aliases():
    from app.core import _story_shape

    payload = {
        "story": {
            "title": "عنوان القصة",
            "scene": [
                {"narration": "نص عربي", "visual": "لقطة سيارة", "seconds": 12, "annotations": ["نص"]}
            ],
        }
    }
    normalized = _story_shape(payload)
    assert "scenes" in normalized
    assert normalized["scenes"][0]["id"] == 1
    assert normalized["scenes"][0]["visual_intent"] == "لقطة سيارة"
    assert normalized["scenes"][0]["duration"] == 12
    assert normalized["scenes"][0]["callouts"] == ["نص"]


def test_story_shape_converts_numeric_scene_mapping():
    from app.core import _story_shape

    normalized = _story_shape({"scenes": {"1": {"narration": "أ"}, "2": {"narration": "ب"}}})
    assert [scene["id"] for scene in normalized["scenes"]] == [1, 2]


def test_odysseus_request_retries_invalid_model_json(monkeypatch):
    from app import core

    class Response:
        def __init__(self, content):
            self.status_code = 200
            self.headers = {}
            self._content = content
            self.ok = True
            self.text = json.dumps(content)

        def json(self):
            return {"response": self._content}

    responses = iter([Response("not-json"), Response(json.dumps({"ok": True}))])
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setenv("ODYSSEUS_GATEWAY_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("ODYSSEUS_GATEWAY_API_KEY", "test")
    monkeypatch.setattr(core.requests, "post", post)
    assert core.ask_odysseus("system", "user") == {"ok": True}
    assert len(calls) == 2
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_odysseus_429_retries_then_fails_without_provider_fallback(monkeypatch):
    from app import core

    class Response:
        status_code = 429
        headers = {"Retry-After": "1"}
        ok = False
        text = '{"error":"quota exceeded"}'

        def json(self):
            return {"error": "quota exceeded"}

    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setenv("ODYSSEUS_GATEWAY_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("ODYSSEUS_GATEWAY_API_KEY", "test")
    monkeypatch.setenv("ODYSSEUS_MAX_ATTEMPTS", "2")
    monkeypatch.setattr(core.requests, "post", post)
    monkeypatch.setattr(core.time, "sleep", lambda _: None)

    with pytest.raises(core.OdysseusRateLimitError, match="rate limit exhausted"):
        core.ask_odysseus("system", "user")
    assert len(calls) == 2
    assert all("openrouter" not in str(call).lower() for call in calls)


def test_story_validator_accepts_strong_story(tmp_path):
    from app.validator import validate_story

    path = tmp_path / "story.json"
    path.write_text(json.dumps(strong_story(), ensure_ascii=False), encoding="utf-8")
    assert validate_story(path) is True


def test_story_validator_rejects_wrong_numeric_digit_script(tmp_path):
    from app.validator import validate_story

    data = strong_story()
    data["scenes"][0]["callouts"] = ["320 حصان"]
    data["scenes"][0]["narration"] = data["scenes"][0]["narration"].replace("320", "٣٢٠")
    path = tmp_path / "story.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AssertionError, match="unsupported numeric token"):
        validate_story(path)


def test_story_validator_accepts_exact_numeric_form(tmp_path):
    from app.validator import validate_story

    data = strong_story()
    path = tmp_path / "story.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert validate_story(path) is True


def test_tts_synchronization_uses_real_duration_without_short_floor():
    from app.core import Scene
    from app.tts import DURATION_PADDING, synchronize_scene_durations

    story = type("S", (), {})()
    story.scenes = [Scene(1, "نص عربي كاف ومتماسك للاختبار مع معلومات واضحة", "لقطة سيارة مع حركة وتفصيل بصري للمعلومة", "hero", [], 30)]
    synchronize_scene_durations(story, {1: 10.0})
    assert story.scenes[0].duration == pytest.approx(10.0 + DURATION_PADDING)


def test_tts_timing_rejects_overrun():
    from app.tts import validate_tts_timing

    story = type("S", (), {})()
    story.scenes = [type("C", (), {"id": 1, "duration": 10.0, "narration": "هذا نص عربي مناسب للاختبار"})()]
    with pytest.raises(RuntimeError, match="TTS TIMING FAILED"):
        validate_tts_timing(story, {1: 11.0})


def test_upload_title_limit_and_metadata_cleaning():
    from app.upload import _clean_text, _final_title

    marker = " [ACE:123456789abc]"
    title = _final_title("x" * 100, marker)
    assert len(title) <= 100
    assert title.endswith(marker)
    cleaned = _clean_text("عنوان\x00\x07\nوصف", 5000)
    assert "\x00" not in cleaned and "\x07" not in cleaned


def test_upload_gate_blocks_missing_or_failed_report(tmp_path):
    from app.upload import _require_final_qa

    with pytest.raises(RuntimeError, match="UPLOAD BLOCKED"):
        _require_final_qa(tmp_path)


def test_render_contract_contains_required_delivery_features():
    text = (ROOT / "app" / "render.py").read_text(encoding="utf-8")
    for token in ["Noto Sans Arabic", "loudnorm=I=-16:TP=-1.5:LRA=11", "1920x1080", "1080x1920", "zoompan"]:
        assert token in text


def test_production_gate_requires_all_outputs_before_publish():
    text = (ROOT / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "default: false" in text
    assert "Final artifact product gate" in text
    assert text.index("Final artifact product gate") < text.index("YouTube upload")
    assert "for i in 1 2 3 4" in text
    assert "weighted_score_10" in text


def test_artifact_gate_imports_and_exposes_qa():
    from app.artifact_gate import qa
    from app.qa import qa as wrapped

    assert callable(qa)
    assert wrapped is qa


def test_vertical_visual_engine_has_all_semantic_modes():
    text = (ROOT / "app" / "vertical_visuals.py").read_text(encoding="utf-8")
    for token in ['"performance"', '"design"', '"interior"', '"technology"', '"efficiency"', '"safety"', '"price"']:
        assert token in text
