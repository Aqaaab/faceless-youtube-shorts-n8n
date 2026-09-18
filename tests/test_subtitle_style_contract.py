from pathlib import Path


def test_arabic_subtitles_use_outline_not_opaque_boxes():
    source=Path("app/render.py").read_text(encoding="utf-8")
    assert "BorderStyle=1" in source
    assert "BorderStyle=3" not in source
    assert source.count("Noto Sans Arabic") >= 2
