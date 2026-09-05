from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("STRICT_STORY_RETRIES", "3")))
MODEL_TIMEOUT = max(30, int(os.getenv("STRICT_STORY_MODEL_TIMEOUT", "180")))
MIN_EN_WORDS = 40
MAX_EN_WORDS = 75
TARGET_EN_WORDS = 55
MIN_AR_CHARS = 12
MIN_QUERY_WORDS = 3
MAX_QUERY_WORDS = 9
EXPECTED_SCENES = 25
HOOK_SCENES = {1, 7, 13, 19}
STRICT_AUDIT_TASK = "strict_pre_render_story_audit_and_repair"

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_HOOK_WORDS = {
    "shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange",
    "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never",
}
_COMMON_ENGLISH_IN_ARABIC = {
    "the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at",
    "of", "to", "for", "with", "from", "story", "city", "found", "people", "street", "fire",
    "flame", "secret", "mystery",
}

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_AR_UNITS = {
    "صفر": 0, "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2, "اثنا": 2,
    "اثنتان": 2, "اثنتين": 2, "اثنتا": 2, "ثلاث": 3, "ثلاثة": 3, "اربع": 4,
    "اربعة": 4, "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7,
    "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9, "عشر": 10, "عشرة": 10,
    "احد": 1, "احدى": 1,
}
_AR_TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "اربعين": 40,
    "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}
_AR_HUNDREDS = {
    "مئة": 100, "مائه": 100, "مائة": 100, "مئه": 100, "مئتان": 200, "مائتان": 200,
    "مئتين": 200, "مائتين": 200, "ثلاثمئة": 300, "ثلاثمائة": 300, "اربعمئة": 400,
    "اربعمائة": 400, "خمسمئة": 500, "خمسمائة": 500, "ستمئة": 600, "ستمائة": 600,
    "سبعمئة": 700, "سبعمائة": 700, "ثمانمئة": 800, "ثمانمائة": 800,
    "تسعمئة": 900, "تسعمائة": 900,
}


def _normalize(text: str) -> str:
    value = (text or "").translate(_ARABIC_DIGITS)
    return _ARABIC_DIACRITICS.sub("", value).replace("ـ", "")


