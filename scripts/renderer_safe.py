from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import renderer


# Hardening layer: keep renderer.py stable while enforcing safer caption geometry
# and landscape-first source selection. The previous implementation preferred
# portrait Pexels clips even for the 16:9 master, which made crops look unrelated.
SAFE_LONG_MARGIN_LR = 300
SAFE_LONG_MARGIN_V = 170
SAFE_SHORT_MARGIN_LR = 260
SAFE_SHORT_MARGIN_V = 330
SAFE_SHORT_MAX_CHARS = 18


def _wrap_arabic(text: str, max_chars: int = SAFE_SHORT_MAX_CHARS, max_lines: int = 2) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    if not normalized:
        return ""
    words = normalized.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return "\\N".join(lines)
    # Rebalance two lines instead of allowing a third line to drift toward the
    # phone edges. Long individual words are kept intact rather than split.
    mid = max(1, min(len(words) - 1, len(words) // 2))
    first, second = words[:mid], words[mid:]
    while len(" ".join(first)) > max_chars and len(first) > 1:
        second.insert(0, first.pop())
    while len(" ".join(second)) > max_chars and len(second) > 1:
        first.append(second.pop(0))
    return "\\N".join((" ".join(first), " ".join(second)))


def _ass_escape(text: str) -> str:
    return renderer.ass_escape(text)


def _ass_time(seconds: float) -> str:
    return renderer.ass_time(seconds)


def _make_ass(sc: dict, duration_seconds: float, dst: Path) -> None:
    ar = _ass_escape(_wrap_arabic(sc.get("text_ar", ""), max_chars=24, max_lines=2))
    content = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Arabic,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,4,1,2,300,300,170,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    content += f"Dialogue: 0,0:00:00.00,{_ass_time(duration_seconds)},Arabic,,300,300,170,,{ar}\n"
    dst.write_text(content, encoding="utf-8")


def _make_vertical_ass(short: dict, durations: list[float], dst: Path) -> None:
    scenes = short.get("scenes", [])
    if len(scenes) != len(durations):
        raise ValueError(f"Short {short.get('id')} caption timing mismatch")
    content = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: ArabicVertical,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,4,1,2,260,260,330,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    cursor = 0.0
    for scene, dur in zip(scenes, durations):
        end = cursor + max(0.05, float(dur))
        text = _ass_escape(_wrap_arabic(scene.get("text_ar", ""), SAFE_SHORT_MAX_CHARS, 2))
        content += f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(end)},ArabicVertical,,260,260,330,,{text}\n"
        cursor = end
    dst.write_text(content, encoding="utf-8")


def _pexels_landscape(query: str) -> str:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is required for real rendering")
    q = urllib.parse.quote(str(query).strip())
    url = f"https://api.pexels.com/videos/search?query={q}&per_page=8&orientation=landscape"
    last: Exception | None = None
    for attempt in range(max(1, int(os.getenv("MEDIA_RETRIES", "3")))):
        try:
            req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "faceless-youtube-shorts-n8n/3.0"})
            with urllib.request.urlopen(req, timeout=max(10, int(os.getenv("PEXELS_TIMEOUT", "45")))) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            candidates = []
            for video in data.get("videos", []):
                for item in video.get("video_files", []):
                    link = item.get("link")
                    width = int(item.get("width") or 0)
                    height = int(item.get("height") or 0)
                    if not link or width <= 0 or height <= 0:
                        continue
                    if width < height:
                        continue
                    # Prefer genuine landscape and high resolution, but don't
                    # let a giant irrelevant file beat a useful landscape clip.
                    ratio = width / max(1, height)
                    cinematic = 1 if 1.55 <= ratio <= 2.0 else 0
                    candidates.append((cinematic, width * height, link))
            if candidates:
                return max(candidates, key=lambda item: (item[0], item[1]))[2]
            raise RuntimeError(f"No landscape Pexels video found for query: {query}")
        except urllib.error.HTTPError as exc:
            last = RuntimeError(f"Pexels HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}")
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            last = exc
        if attempt + 1 < max(1, int(os.getenv("MEDIA_RETRIES", "3"))):
            time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"Pexels landscape lookup failed for query: {query}") from last


def _write_manifest_hardening(run: Path) -> None:
    path = run / "render_manifest.json"
    if not path.is_file():
        return
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    manifest["caption_hardening"] = "renderer_safe_v3"
    manifest["long_safe_zone"] = {"margin_left": SAFE_LONG_MARGIN_LR, "margin_right": SAFE_LONG_MARGIN_LR, "margin_bottom": SAFE_LONG_MARGIN_V, "max_chars_per_line": 24, "max_lines": 2}
    manifest["short_safe_zone"] = {"margin_left": SAFE_SHORT_MARGIN_LR, "margin_right": SAFE_SHORT_MARGIN_LR, "margin_bottom": SAFE_SHORT_MARGIN_V, "max_chars_per_line": SAFE_SHORT_MAX_CHARS, "max_lines": 2}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    renderer.wrap_arabic = _wrap_arabic
    renderer.make_ass = _make_ass
    renderer.make_vertical_ass = _make_vertical_ass
    renderer.pexels = _pexels_landscape
    result = renderer.main()
    _write_manifest_hardening(Path(os.getenv("RUN_DIR", str(renderer.RUN))))
    print("RENDER_HARDENING=PASS subtitles=extra-safe visual_sources=landscape-first")
    return result


if __name__ == "__main__":
    main()
