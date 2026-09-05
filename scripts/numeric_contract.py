from __future__ import annotations

import re
from collections import Counter

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_ARABIC_LETTER = r"\u0600-\u06ff"
_DIGIT_RE = re.compile(rf"(?<![A-Za-z0-9{_ARABIC_LETTER}])[0-9]+(?:[.,][0-9]+)?(?![A-Za-z0-9{_ARABIC_LETTER}])")

_EN_WORD_VALUES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_AR_WORD_VALUES = {
    "صفر": 0, "واحد": 1, "واحدا": 1, "واحدة": 1,
    "اثنان": 2, "اثنين": 2, "اثنا": 2, "اثنتان": 2, "اثنتين": 2, "اثنتا": 2,
    "ثلاث": 3, "ثلاثة": 3, "اربعة": 4, "اربع": 4,
    "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6, "سبع": 7, "سبعة": 7,
    "ثمان": 8, "ثماني": 8, "ثمانية": 8, "تسع": 9, "تسعة": 9,
    "عشر": 10, "عشرة": 10, "احد": 1, "احدى": 1,
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30,
    "اربعون": 40, "اربعين": 40, "خمسون": 50, "خمسين": 50,
    "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70,
    "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
    "مئة": 100, "مائه": 100, "مائة": 100, "مئه": 100,
    "مئتان": 200, "مائتان": 200, "مئتين": 200, "مائتين": 200,
    "ثلاثمئة": 300, "ثلاثمائة": 300, "اربعمئة": 400, "اربعمائة": 400,
    "خمسمئة": 500, "خمسمائة": 500, "ستمئة": 600, "ستمائة": 600,
    "سبعمئة": 700, "سبعمائة": 700, "ثمانمئة": 800, "ثمانمائة": 800,
    "تسعمئة": 900, "تسعمائة": 900, "الف": 1000, "الاف": 1000,
    "الفان": 2000, "الفين": 2000, "مليون": 1000000, "ملايين": 1000000,
    "مليونين": 2000000,
}

# Spelled numbers are facts only when they clearly quantify a measurement/count field.
# This deliberately avoids treating ordinary prose such as "one car uses a system" as a
# numeric fact, while still protecting claims such as "seven temperature checks" or "eight cylinders".
_EN_QUANTITY_TERMS = {
    "check", "checks", "cylinder", "cylinders", "door", "doors", "second", "seconds",
    "minute", "minutes", "hour", "hours", "liter", "liters", "litre", "litres", "mile", "miles",
    "km", "kilometer", "kilometers", "kilometre", "kilometres", "mph", "rpm", "horsepower", "hp",
    "bhp", "ps", "nm", "degrees", "degree", "percent", "percentage", "gear", "gears", "valve", "valves",
    "stage", "stages", "mode", "modes", "temperature", "temperatures", "pressure", "pressures",
    "ratio", "ratios", "inches", "inch", "feet", "foot", "points", "point", "years", "year",
}
_AR_QUANTITY_TERMS = {
    "فحص", "فحوصات", "اسطوانة", "اسطوانات", "باب", "ابواب", "ثانية", "ثوان", "ثواني", "دقيقة", "دقائق",
    "ساعة", "ساعات", "لتر", "لترات", "ميل", "اميال", "كيلومتر", "كيلومترات", "حصان", "احصنة", "دورة", "دورات",
    "درجة", "درجات", "بالمئة", "نسبة", "تروس", "ترس", "صمام", "صمامات", "مرحلة", "مراحل", "وضع", "اوضع",
    "حرارة", "درجات الحرارة", "ضغط", "ضغوط", "نسبة", "نسب", "نقطة", "نقاط", "سنة", "سنوات",
}


def _normalize_ar_word(value: str) -> str:
    value = _ARABIC_DIACRITICS.sub("", str(value or "").translate(_ARABIC_DIGITS))
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ى", "ي")
    return value.casefold()


def _numeric_text(value: str) -> str:
    return str(value or "").translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", ",")