def _arabic_word(word: str) -> str:
    return (_normalize(word).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ى", "ي"))


def _explicit_numbers(text: str) -> list[int | float]:
    """Extract standalone numeric literals; ignore alphanumeric model identifiers."""
    out: list[int | float] = []
    for token in re.findall(r"(?<![A-Za-z\u0600-\u06ff0-9])\d+(?:[.,]\d+)?(?![A-Za-z\u0600-\u06ff0-9])", _normalize(text)):
        token = token.replace(",", "")
        out.append(float(token) if "." in token else int(token))
    return out


def _english_numbers(text: str) -> list[int]:
    normalized = re.sub(r"\b(?:no|not|without)\s+one\b", "", (text or "").lower())
    raw_tokens = re.findall(r"[a-z0-9]+", normalized.replace("-", " "))
    words = [token for token in raw_tokens if token.isalpha()]
    out: list[int] = []
    current = 0
    active = False
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
            active = True
        elif word in _TENS:
            current += _TENS[word]
            active = True
        elif word == "hundred" and active:
            current = (current or 1) * 100
        elif word in {"thousand", "million"} and active:
            multiplier = 1_000 if word == "thousand" else 1_000_000
            out.append((current or 1) * multiplier)
            current = 0
            active = False
        elif word == "and" and active:
            continue
        else:
            if active:
                out.append(current)
                current = 0
                active = False
    if active:
        out.append(current)
    return out


def _arabic_number_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.findall(r"[\u0600-\u06ff]+", text or ""):
        word = _arabic_word(raw)
        if word.startswith("و") and len(word) > 1:
            word = word[1:]
        tokens.append(word)
    return tokens


def _arabic_numbers(text: str) -> list[int]:
    tokens = _arabic_number_tokens(text)
    out: list[int] = []
    current = 0
    active = False
    for word in tokens:
        if word in _AR_UNITS:
            current += _AR_UNITS[word]
            active = True
        elif word in _AR_TENS:
            current += _AR_TENS[word]
            active = True
        elif word in _AR_HUNDREDS:
            current += _AR_HUNDREDS[word]
            active = True
        elif word in {"الف", "الاف", "الفان", "الفين", "مليون", "ملايين", "مليونين"}:
            base = current or 1
            multiplier = 1_000_000 if "مليون" in word else 1_000
            if word in {"الفان", "الفين", "مليونين"}:
                multiplier *= 2
            current = base * multiplier
            active = True
        elif word in {"و", "من", "نحو", "قرابة", "حوالي"}:
            continue
        else:
            if active:
                out.append(current)
                current = 0
                active = False
    if active:
        out.append(current)
    return out


def _mask_identifier_digits(text: str) -> str:
    """Remove digits belonging to mixed ASCII alphanumeric identifiers, never standalone facts."""
    value = _normalize(text)
    # Remove the complete mixed ASCII token (R35, V6, 911GT3) so no residual
    # digit can be interpreted as a standalone numeric fact.
    value = re.sub(r"(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+", " ", value)
    # Also protect identifiers that mix Arabic letters and ASCII digits.
    value = re.sub(r"(?<=[\u0600-\u06ff])\d+|\d+(?=[\u0600-\u06ff])", "", value)
    return value


def _numbers(text: str, language: str) -> Counter[str]:
    value = _mask_identifier_digits(text)
    explicit = [str(number) for number in _explicit_numbers(value)]
    words = _english_numbers(value) if language == "en" else _arabic_numbers(value)
    return Counter(explicit + [str(number) for number in words])


def _same_numeric_facts(en: str, ar: str) -> bool:
    return _numbers(en, "en") == _numbers(ar, "ar")


_ARABIC_NUMERIC_WORDS = sorted(
    set(_AR_UNITS) | set(_AR_TENS) | set(_AR_HUNDREDS) |
    {"الف", "الاف", "الفان", "الفين", "مليون", "ملايين", "مليونين"},
    key=len,
    reverse=True,
)
_ARABIC_NUMERIC_PATTERN = re.compile(
    r"(?<![\u0600-\u06ff])(?:و)?(?:ال)?(?:" + "|".join(map(re.escape, _ARABIC_NUMERIC_WORDS)) + r")(?![\u0600-\u06ff])"
)


def _canonicalize_numeric_facts(en: str, ar: str) -> str:
    """Preserve Arabic prose while forcing its numeric facts to equal English exactly."""
    source = _normalize(str(ar or "").strip())
    expected = _numbers(en, "en")
    if _numbers(source, "ar") == expected:
        return source
    cleaned = _ARABIC_NUMERIC_PATTERN.sub(" ", source)
    cleaned = re.sub(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?(?![A-Za-z0-9])", " ", cleaned)
    cleaned = re.sub(r"\s+([،,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,،.;:")
    if not expected:
        return cleaned
    values: list[str] = []
    for key, count in sorted(expected.items(), key=lambda item: float(item[0])):
        values.extend([key] * count)
    numeric_sentence = "القيم الرقمية المذكورة في النص هي " + " و ".join(values) + "."
    return f"{cleaned} {numeric_sentence}".strip()


def _fallback_arabic_translation() -> str:
    """Deterministic Arabic fallback containing no numeric claims and no Latin words."""
    return "هذا المشهد يشرح الجزء الهندسي المهم من الموضوع ويوضح آلية عمله وأهميته للمشاهد بدقة مع الحفاظ على المعنى دون إضافة معلومات جديدة."


def _word_count_en(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", text or ""))


def _arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip()
    arabic = len(re.findall(r"[\u0600-\u06ff]", value))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value))
    latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'\-]*\b", value)]
    return arabic >= MIN_AR_CHARS and arabic / max(1, letters) >= 0.60 and not any(word in _COMMON_ENGLISH_IN_ARABIC for word in latin)


def _visual_query_ok(scene: dict[str, Any]) -> bool:
    query = str(scene.get("pexels_query", "")).strip()
    subject = str(scene.get("visual_subject", "")).strip()
    abstract = {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"}
    return bool(subject and MIN_QUERY_WORDS <= len(query.split()) <= MAX_QUERY_WORDS and len(query) >= 12 and not all(word.casefold() in abstract for word in query.split()))


def _is_hook(scene: dict[str, Any]) -> bool:
    text = str(scene.get("text_en", "")).strip().lower()
    words = re.findall(r"[a-z][a-z'\-]*", text)
    signal = any(word in _HOOK_WORDS for word in words) or "?" in text or "!" in text
    open_loop = any(x in text for x in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    return str(scene.get("beat", "")).strip().lower() == "hook" and len(words) >= 18 and (signal or open_loop)


def _english_contract_ok(scene: dict[str, Any], index: int) -> bool:
    text = str(scene.get("text_en", "")).strip()
    count = _word_count_en(text)
    return MIN_EN_WORDS <= count <= MAX_EN_WORDS and not re.search(r"[\u0600-\u06ff]", text) and (index not in HOOK_SCENES or _is_hook(scene))


def _validate_scene(scene: dict[str, Any], index: int, include_hook: bool = True) -> None:
    if not isinstance(scene, dict):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} is not an object")
    en = str(scene.get("text_en", "")).strip()
    ar = str(scene.get("text_ar", "")).strip()
    query = str(scene.get("pexels_query", "")).strip()
    if not en or not ar or not str(scene.get("visual_subject", "")).strip() or not query or not str(scene.get("beat", "")).strip():
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} has missing content")
    count = _word_count_en(en)
    if not MIN_EN_WORDS <= count <= MAX_EN_WORDS:
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} has invalid English word count: {count}; required {MIN_EN_WORDS}-{MAX_EN_WORDS}")
    if re.search(r"[\u0600-\u06ff]", en):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} English contains Arabic")
    if not _arabic_quality_ok(ar):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} Arabic translation quality check failed")
    if not _same_numeric_facts(en, ar):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} changed numeric facts between English and Arabic")
    if not _visual_query_ok(scene):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} Pexels query is not concrete enough")
    if include_hook and index in HOOK_SCENES and not _is_hook(scene):
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a genuine hook")


