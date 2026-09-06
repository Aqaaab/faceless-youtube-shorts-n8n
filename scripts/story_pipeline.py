from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
EXPECTED_SCENES = int(CFG["production"]["long_scene_count"])
MIN_WORDS = 40
MAX_WORDS = 75
TARGET_MIN_WORDS = 55
TARGET_MAX_WORDS = 65
REPAIR_RETRIES = max(1, int(os.getenv("STORY_REPAIR_RETRIES", "3")))
CAR_MODE = os.getenv("CAR_MODE", "0") == "1"
COMMON_ENGLISH_IN_ARABIC = {
    "the", "and", "or", "but", "this", "that", "was", "were", "is", "are", "in", "on", "at", "of", "to", "for", "with", "from",
    "flame", "fire", "secret", "story", "city", "found", "people", "street",
}
ARABIC_COMMON_MISTAKES = {
    "فالقائز": "الفائز",
    "القائز": "الفائز",
    "يسام من": "يعاني من",
    "سيارة دعم قائمة": "سيارة دعم",
}
AUTOMOTIVE_TERMS = {
    "car", "cars", "automotive", "vehicle", "engine", "turbo", "brake", "brakes", "wheel", "wheels", "tire", "tires",
    "battery", "hybrid", "electric", "ev", "transmission", "gearbox", "suspension", "steering", "fuel", "diesel", "petrol",
    "chassis", "aerodynamic", "horsepower", "torque", "rpm", "engine", "sensor", "injector", "radiator", "cooling", "exhaust",
}
FORBIDDEN_NON_AUTOMOTIVE = {"history", "politics", "war", "colonial", "tea", "ship", "ships", "mystery", "parliament", "revolution"}


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
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value[:15]:
        tag = _safe_text(item, 500).lstrip("#").strip()
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            result.append(tag)
    return result


def _arabic_quality_ok(text: str) -> bool:
    value = str(text or "").strip()
    arabic = len(re.findall(r"[\u0600-\u06ff]", value))
    letters = len(re.findall(r"[A-Za-z\u0600-\u06ff]", value))
    latin = [w.casefold() for w in re.findall(r"\b[A-Za-z][A-Za-z'\-]*\b", value)]
    return arabic >= 12 and arabic / max(1, letters) >= 0.60 and not any(w in COMMON_ENGLISH_IN_ARABIC for w in latin)


def arabic_proofread(text: str) -> str:
    value = _safe_text(text, 5000)
    for wrong, right in ARABIC_COMMON_MISTAKES.items():
        value = value.replace(wrong, right)
    return re.sub(r"\s+", " ", value).strip()


def _visual_query_ok(scene: dict) -> bool:
    query = str(scene.get("pexels_query", "")).strip()
    subject = str(scene.get("visual_subject", "")).strip()
    query_words = query.split()
    if not subject or not 3 <= len(query_words) <= 9 or len(query) < 12:
        return False
    if all(word.casefold() in {"history", "mystery", "story", "event", "fact", "past", "interesting", "concept"} for word in query_words):
        return False
    if CAR_MODE:
        lowered = " ".join((subject, query)).casefold()
        if any(term in lowered.split() for term in FORBIDDEN_NON_AUTOMOTIVE):
            return False
        if not any(term in lowered.split() for term in AUTOMOTIVE_TERMS):
            return False
    return True


def _car_text_ok(text: str) -> bool:
    if not CAR_MODE:
        return True
    lowered = str(text or "").casefold()
    if any(term in lowered.split() for term in FORBIDDEN_NON_AUTOMOTIVE):
        return False
    return any(term in lowered.split() for term in AUTOMOTIVE_TERMS)