def _explicit_values(text: str) -> list[str]:
    value = _numeric_text(text)
    return [m.group(0).replace(",", "") for m in _DIGIT_RE.finditer(value)]


def _english_spelled_values(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", str(text or "").casefold())
    out: list[str] = []
    current = 0
    active = False
    for pos, word in enumerate(raw):
        if word in _EN_WORD_VALUES:
            current += _EN_WORD_VALUES[word]
            active = True
        elif word == "hundred" and active:
            current = (current or 1) * 100
        elif word in {"thousand", "million"} and active:
            out.append(str((current or 1) * (1000 if word == "thousand" else 1000000)))
            current = 0
            active = False
        elif word == "and" and active:
            continue
        elif active:
            # Only keep a spelled value when the immediately following noun/measurement
            # makes the number semantically factual; otherwise it is ordinary prose.
            if word in _EN_QUANTITY_TERMS:
                out.append(str(current))
            current = 0
            active = False
    if active:
        out.append(str(current))
    lowered = str(text or "").casefold()
    if any(phrase in lowered for phrase in ("no one", "not one", "without one")):
        out = [value for value in out if value != "1"]
    return out


def _arabic_spelled_values(text: str) -> list[str]:
    raw = re.findall(rf"[{_ARABIC_LETTER}]+", str(text or ""))
    out: list[str] = []
    for pos, raw_word in enumerate(raw):
        word = _normalize_ar_word(raw_word)
        value = _AR_WORD_VALUES.get(word)
        if value is None and word.startswith("و") and len(word) > 1:
            value = _AR_WORD_VALUES.get(word[1:])
        if value is None:
            continue
        following = ""
        if pos + 1 < len(raw):
            following = _normalize_ar_word(raw[pos + 1])
        if following in _AR_QUANTITY_TERMS:
            out.append(str(value))
    return out


def numeric_facts(text: str, language: str) -> Counter[str]:
    language = str(language or "en").casefold()
    values = _explicit_values(text)
    values.extend(_english_spelled_values(text) if language == "en" else _arabic_spelled_values(text))
    return Counter(values)


def same_numeric_facts(en: str, ar: str) -> bool:
    return numeric_facts(en, "en") == numeric_facts(ar, "ar")


def _arabic_digit(value: str) -> str:
    return str(value).replace(".", "٫").translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def align_arabic_numeric_facts(en: str, ar: str) -> str:
    source = str(ar or "").strip()
    expected = numeric_facts(en, "en")
    if numeric_facts(source, "ar") == expected:
        return source
    digits = [_arabic_digit(value) for value in expected.elements()]
    cursor = 0

    def replace_explicit(match: re.Match[str]) -> str:
        nonlocal cursor
        if cursor >= len(digits):
            return match.group(0)
        value = digits[cursor]
        cursor += 1
        return value

    repaired = _DIGIT_RE.sub(replace_explicit, _numeric_text(source))
    if numeric_facts(repaired, "ar") == expected:
        return repaired

    replacements: list[tuple[int, int, str]] = []
    for match in re.finditer(rf"[{_ARABIC_LETTER}]+", repaired):
        word = _normalize_ar_word(match.group(0))
        candidate = word[1:] if word.startswith("و") and len(word) > 1 else word
        if candidate in _AR_WORD_VALUES and cursor < len(digits):
            # Replace only a spelled numeric quantity, not an arbitrary occurrence of a
            # number word that is functioning as normal prose.
            following_match = re.match(r"\s*([\u0600-\u06ff]+)", repaired[match.end():])
            following = _normalize_ar_word(following_match.group(1)) if following_match else ""
            if following in _AR_QUANTITY_TERMS:
                replacements.append((match.start(), match.end(), digits[cursor]))
                cursor += 1
    for start, end, value in reversed(replacements):
        repaired = repaired[:start] + value + repaired[end:]
    if numeric_facts(repaired, "ar") == expected:
        return repaired
    if digits:
        repaired = f"{repaired.rstrip(' .،,؛:')} القيم الرقمية المطابقة هي {' و '.join(digits)}."
    return repaired.strip()
