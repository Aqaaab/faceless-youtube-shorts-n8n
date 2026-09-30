from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageStat

PREFERRED_FONTS = (
    "Noto Sans Arabic",
    "Noto Naskh Arabic",
    "Amiri",
    "DejaVu Sans",
)
TEST_TEXT = "السيارة العربية التقنية ١٢٣ — اختبار اتصال الحروف"


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def _charset_values(font_file: str) -> set[int]:
    raw = _run(["fc-query", "--format=%{charset}", font_file])
    values: set[int] = set()
    for token in raw.split():
        if "-" in token:
            left, right = token.split("-", 1)
            try:
                values.update(range(int(left, 16), int(right, 16) + 1))
            except ValueError:
                continue
        else:
            try:
                values.add(int(token, 16))
            except ValueError:
                continue
    return values


def discover() -> dict:
    errors = []
    candidates = [f"{name}:lang=ar" for name in PREFERRED_FONTS]
    candidates.append(":lang=ar")
    for query in candidates:
        try:
            font_file = _run(["fc-match", "-f", "%{file}\\n", query])
            family = _run(["fc-match", "-f", "%{family[0]}\\n", query])
            if font_file and Path(font_file).is_file():
                return {"file": font_file, "family": family or Path(font_file).stem}
        except (subprocess.CalledProcessError, OSError) as exc:
            errors.append(str(exc))
    raise RuntimeError("Arabic font discovery failed: " + " | ".join(errors[-3:]))


def _required_codepoints(text: str) -> set[int]:
    return {ord(ch) for ch in text if 0x0600 <= ord(ch) <= 0x06FF}


def glyph_report(font: dict, text: str = TEST_TEXT) -> dict:
    supported = _charset_values(font["file"])
    required = _required_codepoints(text)
    missing = sorted(required - supported)
    return {
        "font_file": font["file"],
        "family": font["family"],
        "required_codepoints": [f"U+{value:04X}" for value in sorted(required)],
        "missing_codepoints": [f"U+{value:04X}" for value in missing],
        "glyphs_ok": not missing,
    }


def _render_smoke(font: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="ace-arabic-") as tmp:
        root = Path(tmp)
        srt = root / "probe.srt"
        out = root / "probe.png"
        srt.write_text(f"1\\n00:00:00,000 --> 00:00:01,500\\n{TEST_TEXT}\\n", encoding="utf-8")
        escaped = str(srt).replace("\\", "/").replace(":", "\\:")
        style = (
            f"FontName={font['family']},FontSize=30,Alignment=2,MarginV=42,"
            "Outline=2,Shadow=0,BorderStyle=1,Spacing=0,WrapStyle=2"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=960x240:r=2",
                "-vf",
                f"subtitles={escaped}:force_style='{style}'",
                "-frames:v",
                "1",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        with Image.open(out).convert("L") as im:
            crop = im.crop((20, 120, im.width - 20, im.height - 10))
            stat = ImageStat.Stat(crop)
            return {"rendered": True, "mean": round(float(stat.mean[0]), 3), "stddev": round(float(stat.stddev[0]), 3), "ink_present": float(stat.stddev[0]) > 3.0}


def ensure_ready(report_path: Path | None = None, strict: bool = True) -> dict:
    font = discover()
    result = glyph_report(font)
    if result["glyphs_ok"]:
        try:
            result["shaping_smoke"] = _render_smoke(font)
        except (OSError, subprocess.CalledProcessError) as exc:
            result["shaping_smoke"] = {"rendered": False, "error": str(exc)}
    else:
        result["shaping_smoke"] = {"rendered": False, "error": "missing glyphs"}
    result["passed"] = bool(result["glyphs_ok"] and result["shaping_smoke"].get("ink_present"))
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if strict and not result["passed"]:
        raise RuntimeError(f"ARABIC FONT GATE FAILED: {result}")
    return result