def validate_scene(scene: dict, index: int) -> None:
    required = ("text_en", "text_ar", "visual_subject", "pexels_query", "beat")
    if not isinstance(scene, dict) or not all(str(scene.get(key, "")).strip() for key in required):
        raise ValueError(f"scene {index} missing required fields")
    count = words(scene["text_en"])
    if not MIN_WORDS <= count <= MAX_WORDS:
        raise ValueError(f"scene {index} has invalid English word count: {count}; required {MIN_WORDS}-{MAX_WORDS}")
    if re.search(r"[\u0600-\u06ff]", scene["text_en"]):
        raise ValueError(f"scene {index} English contains Arabic")
    if not _arabic_quality_ok(scene["text_ar"]):
        raise ValueError(f"scene {index} Arabic translation quality check failed")
    if not _visual_query_ok(scene):
        raise ValueError(f"scene {index} visual query is too abstract or underspecified")
    if not _car_text_ok(" ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject", "pexels_query"))):
        raise ValueError(f"scene {index} is outside the automotive niche")


def validate_story(story: dict) -> None:
    scenes = story.get("scenes") if isinstance(story, dict) else None
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise ValueError(f"story must contain exactly {EXPECTED_SCENES} scenes")
    title = str(story.get("title", "")).strip()
    description = str(story.get("description", "")).strip()
    tags = story.get("tags")
    if not title or not description or not isinstance(tags, list) or not tags:
        raise ValueError("story metadata is incomplete")
    if CAR_MODE and not _car_text_ok(f"{title} {description} {' '.join(map(str, tags))}"):
        raise ValueError("story metadata is outside the automotive niche")
    for index, scene in enumerate(scenes, 1):
        validate_scene(scene, index)


def _story_prompt(topic: str) -> str:
    topic = str(topic or "").strip()
    payload: dict[str, object] = {"task": "long_story", "topic": topic}
    if CAR_MODE:
        reference = ""
        cfg_path = ROOT / "config" / "car_encyclopedia.json"
        if cfg_path.is_file():
            try:
                reference = json.dumps(json.loads(cfg_path.read_text(encoding="utf-8")), ensure_ascii=False)
            except (OSError, json.JSONDecodeError):
                reference = ""
        payload["niche"] = "cars and automotive technology only"
        payload["reference"] = reference
        payload["hard_rules"] = [
            "Every title, description, tag, scene narration, visual subject and Pexels query must be automotive.",
            "No history, politics, war, colonial stories, tea, ships, generic mysteries, or unrelated subjects.",
            "Every visual must be directly searchable as automotive footage on Pexels.",
            "Explain one concrete automotive mechanism, feature, failure mode, engineering principle, or technology.",
            "Avoid unsupported exact specifications; use technically accurate qualitative explanations when uncertain.",
            "Use explicit digits for factual automotive specifications and preserve exact values in Arabic when they are stated.",
        ]
    payload["contract"] = {
        "scenes": EXPECTED_SCENES,
        "scene_words": f"{TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} target; {MIN_WORDS}-{MAX_WORDS} hard limit",
        "language": "English narration with faithful publication-quality Modern Standard Arabic",
        "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
        "visual_rule": "pexels_query must be 3-9 concrete searchable words",
        "arabic_rule": "No ordinary English words in Arabic subtitles; proofread every scene",
    }
    payload["output"] = "JSON only with title, description, tags and scenes"
    return json.dumps(payload, ensure_ascii=False)


def repair_story(story: dict, topic: str) -> dict:
    contract: dict[str, object] = {
        "exact_scene_count": EXPECTED_SCENES,
        "scene_words": f"{TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} target; {MIN_WORDS}-{MAX_WORDS} hard limit",
        "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
    }
    if CAR_MODE:
        contract.update({
            "niche": "cars and automotive technology only",
            "forbidden": "history, politics, war, colonial, tea, ships, generic mystery, unrelated topics",
            "visuals": "Every pexels_query must be concrete automotive",
        })
    payload = {
        "task": "repair_story_structure",
        "topic": topic,
        "story": story,
        "contract": contract,
        "instruction": f"Return complete JSON with exactly {EXPECTED_SCENES} scenes. Every English scene must be complete and accompanied by publication-quality Modern Standard Arabic subtitles.",
    }
    result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
    if not isinstance(result, dict):
        raise ValueError("story structure repair returned invalid JSON")
    return result


