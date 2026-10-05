from __future__ import annotations
import re
from .parser import _story_shape

def _normalize_for_validation(data: dict) -> dict:
    normalized = _story_shape(data)
    scenes = normalized.get("scenes")
    if isinstance(scenes, list) and not str(normalized.get("narration", "")).strip():
        normalized["narration"] = " ".join(str(s.get("narration", "")).strip() for s in scenes if isinstance(s, dict)).strip()
    return normalized


def _callout_is_grounded(callout: str, narration: str) -> bool:
    numeric = re.findall(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*", callout)
    narration_numbers = set(re.findall(r"[0-9٠-٩]+(?:[.,٫٬][0-9٠-٩]+)*", narration))
    if any(token not in narration_numbers for token in numeric):
        return False
    words = {x for x in re.sub(r"[^\w\u0600-\u06ff]+", " ", callout.casefold()).split() if len(x) >= 3 and not x.isdigit()}
    nwords = {x for x in re.sub(r"[^\w\u0600-\u06ff]+", " ", narration.casefold()).split() if len(x) >= 3 and not x.isdigit()}
    return not words or bool(words & nwords)


def _short_title(seed: str, index: int) -> str:
    text = re.sub(r"\s+", " ", seed).strip(" ،.")
    if len(text) > 66:
        text = text[:66].rstrip()
    return (text + f" — المقطع {index}")[:80].strip()


def _ensure_description(data: dict, topic: str) -> None:
    description = re.sub(r"\s+", " ", str(data.get("description", "")).strip())
    if len(description) < 120:
        base = description or f"تحليل عربي منظم لموضوع {topic} ضمن حلقة سيارات مترابطة."
        description = base + " يركز على التصميم والتقنية والأداء وتجربة الاستخدام ضمن سرد واضح ومشاهد متتابعة، مع الالتزام بالمعلومات المتاحة وعدم اختلاق مواصفات غير مؤكدة."
    data["description"] = description[:2000]


