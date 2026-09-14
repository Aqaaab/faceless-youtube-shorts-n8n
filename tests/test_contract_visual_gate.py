from __future__ import annotations
from pathlib import Path
from app.visual_product_gate import CAR_PRIMARY_THRESHOLD, car_first_ratio
ROOT=Path(__file__).parents[1]

def test_CONTRACT_29_car_layer_attribute_present_in_all_scene_types(tmp_path):
    from app.core import Scene
    from app.story_visuals import render_scene_svg
    from app.vertical_visuals import vertical_scene_svg
    for sid,words in [(1,"تصميم السيارة"),(2,"بطارية السيارة"),(3,"أداء السيارة")]:
        scene=Scene(sid,words,words+" مع لقطة سيارة واضحة","hero",["معلومة واضحة"],10.0)
        master=tmp_path/f"master_{sid}.svg"; short=tmp_path/f"short_{sid}.svg"
        render_scene_svg(scene,"سيارة اختبار",master); vertical_scene_svg(scene,"سيارة اختبار",short)
        assert 'data-car-layer="primary"' in master.read_text(encoding="utf-8")
        assert 'data-car-layer="primary"' in short.read_text(encoding="utf-8")

def test_CONTRACT_30_artifact_gate_produces_non_empty_qa_report():
    workflow=(ROOT/".github"/"workflows"/"ci.yml").read_text(encoding="utf-8")
    assert "- name: artifact_gate" in workflow
    assert "test -s work/qa_report.json" in workflow
    assert "qa_report.json" in workflow

def test_CONTRACT_31_car_first_ratio_test_render_threshold():
    workflow=(ROOT/".github"/"workflows"/"ci.yml").read_text(encoding="utf-8")
    two_primary=['<svg data-car-layer="primary"></svg>','<svg data-car-layer="primary"></svg>','<svg></svg>']
    all_primary=['<svg data-car-layer="primary"></svg>']*3
    assert round(car_first_ratio(two_primary),2)==0.67
    assert car_first_ratio(two_primary)<CAR_PRIMARY_THRESHOLD
    assert round(car_first_ratio(all_primary),2)==1.00
    assert car_first_ratio(all_primary)>=0.70
    assert "assert report['car_first_ratio'] >= 0.70" in workflow