def _local_scene_fallback(scene: dict, index: int, topic: str) -> dict:
    fallback = dict(scene) if isinstance(scene, dict) else {}
    vehicle = _safe_text(os.getenv("CAR_VEHICLE", ""), 100)
    if CAR_MODE:
        subject_core = vehicle or "modern performance car"
        default_text = (
            f"This automotive scene explains how {subject_core} manages an important vehicle system in practical terms. "
            "The key mechanism affects vehicle behavior, efficiency, reliability, or control. "
            "Understanding the component helps explain why the system responds the way drivers observe."
        )
        default_visual = f"{subject_core} engine bay"
        default_query = f"{subject_core} engine performance"
        default_ar = (
            "هذا المشهد يشرح كيفية عمل نظام مهم في السيارة بصورة عملية، ويوضح الآلية الأساسية وتأثيرها في الأداء والكفاءة والاعتمادية. "
            "كما يبيّن دور المكوّن في استجابة المركبة وما يمكن أن يلاحظه السائق أثناء التشغيل."
        )
    else:
        default_text = (
            f"This scene explains an important part of {topic or 'the subject'}. "
            "It connects the main idea to the evidence and shows why the detail matters. "
            "The explanation keeps the sequence clear and gives the viewer a useful takeaway."
        )
        default_visual = "technical documentary detail"
        default_query = "technical documentary detail footage"
        default_ar = (
            "هذا المشهد يشرح جزءاً مهماً من الموضوع بصورة واضحة، ويربط الفكرة الأساسية بالأدلة ويبيّن سبب أهميتها. "
            "كما يحافظ على تسلسل منطقي يمنح المشاهد خلاصة مفيدة ومفهومة."
        )

    text = _safe_text(fallback.get("text_en"), 900)
    if words(text) < MIN_WORDS or re.search(r"[\u0600-\u06ff]", text):
        text = default_text
    tokenized = re.findall(r"\b[A-Za-z][A-Za-z0-9'\-]*\b", text)
    if len(tokenized) > MAX_WORDS:
        text = " ".join(tokenized[:MAX_WORDS]) + "."
    fallback["text_en"] = text

    arabic = arabic_proofread(fallback.get("text_ar", ""))
    fallback["text_ar"] = arabic if _arabic_quality_ok(arabic) else default_ar

    candidate_subject = str(fallback.get("visual_subject", "")).strip()
    candidate_query = str(fallback.get("pexels_query", "")).strip()
    candidate = {
        "visual_subject": candidate_subject or default_visual,
        "pexels_query": candidate_query or default_query,
        "text_en": fallback["text_en"],
    }
    if not _visual_query_ok(candidate):
        fallback["visual_subject"] = default_visual
        fallback["pexels_query"] = default_query
    else:
        fallback["visual_subject"] = candidate_subject
        fallback["pexels_query"] = candidate_query

    fallback["beat"] = "hook" if index in (1, 7, 13, 19) else (str(fallback.get("beat", "")).strip() or "development")
    return fallback


