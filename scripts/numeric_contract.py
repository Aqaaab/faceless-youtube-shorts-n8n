from __future__ import annotations

import re
from collections import Counter

_DIGIT_RE = re.compile(r"(?<![A-Za-z])[0-9٠-٩۰-۹]+(?:[.,][0-9٠-٩۰-۹]+)?(?![A-Za-z])")
_AR_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

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


def _normalized_digits(value: str) -> str:
    return str(value or "").translate(_AR_DIGIT_TRANSLATION).replace(",", "")


def _normalize_explicit(text: str) -> list[str]:
    return [_normalized_digits(x) for x in _DIGIT_RE.findall(str(text or ""))]


def _spelled_value(token: str, language: str) -> str | None:
    if language == "en":
        value = _EN_WORD_VALUES.get(token.casefold())
    else:
        value = _AR_WORD_VALUES.get(_normalize_ar_word(token))
    return str(value) if value is not None else None


def _unit_adjacent_spelled_numbers(text: str, language: str) -> list[str]:
    if language == "en":
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'/-]*", str(text or ""))
        normalized = [t.casefold() for t in tokens]
        units = _EN_UNITS
    else:
        tokens = re.findall(r"[\u0600-\u06ff]+", str(text or ""))
        normalized = [_normalize_ar_word(t) for t in tokens]
        units = {_normalize_ar_word(t) for t in _AR_UNITS}

    out: list[str] = []
    for i, token in enumerate(tokens):
        value = _spelled_value(token, language)
        if value is None:
            continue
        neighbors = []
        if i > 0:
            neighbors.append(normalized[i - 1])
        if i + 1 < len(tokens):
            neighbors.append(normalized[i + 1])
        if any(item in units for item in neighbors):
            out.append(value)
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

    digits = [str(v).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")) for v in expected]
    cursor = 0

    def replace_explicit(match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(digits):
            return match.group(0)
        value = digits[cursor]
        cursor += 1
        return value

    repaired = _DIGIT_RE.sub(replace_explicit, source)
    if same_numeric_facts(en, repaired):
        return repaired

    tokens = list(re.finditer(r"[\u0600-\u06ff]+", repaired))
    unit_words = {_normalize_ar_word(t) for t in _AR_UNITS}
    replacements: list[tuple[int, int, str]] = []
    for idx, match in enumerate(tokens):
        value = _spelled_value(match.group(0), "ar")
        if value is None:
            continue
        neighbors = []
        if idx > 0:
            neighbors.append(_normalize_ar_word(tokens[idx - 1].group(0)))
        if idx + 1 < len(tokens):
            neighbors.append(_normalize_ar_word(tokens[idx + 1].group(0)))
        if any(n in unit_words for n in neighbors) and cursor < len(digits):
            replacements.append((match.start(), match.end(), digits[cursor]))
            cursor += 1
    for start, end, value in reversed(replacements):
        repaired = repaired[:start] + value + repaired[end:]
    return repaired
