from pathlib import Path
from PIL import Image

from app.mp4_visual_gate import _portrait_frame_ok


def test_portrait_frame_rejects_black_bottom_padding(tmp_path: Path):
    image = Image.new("RGB", (1080, 1920), (18, 22, 27))
    draw = image.load()
    for y in range(0, 1250):
        for x in range(80, 1000):
            draw[x, y] = (150, 155, 160)
    path = tmp_path / "bad.png"
    image.save(path)
    ok, reason = _portrait_frame_ok(path)
    assert not ok
    assert "bottom" in reason.lower()


def test_portrait_frame_accepts_full_frame_signal(tmp_path: Path):
    image = Image.new("RGB", (1080, 1920), (24, 28, 33))
    draw = image.load()
    for y in range(0, 1920, 8):
        for x in range(0, 1080, 8):
            v = (x * 13 + y * 7) % 70
            draw[x, y] = (70 + v, 75 + v, 80 + v)
    path = tmp_path / "good.png"
    image.save(path)
    ok, _ = _portrait_frame_ok(path)
    assert ok
