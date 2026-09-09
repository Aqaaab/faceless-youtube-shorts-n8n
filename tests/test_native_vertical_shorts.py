from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "renderer.py"


def test_shorts_use_native_vertical_scene_composition() -> None:
    text = RENDERER.read_text(encoding="utf-8")
    assert '"shorts_pipeline": "native_vertical_scene_composition"' in text
    assert "selected_scenes = scenes[start - 1:end]" in text
    assert "_render_vertical_scene(record, scene, duration, scene_index, work)" in text
    assert "vertical=True" in text
    assert "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" in text


def test_shorts_do_not_crop_horizontal_master_segments() -> None:
    text = RENDERER.read_text(encoding="utf-8")
    assert 'source_short = work / f"short-{sid}-source.mp4"' in text
    assert "concat_segments([item[0] for item in selected], source_short, work)" not in text
    assert "Native vertical scenes already contain their Arabic captions" in text
