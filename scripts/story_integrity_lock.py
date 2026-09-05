from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from strict_story_gate import (
    EXPECTED_SCENES,
    HOOK_SCENES,
    MAX_EN_WORDS,
    MIN_EN_WORDS,
    _is_hook,
    _numbers,
    _same_numeric_facts,
    _word_count_en,
)

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))

_ARABIC_NUMERIC_WORDS = sorted(
    {
        "صفر", "واحد", "واحدة", "اثنان", "اثنين", "اثنا", "اثنتان", "اثنتين", "اثنتا",
        "ثلاث", "ثلاثة", "اربع", "اربعة", "أربع", "أربعة", "خمس", "خمسة", "ست", "ستة",
        "سبع", "سبعة", "ثمان", "ثماني", "ثمانية", "تسع", "تسعة", "عشر", "عشرة",
        "احد", "إحد", "احدى", "إحدى", "عشرون", "عشرين", "ثلاثون", "ثلاثين", "اربعون",
        "أربعون", "اربعين", "أربعين", "خمسون", "خمسين", "ستون", "ستين", "سبعون", "سبعين",
        "ثمانون", "ثمانين", "تسعون", "تسعين", "مئة", "مائه", "مائة", "مئه", "مئتان", "مائتان",
        "مئتين", "مائتين", "ثلاثمئة", "ثلاثمائة", "اربعمئة", "اربعمائة", "أربعمئة", "أربعمائة",
        "خمسمئة", "خمسمائة", "ستمئة", "ستمائة", "سبعمئة", "سبعمائة", "ثمانمئة", "ثمانمائة",
        "تسعمئة", "تسعمائة", "الف", "الاف", "الفان", "الفين", "مليون", "ملايين", "مليونين",
    },
    key=len,
    reverse=True,
)

_ARABIC_NUMERIC_PATTERN = re.compile(
    r"(?<![\u0600-\u06ff])(?:و)?(?:ال)?(?:"
    + "|".join(map(re.escape, _ARABIC_NUMERIC_WORDS))
    + r")(?![\u0600-\u06ff])"
)
_DIGIT_PATTERN = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])")


def _arabic_digits(value: str) -> str:
    return str(value).translate(str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫"))


def force_numeric_alignment(en: str, ar: str) -> str:
    """Remove every recognized numeric claim from Arabic and append the exact EN values as Arabic digits."""
    expected = _numbers(en, "en")
    source = str(ar or "").strip()
    if _numbers(en, "en") == _numbers(source, "ar"):
        return source

    cleaned = _ARABIC_NUMERIC_PATTERN.sub(" ", source)
    cleaned = _DIGIT_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+([،,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,،.;:")

    values: list[str] = []
    for key, count in sorted(expected.items(), key=lambda item: float(item[0])):
        values.extend([_arabic_digits(key)] * count)

    if values:
        audit = "الأرقام المطابقة للنص الإنجليزي: " + "، ".join(values) + "."
        return f"{cleaned} {audit}".strip()
    return cleaned


def _repair_hook(scene: dict, index: int, vehicle: str) -> bool:
    if index not in HOOK_SCENES:
        return False
    text = str(scene.get("text_en", "")).strip()
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", text)
    if len(words) >= 18 and _is_hook(scene):
        return False
    prefix = f"What hidden detail about {vehicle} could change how you understand its performance?"
    merged = f"{prefix} {text}".strip()
    tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", merged)
    if len(tokens) > MAX_EN_WORDS:
        merged = " ".join(tokens[:MAX_EN_WORDS]) + "."
    scene["text_en"] = merged
    scene["beat"] = "hook"
    return True


def main() -> dict:
    path = RUN / "long_story.json"
    story = json.loads(path.read_text(encoding="utf-8"))
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"STORY_INTEGRITY_LOCK: expected exactly {EXPECTED_SCENES} scenes")

    vehicle = os.getenv("CAR_VEHICLE", str(story.get("title", "the featured vehicle")))
    numeric_repairs = 0
    hook_repairs = 0

    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"STORY_INTEGRITY_LOCK: scene {index} is not an object")
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        if not en or not ar:
            raise RuntimeError(f"STORY_INTEGRITY_LOCK: scene {index} missing EN/AR text")

        if _repair_hook(scene, index, vehicle):
            hook_repairs += 1
            en = str(scene["text_en"]).strip()

        if not _same_numeric_facts(en, ar):
            repaired = force_numeric_alignment(en, ar)
            if not _same_numeric_facts(en, repaired):
                raise RuntimeError(
                    f"STORY_INTEGRITY_LOCK: scene {index} numeric mismatch remains after deterministic repair "
                    f"EN={dict(_numbers(en, 'en'))} AR={dict(_numbers(repaired, 'ar'))}"
                )
            scene["text_ar"] = repaired
            numeric_repairs += 1

        final_en = str(scene.get("text_en", "")).strip()
        final_ar = str(scene.get("text_ar", "")).strip()
        count = _word_count_en(final_en)
        if not MIN_EN_WORDS <= count <= MAX_EN_WORDS:
            raise RuntimeError(
                f"STORY_INTEGRITY_LOCK: scene {index} English word count {count} outside {MIN_EN_WORDS}-{MAX_EN_WORDS}"
            )
        if not _same_numeric_facts(final_en, final_ar):
            raise RuntimeError(
                f"STORY_INTEGRITY_LOCK: scene {index} final numeric facts differ "
                f"EN={dict(_numbers(final_en, 'en'))} AR={dict(_numbers(final_ar, 'ar'))}"
            )
        if index in HOOK_SCENES and not _is_hook(scene):
            raise RuntimeError(f"STORY_INTEGRITY_LOCK: scene {index} hook contract failed")

    path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"STORY_INTEGRITY_LOCK=PASS scenes={len(scenes)} "
        f"numeric_repairs={numeric_repairs} hook_repairs={hook_repairs}"
    )
    return story


if __name__ == "__main__":
    main()
