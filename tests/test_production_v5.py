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
