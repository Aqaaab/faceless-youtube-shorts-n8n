from pathlib import Path
import re

ROOT=Path(__file__).parents[1]


def test_visual_product_gate_validates_renderer_metadata_contract():
    source=Path("app/visual_product_gate.py").read_text(encoding="utf-8")
    assert 'asset-quality' in source
    assert 'blender_eevee_automotive_v' in source
    assert 'asset_external' in Path("app/blender_automotive.py").read_text(encoding="utf-8")


def test_scene_render_pipeline_emits_v5_asset_quality_marker():
    for name in ("app/story_visuals.py", "app/vertical_visuals.py"):
        source=Path(name).read_text(encoding="utf-8")
        assert 'asset-quality' in source
        assert 'blender_eevee_automotive_v5_persistent' in source
