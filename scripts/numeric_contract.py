from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIGIT_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])")

# Bare number words such as "one" or "seven" are ordinary language. Only
# spelled numbers attached to objective measurement/specification units count
# as facts; explicit numeric literals always count.
_EN_UNITS = {x.casefold() for x in {
    "hp", "horsepower", "bhp", "ps", "nm", "lb-ft", "mph", "kmh", "km/h", "kph",
    "rpm", "liter", "liters", "litre", "litres", "cylinder", "cylinders", "speed", "speeds",
    "gear", "gears", "second", "seconds", "ms", "millisecond", "milliseconds", "kg", "kgs",
    "kilogram", "kilograms", "lb", "lbs", "pound", "pounds", "mile", "miles", "percent", "percentage",
    "kw", "kilowatt", "kilowatts", "degree", "degrees", "volt", "volts"
}}
_AR_UNITS = {x.casefold() for x in {
    "حصان", "أحصنة", "حصانا", "حصاناً", "نيوتن", "نيوتنمتر", "نيوتن‏متر", "كم/س", "كم‏/‏س",
    "دورة", "دورات", "دقيقة", "دقائق", "لتر", "لترات", "أسطوانة", "أسطوانات", "اسطوانة", "اسطوانات",
    "سرعة", "سرعات", "غيار", "غيارات", "ثانية", "ثوان", "ثواني", "كيلوغرام", "كيلوجرام", "كجم", "رطل",
    "ميل", "أميال", "بالمئة", "بالمائة", "نسبة", "كيلوواط", "فولت", "فولتات", "درجة", "درجات"
}}

_EN_WORD_VALUES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_AR_WORD_VALUES = {
    "صفر": 0, "واحد": 1, "واحدة": 1, "اثنان": 2, "اثنين": 2, "اثنا": 2,
    "اثنتان": 2, "اثنتين": 2, "ثلاث": 3, "ثلاثة": 3, "اربع": 4, "اربعة": 4,
    "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7,
    "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9,
    "عشر": 10, "عشرة": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30,
    "ثلاثين": 30, "اربعون": 40, "اربعين": 40, "خمسون": 50, "خمسين": 50,
    "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70, "ثمانون": 80,
    "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}


def _normalize_ar_word(value: str) -> str:
    return (value or "").translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})).casefold()


def _normalize_explicit(text: str) -> list[str]:
    return [x.replace(",", "") for x in _DIGIT_RE.findall(str(text or "").translate(_AR_DIGITS))]


def _spelled_number(token: str, language: str) -> list[str]:
    if language == "en":
        parts = token.casefold().replace("-", " ").split()
        mapping = _EN_WORD_VALUES
    else:
        parts = [_normalize_ar_word(token)]
        mapping = {k: v for k, v in _AR_WORD_VALUES.items()}
    values = [mapping[p] for p in parts if p in mapping]
    return [str(v) for v in values]


def _unit_adjacent_spelled_numbers(text: str, language: str) -> list[str]:
    if language == "en":
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'/-]*", str(text or ""))
        units = _EN_UNITS
        normalized = [t.casefold() for t in tokens]
    else:
        tokens = re.findall(r"[\u0600-\u06ff]+", str(text or ""))
        units = _AR_UNITS
        normalized = [_normalize_ar_word(t) for t in tokens]

    out: list[str] = []
    for i, token in enumerate(tokens):
        number_values = _spelled_number(token, language)
        if not number_values:
            continue
        window = normalized[max(0, i - 2): min(len(tokens), i + 3)]
        if any(candidate in units for candidate in window):
            out.extend(number_values)
    return out


def numeric_facts(text: str, language: str) -> Counter[str]:
    return Counter(_normalize_explicit(text) + _unit_adjacent_spelled_numbers(text, language))


def same_numeric_facts(en: str, ar: str) -> bool:
    return numeric_facts(en, "en") == numeric_facts(ar, "ar")


def align_arabic_numeric_facts(en: str, ar: str) -> str:
    source = str(ar or "").strip()
    if same_numeric_facts(en, source):
        return source
    expected = list(numeric_facts(en, "en").elements())
    if not expected:
        return source

    # For explicit digit mismatches, replace Arabic/Latin standalone numeric
    # literals in-place. This preserves the surrounding Arabic translation.
    cursor = 0
    digits = [str(v).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) for v in expected]
    def repl(match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(digits):
            return match.group(0)
        value = digits[cursor]
        cursor += 1
        return value

    repaired = _DIGIT_RE.sub(repl, source)
    if same_numeric_facts(en, repaired):
        return repaired

    # If the Arabic side uses spelled numeric words, convert only the
    # unit-adjacent number words to digits. We deliberately avoid rewriting
    # ordinary number words elsewhere in prose.
    arabic_words = sorted(_AR_WORD_VALUES, key=len, reverse=True)
    unit_pattern = "|".join(re.escape(x) for x in sorted(_AR_UNITS, key=len, reverse=True))
    number_pattern = "|".join(re.escape(x) for x in arabic_words)
    pattern = re.compile(rf"(?:و)?(?:{number_pattern})(?=\s*(?:{unit_pattern}))")
    cursor = 0
    def repl_word(match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(digits):
            return match.group(0)
        value = digits[cursor]
        cursor += 1
        return value

    repaired = pattern.sub(repl_word, source)
    return repaired
