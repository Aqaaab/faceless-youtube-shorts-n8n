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


def _safe_text(value: object, limit: int = 100) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" .,:;!?-")
    return text


def _hook_sentence(scene: dict) -> str:
    text = _safe_text(scene.get("text_en", ""), 180)
    parts = re.split(r"(?<=[.!?])\s+", text)
    for part in parts:
        candidate = part.strip().rstrip(".!?")
        if len(candidate) >= 18:
            return candidate
    return text.rstrip(".!?")


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


def _short_title(story_title: str, scene: dict, index: int) -> str:
    hook = _hook_sentence(scene)
    candidates = [hook, str(scene.get("short_title", "")), story_title, f"Cars Explained: Episode {index}"]
    for value in candidates:
        value = _title_fit(value)
        if value and value.lower() not in {"story", "untitled", "untitled story"}:
            return value
    raise ValueError(f"unable to build automotive short title {index}")


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
    if index <= 3:
        score += 2
    return score


def _is_automotive(scene: dict) -> bool:
    text = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject", "pexels_query", "technical_component", "technical_flow"))
    return bool(re.search(r"\b(car|cars|automotive|automobile|vehicle|engine|turbo|brake|tire|wheel|suspension|differential|cooling|radiator|battery|electric|hybrid|drivetrain|transmission|horsepower|torque)\b", text, re.I))


def _select_candidates(scenes: list[dict]) -> list[int]:
    ranked = sorted(range(len(scenes)), key=lambda i: (_candidate_score(scenes[i], i + 1), -i), reverse=True)
    chosen: list[int] = []
    used_roles: set[str] = set()
    for idx in ranked:
        scene = scenes[idx]
        role = _safe_text(scene.get("short_role", ""), 60).casefold()
        if not _is_automotive(scene):
            continue
        if role and role in used_roles:
            continue
        chosen.append(idx)
        if role:
            used_roles.add(role)
        if len(chosen) == REQUIRED_SHORTS:
            break
    if len(chosen) < REQUIRED_SHORTS:
        for idx in ranked:
            if idx not in chosen and _is_automotive(scenes[idx]):
                chosen.append(idx)
                if len(chosen) == REQUIRED_SHORTS:
                    break
    if len(chosen) != REQUIRED_SHORTS:
        raise ValueError("unable to select four automotive short candidates")
    return sorted(chosen)


def build_shorts(story: dict) -> list[dict]:
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("automotive shorts require exactly 25 story scenes")
    chosen = _select_candidates(scenes)
    shorts: list[dict] = []
    seen_titles: set[str] = set()
    role_defaults = ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"]
    for i, idx in enumerate(chosen, 1):
        scene = scenes[idx]
        title = _short_title(str(story.get("title", "")), scene, i)
        if title.casefold() in seen_titles:
            title = _title_fit(f"{title} {i}")
        seen_titles.add(title.casefold())
        role = _safe_text(scene.get("short_role") or role_defaults[i - 1], 60)
        shorts.append({
            "id": i,
            "scene_start": idx + 1,
            "scene_end": idx + 1,
            "title": title,
            "description": _short_description(story, title),
            "role": role,
            "score": round(_candidate_score(scene, idx + 1), 2),
            "scenes": [scene],
            "source_from_long_video": True,
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
        "version": 5,
        "niche": "cars",
        "strategy": "derive four unique Shorts directly from four high-scoring scenes of the long-form master",
        "target_duration_seconds": [MIN_SHORT_DURATION, MAX_SHORT_DURATION],
        "shorts": shorts,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("SHORTS_PLAN=PASS niche=cars count=4 source=long_video best_scene_selection=1scene_per_short")
    return shorts


if __name__ == "__main__":
    main()