def repair_scene(scene: dict, index: int, topic: str, previous_error: str = "") -> dict:
    current = scene if isinstance(scene, dict) else {}
    last_error = previous_error or "initial validation failure"
    for _ in range(REPAIR_RETRIES):
        contract: dict[str, object] = {
            "text_en_words": f"{TARGET_MIN_WORDS}-{TARGET_MAX_WORDS} target; {MIN_WORDS}-{MAX_WORDS} hard limit",
            "text_en_language": "English only",
            "text_ar_language": "publication-quality Modern Standard Arabic",
            "required_fields": ["text_en", "text_ar", "visual_subject", "pexels_query", "beat"],
        }
        if CAR_MODE:
            contract.update({
                "niche": "cars and automotive technology only",
                "visual_rule": "concrete automotive Pexels query only",
                "forbidden": "history, politics, war, tea, ships, unrelated topics",
            })
        payload = {
            "task": "repair_scene",
            "topic": topic,
            "scene_number": index,
            "scene": current,
            "validation_error": last_error,
            "contract": contract,
            "instruction": "Return this scene only as JSON with the required fields.",
        }
        try:
            result = extract_json(call(json.dumps(payload, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
        except Exception as exc:
            last_error = f"scene {index} repair request failed: {exc}"
            continue
        if isinstance(result, dict) and isinstance(result.get("scenes"), list):
            result = result["scenes"][0] if result["scenes"] else {}
        if not isinstance(result, dict):
            last_error = f"scene {index} repair returned invalid JSON"
            continue
        try:
            validate_scene(result, index)
            return result
        except ValueError as exc:
            current, last_error = result, str(exc)
    fallback = _local_scene_fallback(current, index, topic)
    validate_scene(fallback, index)
    print(f"SCENE_REPAIR_FALLBACK scene={index} reason={last_error}")
    return fallback


def normalize_metadata(story: dict, topic: str) -> dict:
    title = _safe_text(story.get("title"), 100)
    description = re.sub(r"(?:^|\s)#[\w-]+", "", _safe_text(story.get("description"), 4700)).strip()
    tags = _safe_tags(story.get("tags", []))
    if CAR_MODE:
        story["title"] = title or _safe_text(topic, 100) or "Automotive Engineering Explained"
        story["description"] = _safe_text(
            (description or f"Automotive engineering explained: {story['title']}.") + "\n\n#Cars #Automotive #CarTechnology #CarFacts",
            5000,
        )
        defaults = ["cars", "automotive", "car technology", "car engineering", "car facts"]
    else:
        story["title"] = title or _safe_text(topic, 100) or "The Hidden Story Behind a Surprising Event"
        story["description"] = _safe_text(
            (description or f"Discover the hidden story behind {story['title']}.") + "\n\n#History #Mystery #HistoryFacts",
            5000,
        )
        defaults = ["facts", "explainer", "story"]
    story["tags"] = tags or defaults
    return story


def normalize_story(story: dict, topic: str) -> dict:
    for attempt in range(REPAIR_RETRIES + 1):
        if isinstance(story, dict) and isinstance(story.get("scenes"), list) and len(story["scenes"]) == EXPECTED_SCENES:
            break
        if attempt >= REPAIR_RETRIES:
            raise ValueError(f"story must contain exactly {EXPECTED_SCENES} scenes")
        story = repair_story(story if isinstance(story, dict) else {}, topic)
    story = normalize_metadata(story, topic)
    scenes = story["scenes"]
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            scene = {}
            scenes[index - 1] = scene
        scene["text_ar"] = arabic_proofread(scene.get("text_ar", ""))
        try:
            validate_scene(scene, index)
        except ValueError as exc:
            print(f"SCENE_REPAIR scene={index} reason={exc}")
            repaired = repair_scene(scene, index, topic, str(exc))
            repaired["text_ar"] = arabic_proofread(repaired.get("text_ar", ""))
            scenes[index - 1] = repaired
    validate_story(story)
    return story


def generate() -> dict:
    run = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
    run.mkdir(parents=True, exist_ok=True)
    default_topic = "Why modern cars manage turbo lag" if CAR_MODE else "The hidden story behind a surprising event"
    topic = os.getenv("VIDEO_TOPIC", "").strip() or default_topic
    raw = extract_json(call(_story_prompt(topic), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story")))
    story = normalize_story(raw, topic)
    path = run / "long_story.json"
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STORY_GENERATION=PASS scenes={len(story['scenes'])} niche={'cars' if CAR_MODE else 'general'}")
    return story


def main() -> dict:
    return generate()


if __name__ == "__main__":
    main()