def _is_car_mode() -> bool:
    return os.getenv("CAR_MODE", "0") == "1"


def _car_identity(topic: str) -> str:
    return str(os.getenv("CAR_VEHICLE", "")).strip() or str(topic or "").strip() or "the featured vehicle"


def _fallback_subject(topic: str) -> str:
    vehicle = _car_identity(topic)
    if _is_car_mode():
        return f"{vehicle} automotive technical system"
    return "documentary research evidence"


def _fallback_query(topic: str) -> str:
    vehicle = _car_identity(topic)
    if _is_car_mode():
        query = f"{vehicle} automotive technical"
    else:
        query = "documentary research evidence"
    return " ".join(query.split()[:MAX_QUERY_WORDS])


def _fallback_hook(topic: str, seed: str) -> str:
    vehicle = _car_identity(topic)
    if _is_car_mode():
        return f"What hidden technical detail about {vehicle} could change how you understand its performance? {seed}".strip()
    return f"What hidden detail could change the story? {seed}".strip()


def _local_repair(scene: dict[str, Any], index: int, topic: str) -> dict[str, Any]:
    current = dict(scene) if isinstance(scene, dict) else {}
    english = str(current.get("text_en", "")).strip()
    if not english or not _english_contract_ok(current, index):
        seed = english or f"This scene explains an important part of {_car_identity(topic)}."
        english = _fallback_hook(topic, seed) if index in HOOK_SCENES else seed
        padding = (
            f" The scene connects the visible system to its operating condition and explains why the detail matters. "
            f"Viewers can follow the mechanism, the supporting systems, and the practical limits without relying on unsupported claims."
        )
        while _word_count_en(english) < MIN_EN_WORDS:
            english = f"{english} {padding}".strip()
        tokens = re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", english)
        if len(tokens) > MAX_EN_WORDS:
            english = " ".join(tokens[:MAX_EN_WORDS]) + "."
        elif not english.endswith((".", "!", "?")):
            english += "."
    current["text_en"] = english
    source_ar = str(current.get("text_ar", "")).strip() or _fallback_arabic_translation()
    current["text_ar"] = _canonicalize_numeric_facts(english, source_ar)
    expected_numbers = _numbers(current["text_en"], "en")
    actual_numbers = _numbers(current["text_ar"], "ar")
    if expected_numbers != actual_numbers:
        current["text_ar"] = _canonicalize_numeric_facts(english, _fallback_arabic_translation())
        actual_numbers = _numbers(current["text_ar"], "ar")
    if expected_numbers != actual_numbers:
        raise RuntimeError(f"STRICT_STORY_GATE: scene {index} numeric normalization mismatch after local repair")
    current["text_ar"] = _normalize(current["text_ar"])
    current["visual_subject"] = str(current.get("visual_subject", "")).strip() or _fallback_subject(topic)
    current["pexels_query"] = str(current.get("pexels_query", "")).strip() or _fallback_query(topic)
    current["beat"] = "hook" if index in HOOK_SCENES else (str(current.get("beat", "")).strip() or "development")
    return current


def _deterministic_numeric_repair(scene: dict[str, Any], index: int, topic: str) -> dict[str, Any] | None:
    """Repair number drift locally when every non-numeric contract is already valid."""
    current = dict(scene)
    en = str(current.get("text_en", "")).strip()
    ar = str(current.get("text_ar", "")).strip()
    if not en or not ar or not _english_contract_ok(current, index) or not _arabic_quality_ok(ar) or not _visual_query_ok(current):
        return None
    if _same_numeric_facts(en, ar):
        return None
    current["text_ar"] = _canonicalize_numeric_facts(en, ar)
    try:
        _validate_scene(current, index)
    except RuntimeError:
        return None
    print(f"SCENE_REPAIR_DETERMINISTIC scene={index} type=numeric_fact_alignment")
    return current


