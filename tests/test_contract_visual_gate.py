from __future__ import annotations

from pathlib import Path

from app.visual_product_gate import CAR_PRIMARY_THRESHOLD, car_first_ratio

ROOT = Path(__file__).parents[1]


def test_CONTRACT_29_car_layer_attribute_present_in_all_scene_types(tmp_path):
    from app.core import Scene
    from app.story_visuals import render_scene_svg
    from app.vertical_visuals import vertical_scene_svg

    for sid, words in [(1, "تصميم السيارة"), (2, "بطارية السيارة"), (3, "أداء السيارة")]:
        scene = Scene(sid, words, words + " مع لقطة سيارة واضحة", "hero", ["معلومة واضحة"], 10.0)
        master = tmp_path / f"master_{sid}.svg"
        short = tmp_path / f"short_{sid}.svg"
        render_scene_svg(scene, "سيارة اختبار", master)
        vertical_scene_svg(scene, "سيارة اختبار", short)
        assert 'data-car-layer="primary"' in master.read_text(encoding="utf-8")
        assert 'data-car-layer="primary"' in short.read_text(encoding="utf-8")


def test_CONTRACT_30_car_first_mock_ratio_gate():
    two_primary = [
        '<svg data-car-layer="primary"></svg>',
        '<svg data-car-layer="primary"></svg>',
        '<svg></svg>',
    ]
    assert round(car_first_ratio(two_primary), 2) == 0.67
    assert car_first_ratio(two_primary) < CAR_PRIMARY_THRESHOLD


def test_CONTRACT_31_all_primary_mock_ratio_passes():
    all_primary = [
        '<svg data-car-layer="primary"></svg>',
        '<svg data-car-layer="primary"></svg>',
        '<svg data-car-layer="primary"></svg>',
    ]
    assert round(car_first_ratio(all_primary), 2) == 1.00
    assert car_first_ratio(all_primary) >= CAR_PRIMARY_THRESHOLD
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "artifact_gate" in workflow
