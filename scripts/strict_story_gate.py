from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("STRICT_STORY_RETRIES", "3")))

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_HOOK_WORDS = {"shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange", "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never"}

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_AR_UNITS = {"صفر": 0, "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2, "اثنا": 2, "اثنتان": 2, "اثنتين": 2, "اثنتا": 2, "ثلاث": 3, "ثلاثة": 3, "اربع": 4, "اربعة": 4, "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7, "ثمان": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9, "عشر": 10, "عشرة": 10}
_AR_TENS = {"عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "اربعين": 40, "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70, "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90}
_AR_HUNDREDS = {"مئة": 100, "مائه": 100, "مائة": 100, "مئه": 100, "مئتان": 200, "مائتان": 200, "مئتين": 200, "مائتين": 200, "ثلاثمئة": 300, "ثلاثمائة": 300, "اربعمئة": 400, "اربعمائة": 400, "خمسمئة": 500, "خمسمائة": 500, "ستمئة": 600, "ستمائة": 600, "سبعمئة": 700, "سبعمائة": 700, "ثمانمئة": 800, "ثمانمائة": 800, "تسعمئة": 900, "تسعمائة": 900}


def _normalize(text: str) -> str:
    return _ARABIC_DIACRITICS.sub("", (text or "").translate(_ARABIC_DIGITS)).replace("ـ", "")


def _arabic_word(word: str) -> str:
    return _normalize(word).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ى", "ي")


def _explicit_numbers(text: str) -> list[int | float]:
    out: list[int | float] = []
    for token in re.findall(r"\d+(?:[.,]\d+)?", _normalize(text)):
        token = token.replace(",", "")
        value = float(token) if "." in token else int(token)
        out.append(value)
    return out


def _english_numbers(text: str) -> list[int]:
    words = re.findall(r"[a-z]+", (text or "").lower().replace("-", " "))
    out: list[int] = []
    current = 0
    active = False
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]; active = True
        elif word in _TENS:
            current += _TENS[word]; active = True
        elif word == "hundred" and active:
            current = (current or 1) * 100
        elif word in {"thousand", "million"} and active:
            multiplier = 1000 if word == "thousand" else 1_000_000
            out.append(current * multiplier); current = 0; active = False
        elif word == "and" and active:
            continue
        else:
            if active:
                out.append(current); current = 0; active = False
    if active:
        out.append(current)
    return out


def _arabic_numbers(text: str) -> list[int]:
    words = [_arabic_word(w) for w in re.findall(r"[\u0600-\u06ff]+", text or "")]
    out: list[int] = []
    current = 0
    active = False
    for word in words:
        if word.startswith("و") and len(word) > 1:
            word = word[1:]
        if word in _AR_UNITS:
            current += _AR_UNITS[word]; active = True
        elif word in _AR_TENS:
            current += _AR_TENS[word]; active = True
        elif word in _AR_HUNDREDS:
            current += _AR_HUNDREDS[word]; active = True
        elif word in {"الف", "الفا", "الفان", "الفين", "مليون", "مليونين"}:
            multiplier = 2 if word in {"الفان", "الفين", "مليونين"} else 1
            unit = 1_000_000 if "مليون" in word else 1000
            out.append((current or 1) * unit * multiplier); current = 0; active = False
        else:
            if active:
                out.append(current); current = 0; active = False
    if active:
        out.append(current)
    return out


def _numbers(text: str, language: str) -> Counter[str]:
    explicit = [str(x) for x in _explicit_numbers(text)]
    words = _english_numbers(text) if language == "en" else _arabic_numbers(text)
    return Counter(explicit + [str(x) for x in words])


def _same_numeric_facts(en: str, ar: str) -> bool:
    return _numbers(en, "en") == _numbers(ar, "ar")


def _is_hook(scene: dict) -> bool:
    text = str(scene.get("text_en", "")).strip().lower()
    words = re.findall(r"[a-z][a-z'-]*", text)
    signal = any(word in _HOOK_WORDS for word in words) or "?" in text or "!" in text
    open_loop = any(x in text for x in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    return str(scene.get("beat", "")).strip().lower() == "hook" and len(words) >= 18 and (signal or open_loop)


def _local_contract(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("STRICT_STORY_GATE: story must contain exactly 25 scenes")
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} is not an object")
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        if not en or not ar or not str(scene.get("visual_subject", "")).strip() or not query or not str(scene.get("beat", "")).strip():
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} has missing content")
        if not _same_numeric_facts(en, ar):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} changed numeric facts between English and Arabic")
        if len(re.findall(r"[\u0600-\u06ff]", ar)) < 12:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} Arabic is too short")
        if not 3 <= len(query.split()) <= 9:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} Pexels query is not concrete enough")
    for index in (1, 7, 13, 19):
        if not _is_hook(scenes[index - 1]):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a genuine hook")


def _review(story: dict) -> dict:
    rules = [
        "Return exactly 25 scenes with complete metadata.",
        "Scenes 1, 7, 13 and 19 must be genuine hooks of at least 18 English words.",
        "Preserve every numeric fact exactly; Arabic may use Arabic digits or number words, but the numeric value and count must match English.",
        "Preserve named entities, chronology, causal relationships, and factual scope.",
        "Arabic must faithfully preserve the English meaning in fluent Modern Standard Arabic.",
        "Every visual_subject and pexels_query must describe concrete visible footage.",
        "Return complete JSON only, without markdown or commentary.",
    ]
    current = story
    last: Exception | None = None
    for _ in range(RETRIES):
        payload = {"task": "strict_pre_render_story_audit_and_repair", "rules": rules, "validation_feedback": str(last) if last else "", "story": current}
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=240))
            if not isinstance(result, dict):
                raise RuntimeError("strict audit returned non-object JSON")
            _local_contract(result)
            return result
        except Exception as exc:
            last = exc
            if isinstance(locals().get("result"), dict):
                current = result
    raise RuntimeError("STRICT_STORY_GATE failed after deterministic and semantic validation") from last


def main() -> dict:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    story = json.loads(path.read_text(encoding="utf-8"))
    repaired = _review(story) if True else story
    repaired.setdefault("provider", story.get("provider", "Odysseus"))
    _local_contract(repaired)
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "metadata.json").write_text(json.dumps({"title": repaired.get("title", ""), "description": repaired.get("description", ""), "tags": repaired.get("tags", [])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS semantic=audited hooks=validated visuals=concrete arabic=faithful")
    return repaired


if __name__ == "__main__":
    main()
