from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
MAX_TITLE_CHARS = 68
CAR_HASHTAGS = "#Cars #Automotive #CarTechnology #CarFacts"
REQUIRED_SHORTS = 4
MIN_SHORT_DURATION = 28.0
MAX_SHORT_DURATION = 59.0
SHORT_WINDOWS = [(1, 2), (7, 8), (13, 14), (19, 20)]
ROLE_DEFAULTS = ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"]


def _safe_text(value: object, limit: int = 100) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" .,:;!?-")
    return text


def _title_fit(text: str, limit: int = MAX_TITLE_CHARS) -> str:
    text = _safe_text(text, 200).strip()
    if len(text) <= limit:
        return text
    out = ""
    for word in text.split():
        candidate = word if not out else f"{out} {word}"
        if len(candidate) > limit:
            break
        out = candidate
    return out.rstrip(" .,:;!?-") or _safe_text(text, limit)


def _short_title(story_title: str, scenes: list[dict], index: int) -> str:
    for scene in scenes:
        text = _safe_text(scene.get("short_title") or scene.get("text_en", ""), 180)
        parts = re.split(r"(?<=[.!?])\s+", text)
        for part in parts:
            candidate = _title_fit(part.rstrip(".!?"))
            if len(candidate) >= 18:
                return candidate
    fallback = _title_fit(story_title) or f"Cars Explained: Part {index}"
    return fallback


def _short_description(story: dict, title: str) -> str:
    base = _safe_text(story.get("description", ""), 3600)
    base = re.sub(r"(?:^|\s)#[\w-]+", "", base)
    return _safe_text(f"{title}.\n\n{base}\n\n{CAR_HASHTAGS}", 5000)


def _candidate_score(scene: dict, index: int) -> float:
    raw = scene.get("short_candidate_score", scene.get("hook_score", 0))
    try:
        score = float(raw)
    except (TypeError, ValueError):
        score = 0.0
    beat = str(scene.get("beat", "")).casefold()
    role = str(scene.get("short_role", "")).casefold()
    if beat == "hook":
        score += 18
    if role:
        score += 5
    if index in {1, 7, 13, 19}:
        score += 10
    return score


def _is_automotive(scene: dict) -> bool:
    text = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject", "pexels_query", "technical_component", "technical_flow"))
    return bool(re.search(r"\b(car|cars|automotive|automobile|vehicle|engine|turbo|brake|tire|wheel|suspension|differential|cooling|radiator|battery|electric|hybrid|drivetrain|transmission|horsepower|torque)\b", text, re.I))


def _validate_window(scenes: list[dict], start: int, end: int) -> None:
    window = scenes[start - 1:end]
    if not window or not all(isinstance(scene, dict) and _is_automotive(scene) for scene in window):
        raise ValueError(f"Short window {start}-{end} is not fully automotive")
    if len(window) < 2:
        raise ValueError("Each Short must contain at least two master scenes to avoid frozen-frame padding")


def build_shorts(story: dict) -> list[dict]:
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("automotive shorts require exactly 25 story scenes")

    shorts: list[dict] = []
    seen_titles: set[str] = set()
    for index, (start, end) in enumerate(SHORT_WINDOWS, 1):
        _validate_window(scenes, start, end)
        selected = scenes[start - 1:end]
        title = _short_title(str(story.get("title", "")), selected, index)
        if title.casefold() in seen_titles:
            title = _title_fit(f"{title} {index}")
        seen_titles.add(title.casefold())
        # The role belongs to the published Short contract, not to arbitrary
        # model metadata. This prevents a free-form LLM label from breaking the
        # final quality gate.
        role = ROLE_DEFAULTS[index - 1]
        shorts.append({
            "id": index,
            "scene_start": start,
            "scene_end": end,
            "title": title,
            "description": _short_description(story, title),
            "role": role,
            "score": round(max(_candidate_score(selected[0], start), _candidate_score(selected[1], end)), 2),
            "scenes": selected,
            "source_from_long_video": True,
            "selection_reason": "fixed hook-to-explanation two-scene window; canonical role; no artificial duration padding",
        })
    return shorts


def main() -> list[dict]:
    source = RUN / "long_story.json"
    if not source.is_file():
        raise FileNotFoundError(f"missing story: {source}")
    story = json.loads(source.read_text(encoding="utf-8"))
    shorts = build_shorts(story)
    out = RUN / "shorts_plan.json"
    out.write_text(json.dumps({
        "version": 7,
        "niche": "cars",
        "strategy": "derive four unique Shorts from fixed two-scene windows in the 25-scene master",
        "target_duration_seconds": [MIN_SHORT_DURATION, MAX_SHORT_DURATION],
        "windows": SHORT_WINDOWS,
        "roles": ROLE_DEFAULTS,
        "shorts": shorts,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SHORTS_PLAN=PASS niche=cars count=4 source=long_video windows=2scenes artificial_padding=false canonical_roles=true")
    return shorts


if __name__ == "__main__":
    main()