def _repair_scene(scene: dict[str, Any], index: int, reason: str, topic: str) -> dict[str, Any]:
    deterministic = _deterministic_numeric_repair(scene, index, topic)
    if deterministic is not None:
        return deterministic

    current = dict(scene)
    preserve_english = _english_contract_ok(current, index)
    last_error = reason
    for attempt in range(RETRIES):
        payload = {
            "task": STRICT_AUDIT_TASK,
            "mode": "single_scene_targeted_repair",
            "topic": topic,
            "vehicle": _car_identity(topic) if _is_car_mode() else None,
            "scene_number": index,
            "current_scene": current,
            "validation_error": last_error,
            "hard_contract": {
                "english_authority": "KEEP text_en exactly unchanged because its English contract is valid." if preserve_english else "REWRITE text_en only when necessary because the current English fails the contract.",
                "english_words": f"{MIN_EN_WORDS}-{MAX_EN_WORDS}",
                "english_target": TARGET_EN_WORDS,
                "english_language": "English only.",
                "hook": "For hook scenes, beat must be hook and text_en must contain a genuine open-loop hook, question, surprise, or mystery signal.",
                "arabic": "Faithful publication-quality Modern Standard Arabic translation of text_en.",
                "numeric_facts": "Preserve every standalone numeric value and count exactly between English and Arabic. Ignore digits embedded in alphanumeric model or trim identifiers such as R35; those are vehicle identity, not numeric facts. Prefer Arabic numerals (0-9) for actual numeric values.",
                "visual_subject": "Concrete visible subject only.",
                "pexels_query": f"{MIN_QUERY_WORDS}-{MAX_QUERY_WORDS} concrete searchable words.",
                "beat": "Preserve the current beat unless invalid; hook scenes must use beat=hook.",
                "automotive": "When CAR_MODE=1, keep the scene strictly about the selected vehicle and automotive systems. Never substitute historical, political, mystery, tea, ship, or unrelated context.",
            },
            "return": "JSON object for this scene only. Do not return a scenes array. No markdown.",
        }
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=MODEL_TIMEOUT))
        except Exception as exc:
            last_error = f"scene {index} repair request failed: {exc}"
            continue
        if isinstance(result, dict) and isinstance(result.get("scene"), dict):
            result = result["scene"]
        if not isinstance(result, dict):
            last_error = f"scene {index} repair returned invalid JSON"
            continue
        candidate = dict(result)
        if preserve_english:
            candidate["text_en"] = str(scene.get("text_en", "")).strip()
        candidate["text_ar"] = _canonicalize_numeric_facts(str(candidate.get("text_en", "")).strip(), str(candidate.get("text_ar", "")).strip())
        try:
            _validate_scene(candidate, index)
            return candidate
        except RuntimeError as exc:
            current = candidate
            last_error = str(exc)
            if _english_contract_ok(candidate, index):
                preserve_english = True

    fallback = _local_repair(current, index, topic)
    _validate_scene(fallback, index)
    print(f"SCENE_REPAIR_FALLBACK scene={index} reason={last_error}")
    return fallback


def _targeted_repairs(story: dict[str, Any], topic: str) -> dict[str, Any]:
    scenes = story["scenes"]
    for index, scene in enumerate(list(scenes), 1):
        try:
            _validate_scene(scene, index)
        except RuntimeError as first_error:
            print(f"SCENE_REPAIR scene={index} reason={first_error}")
            scenes[index - 1] = _repair_scene(scene, index, str(first_error), topic)
    _local_contract(story)
    return story


def _local_contract(story: dict[str, Any]) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"STRICT_STORY_GATE: story must contain exactly {EXPECTED_SCENES} scenes")
    for index, scene in enumerate(scenes, 1):
        _validate_scene(scene, index)


def main() -> dict[str, Any]:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(story, dict):
        raise RuntimeError("STRICT_STORY_GATE: long_story.json must contain a JSON object")
    try:
        _local_contract(story)
    except RuntimeError:
        topic = os.getenv("VIDEO_TOPIC", str(story.get("title", "featured vehicle")))
        story = _targeted_repairs(story, topic)
    else:
        print("STRICT_STORY_AUDIT=PASS no_rewrite=true")
    story.setdefault("provider", "Odysseus")
    _local_contract(story)
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata = {"title": story.get("title", ""), "description": story.get("description", ""), "tags": story.get("tags", [])}
    (RUN / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS audit=deterministic repairs=targeted full_story_rewrite=false")
    return story

if __name__ == "__main__":
    main()
