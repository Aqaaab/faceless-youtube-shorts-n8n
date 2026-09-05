from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIGIT_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])")

# Only spelled-out numbers that are attached to objective measurement/specification
# units are treated as numeric facts. Bare words such as "one" or "seven" are
# ordinary language and must not cause an EN/AR contract failure.
_EN_UNITS = {
    "hp", "horsepower", "bhp", "ps", "nm", "lb-ft", "mph", "kmh", "km/h", "kph",
    "rpm", "liter", "liters", "litre", "litres", "cylinder", "cylinders", "speed", "speeds",
    "gear", "gears", "second", "seconds", "ms", "millisecond", "milliseconds", "kg", "kgs",
    "kilogram", "kilograms", "lb", "lbs", "pound", "pounds", "mile", "miles", "percent", "percentage",
    "kw", "kilowatt", "kilowatts", "degree", "degrees", "volt", "volts", "liter", "litre",
}
_AR_UNITS = {
    "حصان", "أحصنة", "حصانا", "حصاناً", "نيوتن", "نيوتنمتر", "نيوتن\u200fمتر", "كم/س", "كم\u200f/\u200fس",
    "دورة", "دورات", "دقيقة", "دقائق", "لتر", "لترات", "أسطوانة", "أسطوانات", "اسطوانة", "اسطوانات",
    "سرعة", "سرعات", "غيار", "غيارات", "ثانية", "ثوان", "ثواني", "كيلوغرام", "كيلوجرام", "كجم", "رطل",
    "ميل", "أميال", "بالمئة", "بالمائة", "نسبة", "كيلوواط", "فولت", "فولتات", "درجة", "درجات",
}

_EN_UNITS = {x.casefold() for x in _EN_UNITS}
_AR_UNITS = {x.casefold() for x in _AR_UNITS}

_EN_UNITS_NEAR = re.compile(r"[A-Za-z][A-Za-z0-9'/-]*")
_AR_WORD = re.compile(r"[\u0600-\u06ff]+")


def _normalize_explicit(text: str) -> list[str]:
    return [x.replace(",", "") for x in _DIGIT_RE.findall(str(text or "").translate(_AR_DIGITS))]


def _number_words(tokens: Iterable[str], language: str) -> list[str]:
    if language == "en":
        units = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                 "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                 "eighteen": 18, "nineteen": 19}
        tens = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
                "seventy": 70, "eighty": 80, "ninety": 90}
        raw = [t.casefold().replace("-", " ") for t in tokens]
    else:
        units = {"صفر": 0, "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2, "اثنا": 2,
                 "اثنتان": 2, "اثنتين": 2, "اثنتا": 2, "ثلاث": 3, "ثلاثة": 3, "اربع": 4,
                 "اربعة": 4, "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7,
                 "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9, "عشر": 10, "عشرة": 10}
        tens = {"عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "اربعين": 40,
                "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
                "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90}
        raw = [t.casefold().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي") for t in tokens]

    values: list[int] = []
    for token in raw:
        for part in token.split():
            if part in units:
                values.append(units[part])
            elif part in tens:
                values.append(tens[part])
    return [str(v) for v in values]


def _unit_adjacent_spelled_numbers(text: str, language: str) -> list[str]:
    if language == "en":
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'/-]*", str(text or ""))
        units = _EN_UNITS
    else:
        tokens = re.findall(r"[\u0600-\u06ff]+", str(text or ""))
        units = _AR_UNITS
    out: list[str] = []
    for i, token in enumerate(tokens):
        lower = token.casefold()
        window = [t.casefold() for t in tokens[max(0, i - 2): min(len(tokens), i + 3)]]
        if any(u in units for u in window if u == u.casefold()):
            candidate = _number_words([token], language)
            if candidate:
                out.extend(candidate)
    return out


def numeric_facts(text: str, language: str) -> Counter[str]:
    explicit = _normalize_explicit(text)
    spelled = _unit_adjacent_spelled_numbers(text, language)
    return Counter(explicit + spelled)


def same_numeric_facts(en: str, ar: str) -> bool:
    return numeric_facts(en, "en") == numeric_facts(ar, "ar")


def align_arabic_numeric_facts(en: str, ar: str) -> str:
    source = str(ar or "").strip()
    if same_numeric_facts(en, source):
        return source
    expected = list(numeric_facts(en, "en").elements())
    if not expected:
        return source

    values = [str(v) for v in expected]
    cursor = 0

    def replace_digit(match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(values):
            return match.group(0)
        value = values[cursor]
        cursor += 1
        return value.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))

    repaired = _DIGIT_RE.sub(replace_digit, source)
    if same_numeric_facts(en, repaired):
        return repaired

    # Remove only unit-adjacent Arabic number words when they are the remaining
    # mismatch; leave ordinary Arabic prose untouched.
    arabic_number_words = (
        "صفر|واحد|واحدة|اثنان|اثنين|اثنا|اثنتان|اثنتين|ثلاث|ثلاثة|اربع|اربعة|خمس|خمسة|ست|ستة|سبع|سبعة|"
        "ثمان|ثماني|ثمانية|تسع|تسعة|عشر|عشرة|عشرون|عشرين|ثلاثون|ثلاثين|اربعون|اربعين|خمسون|خمسين|"
        "ستون|ستين|سبعون|سبعين|ثمانون|ثمانين|تسعون|تسعين"
    )
    pattern = re.compile(rf"(?:و)?(?:{arabic_number_words})(?=\s*(?:{'|'.join(map(re.escape, sorted(_AR_UNITS, key=len, reverse=True)))}))")
    repaired = pattern.sub(lambda _: replace_digit(re.Match) if False else "", source)
    # Rebuild with the expected digits in the safest deterministic form when
    # number-word replacement would otherwise be ambiguous.
    if not same_numeric_facts(en, repaired):
        base = pattern.sub("", source)
        digits = "، ".join(v.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) for v in values)
        repaired = (base + " الأرقام المطابقة: " + digits).strip()
    return repaired
