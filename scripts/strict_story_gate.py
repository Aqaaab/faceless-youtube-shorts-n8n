from __future__ import annotations

import json
import os
import re
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
RETRIES = max(1, int(os.getenv("STRICT_STORY_RETRIES", "3")))
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_HOOK_WORDS = {"shocking", "secret", "mystery", "discovered", "vanished", "hidden", "strange", "unknown", "truth", "surprising", "revealed", "impossible", "forgotten", "warning", "never"}

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_ARABIC_UNITS = {
    "صفر": 0, "واحد": 1, "واحدة": 1,
    "اثنان": 2, "اثنين": 2, "اثنا": 2, "اثنتان": 2, "اثنتين": 2, "اثنتا": 2,
    "ثلاث": 3, "ثلاثة": 3,
    "اربع": 4, "اربعة": 4,
    "خمس": 5, "خمسة": 5,
    "ست": 6, "ستة": 6,
    "سبع": 7, "سبعة": 7,
    "ثمان": 8, "ثمانية": 8,
    "تسع": 9, "تسعة": 9,
    "عشر": 10, "عشرة": 10,
}
_ARABIC_TEENS = {
    "احد عشر": 11, "اثنا عشر": 12, "اثني عشر": 12,
    "اثنتا عشر": 12, "اثنتي عشر": 12,
    "ثلاثة عشر": 13, "اربعة عشر": 14, "خمسة عشر": 15,
    "ستة عشر": 16, "سبعة عشر": 17, "ثمانية عشر": 18, "تسعة عشر": 19,
}
_ARABIC_TENS = {
    "عشرون": 20, "عشرين": 20,
    "ثلاثون": 30, "ثلاثين": 30,
    "اربعون": 40, "اربعين": 40,
    "خمسون": 50, "خمسين": 50,
    "ستون": 60, "ستين": 60,
    "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80,
    "تسعون": 90, "تسعين": 90,
}
_ARABIC_HUNDREDS = {
    "مئة": 100, "مائه": 100, "مائة": 100, "مئه": 100,
    "مئتان": 200, "مائتان": 200, "مئتين": 200, "مائتين": 200,
    "ثلاثمئة": 300, "ثلاثمائة": 300,
    "اربعمئة": 400, "اربعمائة": 400,
    "خمسمئة": 500, "خمسمائة": 500,
    "ستمئة": 600, "ستمائة": 600,
    "سبعمئة": 700, "سبعمائة": 700,
    "ثمانمئة": 800, "ثمانمائة": 800,
    "تسعمئة": 900, "تسعمائة": 900,
}

_ARABIC_NUMBER_TOKENS = set(_ARABIC_UNITS) | set(_ARABIC_TENS) | set(_ARABIC_HUNDREDS) | {
    "الف", "الفا", "الفان", "الفين",
    "مليون", "مليونين", "ملايين",
}


def _normalize_digits(text: str) -> str:
    return (text or "").translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")


def _canonical_digit_token(token: str) -> str:
    token = token.replace(",", "")
    if "." in token:
        left, right = token.split(".", 1)
        right = right.rstrip("0")
        if not right:
            return str(int(left or "0"))
        return f"{int(left or '0')}.{right}"
    return str(int(token))


def _explicit_numbers(text: str) -> list[str]:
    normalized = _normalize_digits(text)
    return [_canonical_digit_token(token) for token in re.findall(r"\d+(?:[.,]\d+)?", normalized)]


def _normalize_arabic_word(word: str) -> str:
    word = _ARABIC_DIACRITICS.sub("", word).replace("ـ", "")
    return (
        word.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
    )


def _arabic_words(text: str) -> list[str]:
    words = re.findall(r"[\u0600-\u06ff]+", _normalize_digits(text))
    return [re.sub(r"[،؛؟۔]", "", _normalize_arabic_word(token)) for token in words]


def _arabic_number_value(token: str) -> int | None:
    token = _normalize_arabic_word(token)
    if token in _ARABIC_UNITS:
        return _ARABIC_UNITS[token]
    if token in _ARABIC_TENS:
        return _ARABIC_TENS[token]
    if token in _ARABIC_HUNDREDS:
        return _ARABIC_HUNDREDS[token]
    if token in {"الف", "الفا"}:
        return 1000
    if token in {"الفان", "الفين"}:
        return 2000
    if token == "مليون":
        return 1_000_000
    if token == "مليونين":
        return 2_000_000
    if token.startswith("و") and len(token) > 1:
        return _arabic_number_value(token[1:])
    return None


