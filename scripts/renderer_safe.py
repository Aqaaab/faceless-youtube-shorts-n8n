from __future__ import annotations

import re
import unicodedata
import textwrap

import renderer


def _clean_arabic(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or ""))
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _wrap_safe(text: str) -> str:
    # Keep subtitles inside a narrow center-safe zone so the later 16:9 -> 9:16
    # crop cannot cut text off the left/right edges.
    lines = textwrap.wrap(
        _clean_arabic(text),
        width=28,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [""]
    return "\\N".join(lines[:3])


def make_ass(sc: dict, duration_seconds: float, dst) -> None:
    ar = renderer.ass_escape(_wrap_safe(sc.get("text_ar", "")))
    content = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Arabic,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,3,1,2,600,600,90,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    content += f"Dialogue: 0,0:00:00.00,{renderer.ass_time(duration_seconds)},Arabic,,0,0,0,,{ar}\n"
    dst.write_text(content, encoding="utf-8")


renderer.make_ass = make_ass


if __name__ == "__main__":
    renderer.main()
