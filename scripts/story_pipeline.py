from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
MIN_WORDS = 40
MAX_WORDS = 75
TARGET_MIN_WORDS = 55
TARGET_MAX_WORDS = 65
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))
CAR_MODE = os.getenv("CAR_MODE", "0") == "1"
COMMON_ENGLISH_IN_ARABIC = {"the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at", "of", "to", "for", "with", "from", "flame", "fire", "secret", "story", "city", "found", "people", "street"}
ARABIC_COMMON_MISTAKES = {"فالقائز": "الفائز", "القائز": "الفائز", "يسام من": "يعاني من", "سيارة دعم قائمة": "سيارة دعم"}


def words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", str(text or "")))


def _safe_text(value: object, limit: int) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if ch in "\n\r\t" or not unicodedata.category(ch).startswith("C"))
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 > limit:
        encoded = encoded[: limit * 2]
        if len(encoded) >= 2 and 0xD800 <= int.from_bytes(encoded[-2:], "little") <= 0xDBFF:
            encoded = encoded[:-2]
        text = encoded.decode("utf-16-le", errors="ignore").rstrip()
    return text


def _safe_tags(value: object) -> list[str]:
    if not isinstance(value, list): return []
    result, seen = [], set()
    for item in value[:15]:
        tag = _safe_text(item, 500).lstrip("#").strip()
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold()); result.append(tag)
    return result


def _arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip(); arabic = len(re.findall(r"[\u0600-\u06ff]", value)); letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value)); latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'\-]*\b", value)]
    return arabic >= 12 and arabic / max(1, letters) >= 0.60 and not any(w in COMMON_ENGLISH_IN_ARABIC for w in latin)


def arabic_proofread(text: str) -> str:
    value = _safe_text(text, 5000)
    for wrong, right in ARABIC_COMMON_MISTAKES.items(): value = value.replace(wrong, right)
    return re.sub(r"\s+", " ", value).strip()


def _visual_query_ok(scene: dict) -> bool:
    query = str(scene.get("pexels_query", "")).strip(); subject = str(scene.get("visual_subject", "")).strip(); abstract = {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"}
    return bool(subject and 3 <= len(query.split()) <= 9 and len(query) >= 12 and not all(w.casefold() in abstract for w in query.split()))


def validate_scene(scene: dict, index: int) -> None:
    required = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")
    if not isinstance(scene, dict) or not all(str(scene.get(key, "")).strip() for key in required): raise ValueError(f"scene {index} missing required fields")
    count = words(scene["text_en"])
    if not MIN_WORDS <= count <= MAX_WORDS: raise ValueError(f"scene {index} has invalid English word count: {count}; required {MIN_WORDS}-{MAX_WORDS}")
    if re.search(r"[\u0600-\u06ff]", scene["text_en"]): raise ValueError(f"scene {index} English contains Arabic")
    if not _arabic_quality_ok(scene["text_ar"]): raise ValueError(f"scene {index} Arabic translation quality check failed")
    if not _visual_query_ok(scene): raise ValueError(f"scene {index} visual query is too abstract or underspecified")


def generate() -> dict:
    raise RuntimeError("story_pipeline.generate implementation preserved in repository history; use current canonical implementation")