def _parse_arabic_number_run(words: list[str]) -> int:
    normalized = [_normalize_arabic_word(word) for word in words]
    joined = " ".join(normalized)
    for phrase, value in sorted(_ARABIC_TEENS.items(), key=lambda item: -len(item[0])):
        if joined == phrase:
            return value
    total = 0
    current = 0
    for word in normalized:
        if word == "و":
            continue
        value = _arabic_number_value(word)
        if value is None:
            continue
        if value == 1000:
            total += (current or 1) * 1000
            current = 0
        elif value == 2000:
            total += 2000
            current = 0
        elif value == 1_000_000:
            total += (current or 1) * 1_000_000
            current = 0
        elif value == 2_000_000:
            total += 2_000_000
            current = 0
        else:
            current += value
    return total + current


def _arabic_number_words(text: str) -> list[str]:
    words = _arabic_words(text)
    values: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        values.append(str(_parse_arabic_number_run(run)))
        run.clear()

    for index, word in enumerate(words):
        normalized = _normalize_arabic_word(word)
        number_like = (
            normalized in _ARABIC_NUMBER_TOKENS
            or _arabic_number_value(normalized) is not None
            or normalized in {"احد", "اثنا", "اثني", "اثنتا", "اثنتي"}
        )
        if normalized == "و":
            next_word = _normalize_arabic_word(words[index + 1]) if index + 1 < len(words) else ""
            if run and (_arabic_number_value(next_word) is not None or next_word in _ARABIC_NUMBER_TOKENS):
                run.append(normalized)
                continue
            flush()
            continue
        if number_like:
            run.append(normalized)
        else:
            flush()
    flush()
    return values


def _dedupe_adjacent(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if not out or out[-1] != value:
            out.append(value)
    return out


def _digits(text: str) -> list[str]:
    explicit = _explicit_numbers(text)
    words = _arabic_number_words(text)
    return _dedupe_adjacent(explicit + words) if explicit else _dedupe_adjacent(words)


def _is_hook(scene: dict) -> bool:
    text = str(scene.get("text_en", "")).strip().lower()
    beat = str(scene.get("beat", "")).strip().lower()
    words = re.findall(r"[a-z][a-z'-]*", text)
    has_hook_signal = any(word in _HOOK_WORDS for word in words) or "?" in text or "!" in text
    has_open_loop = any(token in text for token in ("but", "until", "why", "how", "what", "no one", "didn't", "couldn't"))
    return beat == "hook" and len(words) >= 18 and (has_hook_signal or has_open_loop)


def _local_contract(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("STRICT_STORY_GATE: story must contain exactly 25 scenes")
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} is not an object")
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        visual = str(scene.get("visual_subject", "")).strip()
        query = str(scene.get("pexels_query", "")).strip()
        if not en or not ar or not visual or not query or not str(scene.get("beat", "")).strip():
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} has missing content")
        if _digits(en) != _digits(ar):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} changed numeric facts between English and Arabic")
        if len(re.findall(r"[\u0600-\u06ff]", ar)) < 12:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Arabic is too short")
        if not 3 <= len(query.split()) <= 9:
            raise RuntimeError(f"STRICT_STORY_GATE: scene {i} Pexels query is not concrete enough")
    for index in (1, 7, 13, 19):
        if not _is_hook(scenes[index - 1]):
            raise RuntimeError(f"STRICT_STORY_GATE: scene {index} must be a genuine hook")


def _review(story: dict) -> dict:
    rules = [
        "Return exactly 25 scenes with complete metadata.",
        "Scenes 1, 7, 13 and 19 must be genuine hooks: introduce a specific mystery, contradiction, danger, surprising fact, unanswered question, or open loop; never a generic introduction.",
        "Each hook must be at least 18 English words and contain a hook signal or open-loop construction.",
        "Preserve every number, named entity, chronology, causal relationship, and factual scope.",
        "Arabic must faithfully preserve the English meaning in fluent Modern Standard Arabic. Numeric facts may be rendered as Arabic digits or Arabic number words, but their semantic value must remain identical.",
        "Every visual_subject and pexels_query must describe concrete visible footage.",
        "Return complete JSON only, without markdown or commentary.",
    ]
    current = story
    last: Exception | None = None
    for attempt in range(RETRIES):
        feedback = f"Previous failure: {last}" if last else ""
        payload = {"task": "strict_pre_render_story_audit_and_repair", "rules": rules, "validation_feedback": feedback, "story": current}
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
    try:
        _local_contract(story)
    except RuntimeError as exc:
        print(f"STRICT_STORY_GATE=REPAIR_REQUIRED reason={exc}")
    repaired = _review(story)
    repaired.setdefault("provider", story.get("provider", "Odysseus"))
    _local_contract(repaired)
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "metadata.json").write_text(json.dumps({"title": repaired.get("title", ""), "description": repaired.get("description", ""), "tags": repaired.get("tags", [])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STRICT_STORY_GATE=PASS semantic=audited hooks=validated visuals=concrete arabic=faithful")
    return repaired


if __name__ == "__main__":
    main()
