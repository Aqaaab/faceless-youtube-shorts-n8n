from pathlib import Path

import pytest

from app.render import _subtitle_cues
from app.visual_product_gate import _srt_records


def test_short_subtitle_cues_are_compact_and_two_lines_max():
    text = "السيارة الجديدة تجمع بين تصميم عملي وتقنيات حديثة وأداء متوازن يمنح السائق تجربة واضحة ومتماسكة في الاستخدام اليومي"
    cues = _subtitle_cues(text, 0.0, 18.0, 30, 2)
    assert cues
    for start, end, cue in cues:
        assert end > start
        lines = cue.splitlines()
        assert 1 <= len(lines) <= 2
        assert all(len(line) <= 30 for line in lines)


def test_subtitle_records_reject_tofu(tmp_path: Path):
    srt = tmp_path / "bad.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nسيارة □ جديدة\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="corrupted/tofu"):
        _srt_records(srt)


def test_subtitle_records_reject_overlong_lines(tmp_path: Path):
    srt = tmp_path / "bad.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n" + "ا" * 43 + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="exceeds 42"):
        _srt_records(srt)


def test_visual_gate_defines_hard_short_safe_area():
    from app.visual_product_gate import SHORT_SAFE
    assert SHORT_SAFE == {"left": 72, "right": 72, "top": 120, "bottom": 180}
