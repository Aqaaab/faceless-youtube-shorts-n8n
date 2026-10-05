from __future__ import annotations

import json
from pathlib import Path

from app.checkpoint import begin, load, stage_done, mark
from app.core import Scene, Story
from app.short_selector import MIN_CANDIDATES, build_candidates, select_best


def fixture_story(duration: float = 17.0) -> Story:
    scenes = []
    families = [
        "أداء التسارع والقوة",
        "تصميم المقصورة والشاشة",
        "تقنية الحساسات والبرمجيات",
        "أنظمة الأمان والفرامل",
        "الشحن السريع وإدارة الحرارة",
        "البطارية والمدى والكفاءة",
        "الديناميكا الهوائية وخطوط الهيكل",
        "القيمة والسعر والتجهيزات",
    ]
    for sid in range(1, 26):
        kind = families[(sid - 1) % len(families)]
        scenes.append(
            Scene(
                sid,
                f"هذه فقرة عربية عن {kind} مع معلومة واضحة للمشهد {sid}.",
                f"لقطة سيارة واقعية مع {kind} وتفصيل هندسي واضح للمشهد {sid}",
                "hero",
                [kind],
                duration,
            )
        )
    return Story(
        "سيارة تجريبية",
        "سيارة تجريبية: التصميم والتقنية والأداء",
        "تحليل منظم للتصميم والتقنية والأداء.",
        ["سيارات", "تقنية", "أداء", "تصميم", "مراجعة"],
        ["عنوان قصير أول", "عنوان قصير ثان", "عنوان قصير ثالث", "عنوان قصير رابع"],
        " ".join(s.narration for s in scenes),
        scenes,
    )


def test_short_candidate_pool_is_large_and_bounded(tmp_path):
    story = fixture_story()
    candidates = build_candidates(story, tmp_path)
    assert len(candidates) >= MIN_CANDIDATES
    assert all(28.0 <= c.duration <= 59.0 for c in candidates)
    assert all(c.end_scene > c.start_scene for c in candidates)


def test_short_selector_returns_four_disjoint_candidates(tmp_path):
    story = fixture_story()
    candidates = build_candidates(story, tmp_path)
    selected = select_best(candidates, {})
    assert len(selected) == 4
    ids = [sid for item in selected for sid in item.scene_ids]
    assert len(ids) == len(set(ids))


def test_checkpoint_skips_only_when_artifacts_exist(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    state = begin(work, "موضوع", "premium_coupe")
    artifact = work / "artifact.txt"
    mark(state, work, "render", "done", [artifact])
    assert not stage_done(load(work), "render", [artifact])
    artifact.write_text("ok", encoding="utf-8")
    assert stage_done(load(work), "render", [artifact])
    assert load(work)["stages"]["render"]["status"] == "done"


def test_profile_config_contains_three_local_variants():
    data = json.loads(Path("config/automotive_profiles.json").read_text(encoding="utf-8"))
    assert set(data["profiles"]) >= {"premium_coupe", "graphite_executive", "pearl_sport"}


def test_pipeline_contains_resume_and_candidate_stages():
    text = Path("app/pipeline.py").read_text(encoding="utf-8")
    for token in ("short_selection", "long_render", "short_render", "final_qa", "checkpoint_begin"):
        assert token in text


def test_short_selection_validator_rejects_overlap():
    from app.validator import validate_short_selection
    manifest = {
        "pool_size": 35,
        "selected": [
            {"duration": 32, "scene_ids": [1, 2], "start_time": 0, "end_time": 32, "title": "لماذا يهم تصميم السيارة في هذه الفئة؟"},
            {"duration": 34, "scene_ids": [2, 3], "start_time": 34, "end_time": 68, "title": "ما الذي يميز أداء السيارة في الاستخدام اليومي؟"},
            {"duration": 31, "scene_ids": [8, 9], "start_time": 100, "end_time": 131, "title": "التقنية التي تغيّر تجربة القيادة بشكل واضح؟"},
            {"duration": 33, "scene_ids": [14, 15], "start_time": 150, "end_time": 183, "title": "هل يجتمع الأداء والتصميم في حزمة واحدة؟"},
        ],
    }
    import pytest
    with pytest.raises(AssertionError, match="overlap"):
        validate_short_selection(manifest)


def test_story_engine_does_not_require_fixed_short_pairs():
    core = Path("app/core.py").read_text(encoding="utf-8")
    pipeline = Path("app/pipeline.py").read_text(encoding="utf-8")
    for source in (core, pipeline):
        assert "source pairs (1,2),(7,8),(13,14),(19,20)" not in source
        assert "fixed source scene pairs" not in source


def test_ground_and_high_reveal_have_distinct_camera_geometry():
    source = Path("scripts/automotive_shots.py").read_text(encoding="utf-8")
    assert '"high_reveal":((0.0,-1.0,11.5),(0.0,0.0,0.45),52)' in source
    assert '"ground_wide":((-13.0,-15.0,0.42),(-2.2,0.0,0.78),34)' in source
    assert '"high_reveal":((9.5,-10.0,6.8),(0,0,0.9),50)' not in source
    assert '"ground_wide":((15.0,-20.0,0.55),(0.0,0,0.85),38)' not in source


def test_motion_cache_and_smoke_use_explicit_fps_contracts():
    blender = Path("app/blender_automotive.py").read_text(encoding="utf-8")
    smoke = Path("scripts/ci_artifact_gate.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "motion_fps" in blender
    assert "motion_fps," in blender
    assert 'AUTOMOTIVE_MOTION_FPS": str(motion_fps' in blender
    assert "smoke_duration = 0.25 if _motion_enabled() else 1.2" in smoke
    assert 'AUTOMOTIVE_MOTION_FPS: "8"' in workflow
