from __future__ import annotations

import json, os, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
STARTS = (0, 6, 12, 18)
BLOCK_SIZE = 6


def _safe_text(value: object, limit: int = 100) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = re.sub(r"\s+", " ", text).strip()
    units = len(text.encode("utf-16-le")) // 2
    if units > limit:
        raw = text.encode("utf-16-le")[:limit * 2]
        text = raw.decode("utf-16-le", errors="ignore").rstrip()
    return text


def _hook_sentence(scene: dict) -> str:
    text = _safe_text(scene.get("text_en", ""), 90)
    text = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(text) < 8:
        text = _safe_text(scene.get("visual_subject", "The hidden story"), 90)
    return text.rstrip(".!?")


def _short_title(story_title: str, scene: dict, index: int) -> str:
    hook = _hook_sentence(scene)
    candidates = [hook, story_title]
    for value in candidates:
        value = _safe_text(value, 90)
        if value and value.lower() not in {"story", "untitled", "untitled story"}:
            return value
    return f"The Hidden Story That History Almost Forgot #{index}"


def _short_description(story: dict, title: str, index: int) -> str:
    base = _safe_text(story.get("description", ""), 3800)
    tags = "#History #Mystery #HistoryFacts"
    return _safe_text(f"{title}.\n\n{base}\n\n{tags}", 5000)


def build_shorts(story: dict) -> list[dict]:
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("shorts require exactly 25 story scenes")

    shorts = []
    for i, start in enumerate(STARTS, 1):
        chunk = scenes[start:start + BLOCK_SIZE]
        if len(chunk) != BLOCK_SIZE:
            raise ValueError(f"short {i} must contain exactly {BLOCK_SIZE} scenes")
        if str(chunk[0].get("beat", "")).lower() != "hook":
            # The story contract asks for hook openings at scenes 1, 7, 13 and 19.
            raise ValueError(f"short {i} opening scene is not a hook")
        title = _short_title(str(story.get("title", "")), chunk[0], i)
        shorts.append({
            "id": i,
            "scene_start": start + 1,
            "scene_end": start + len(chunk),
            "title": title,
            "description": _short_description(story, title, i),
            "scenes": chunk,
        })
    return shorts


def main() -> list[dict]:
    source = RUN / "long_story.json"
    if not source.is_file():
        raise FileNotFoundError(f"missing story: {source}")
    story = json.loads(source.read_text(encoding="utf-8"))
    shorts = build_shorts(story)
    out = RUN / "shorts_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": 2, "shorts": shorts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SHORTS_PLAN=PASS count=4 standalone=1")
    return shorts


if __name__ == "__main__":
    main()
