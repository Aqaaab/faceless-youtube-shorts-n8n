#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")

PROMPT = """
Create ONE factual, high-retention YouTube Shorts story in English with accurate Modern Standard Arabic translations.
Return ONLY one JSON object. Exactly 5 scenes. Each scene must contain: text_en, text_ar, visual_subject, pexels_query.
Each English scene must contain 13-19 words. Total English narration must contain 75-95 words.
Scene 1 is a strong curiosity hook. No greeting, no generic introduction, no forced CTA.
Use only well-established, broadly verifiable facts. Do not invent numbers, dates, quotations, scientific claims, historical anecdotes, or medical/safety claims.
If a detail is uncertain, disputed, anecdotal, or difficult to verify from general knowledge, omit it.
Never use absolute wording such as always, never, the only, forever, immortal, never spoils, or never expires.
Avoid exact dates, ages, counts, percentages, rankings, and superlatives unless they are necessary and exceptionally well established; prefer cautious wording such as about, typically, can, often, or may.
Do not turn archaeological anecdotes into scientific certainty. In particular, do not state that 3,000-year-old honey was definitely safe or edible.
If discussing honey preservation, explain that mature honey's low water activity, acidity, and antimicrobial chemistry make it unusually resistant to microbial spoilage under suitable storage, but do not claim that honey is guaranteed safe forever or can never spoil.
Scenes 2-4 explain the fact. Scene 5 gives a memorable payoff.
text_ar must faithfully translate text_en into natural Modern Standard Arabic and preserve every factual qualifier. Never strengthen a cautious English statement into an absolute Arabic statement.
visual_subject must be the literal main physical subject that should visibly dominate the footage. It must be a concrete searchable noun or short noun phrase of 1-3 words, not an action, location, abstract concept, historical period, age, claim, mood, or generic category. Do not put temporal adjectives such as ancient, historical, modern, old, futuristic, or three-thousand-year-old into visual_subject unless they describe a visually obvious physical object type that is actually searchable.
pexels_query must be a direct search for the literal visual_subject. It MUST contain the key subject words from visual_subject and may add at most one concrete shot/context word. Never use unrelated words such as sun, sky, light, background, scene, nature, person, people, object, random, landscape unless that word is itself part of the literal subject.
Example: visual_subject="honey jar" -> pexels_query="honey jar" or "honey jar closeup". Do NOT use "ancient honey jar" as the visual subject.
Keep the same core subject across all scenes while varying the shot concept; when a concept cannot be shown reliably, prefer the concrete object/animal itself rather than a historical or abstract approximation.
script must equal all text_en joined with single spaces. narration must equal script.
subtitle_ar must equal all text_ar joined with single spaces.
Title must be English-only, <=85 characters, curiosity-driven, and end with #Shorts.
Description must be English-only and end with exactly 5 hashtags.
Tags must be 8-12 lowercase ASCII tokens using only letters, numbers, hyphens, or underscores.
Do not put Arabic into title, description, topic, category, query, or tags.
""".strip()

GENERIC_QUERY = {"nature", "background", "abstract", "object", "thing", "scene", "person", "people", "landscape", "random", "sun", "sky", "light", "ancient", "historical", "modern", "old", "futuristic"}
STOP_TAGS = {"the", "and", "of", "for", "a", "an", "to", "in", "with"}
FACTUAL_RED_FLAGS_EN = re.compile(r"\b(?:always|never|the only|only|forever|immortal|never spoils|never expires|lasts forever|completely safe|100%)\b", re.I)
FACTUAL_RED_FLAGS_AR = re.compile(r"(?:دائماً|دائمًا|أبداً|أبدًا|للأبد|إلى الأبد|الوحيد|الوحيدة|لا يفسد|لا يفسد أبداً|لا يفسد أبدًا|لا تنتهي صلاحيته|لا تنتهي صلاحيته أبداً|لا تنتهي صلاحيته أبدًا|آمن تماماً|آمن تمامًا|100٪)")
HONEY_ARCHAEOLOGY_CLAIM = re.compile(r"(?:honey|honeybee|honey bee).*(?:3000|3,000|thousand).*(?:edible|eat|eatable)|(?:3000|3,000|thousand).*(?:edible|eat|eatable).*(?:honey)", re.I)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", text))


def extract_json(text: str) -> dict:
    text = (text or "").strip().replace("\ufeff", "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    raw = text[start:end + 1]
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        from json_repair import repair_json
        value = repair_json(raw, return_objects=True)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    raise ValueError("invalid JSON")


def post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def openrouter(key: str) -> dict:
    payload = post(OPENROUTER_URL, {"model": OPENROUTER_MODEL, "messages": [{"role": "system", "content": "Return exactly one JSON object and nothing else."}, {"role": "user", "content": PROMPT}], "temperature": 0.1, "max_tokens": 5000, "response_format": {"type": "json_object"}}, {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n", "X-Title": "Faceless YouTube Shorts"})
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    return extract_json(content)


def gemini(key: str) -> dict:
    payload = post(GEMINI_URL, {"contents": [{"role": "user", "parts": [{"text": PROMPT}]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 5000, "responseMimeType": "application/json"}}, {"x-goog-api-key": key, "Content-Type": "application/json"})
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return extract_json("".join(x.get("text", "") for x in parts if isinstance(x, dict)))


def cloudflare(key: str, account: str) -> dict:
    payload = post(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CLOUDFLARE_MODEL}", {"messages": [{"role": "system", "content": "Return exactly one JSON object and nothing else."}, {"role": "user", "content": PROMPT}], "temperature": 0.1, "max_tokens": 5000}, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    result = payload.get("result") or {}
    content = result.get("response")
    return content if isinstance(content, dict) else extract_json(content or "")


def normalize_tags(data: dict, scenes: list[dict]) -> list[str]:
    raw = data.get("tags") if isinstance(data.get("tags"), list) else []
    tags: list[str] = []
    for item in raw:
        token = str(item).strip().lower().replace("#", "")
        token = re.sub(r"[^a-z0-9_-]+", "-", token).strip("-_")
        if token and token not in tags:
            tags.append(token)
    seed = " ".join(str(data.get(k, "")) for k in ("topic", "query", "category"))
    seed += " " + " ".join(str(s.get("visual_subject", "")) for s in scenes)
    for token in re.findall(r"[a-z0-9]+", seed.lower()):
        if token not in STOP_TAGS and token not in tags:
            tags.append(token)
    for token in ("science", "facts", "nature", "learning", "animals", "shorts"):
        if token not in tags:
            tags.append(token)
    return tags[:12]


def grounded_query(visual_subject: str, requested_query: str) -> str:
    subject = re.sub(r"[^A-Za-z0-9 -]+", " ", visual_subject).strip().lower()
    requested = re.sub(r"[^A-Za-z0-9 -]+", " ", requested_query).strip().lower()
    subject_words = [w for w in subject.split() if w not in GENERIC_QUERY]
    if not subject_words:
        raise ValueError("visual_subject must contain a concrete subject")
    req_words = [w for w in requested.split() if w not in GENERIC_QUERY and w not in subject_words]
    query_words = subject_words[:3]
    if len(query_words) == 1 and req_words:
        query_words.append(req_words[0])
    return " ".join(query_words[:3])


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("provider response must be an object")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("exactly 5 scenes required")

    english: list[str] = []
    arabic: list[str] = []
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {i} invalid")
        for key in ("text_en", "text_ar", "visual_subject", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"scene {i} missing {key}")
        en = scene["text_en"].strip()
        ar = scene["text_ar"].strip()
        visual = scene["visual_subject"].strip()
        requested_query = scene["pexels_query"].strip()
        wc = word_count(en)
        if not 13 <= wc <= 19:
            raise ValueError(f"scene {i} has {wc} words; expected 13-19")
        visual_words = visual.lower().split()
        if not 1 <= len(visual_words) <= 3 or any(q in GENERIC_QUERY for q in visual_words):
            raise ValueError(f"scene {i} has weak visual subject")
        scene["pexels_query"] = grounded_query(visual, requested_query)
        query_words = scene["pexels_query"].split()
        if not 1 <= len(query_words) <= 3 or any(q in GENERIC_QUERY for q in query_words):
            raise ValueError(f"scene {i} has weak visual query")
        if re.search(r"[\u0600-\u06ff]", en):
            raise ValueError(f"scene {i} English contains Arabic")
        if not re.search(r"[\u0600-\u06ff]", ar):
            raise ValueError(f"scene {i} Arabic translation missing")
        if FACTUAL_RED_FLAGS_EN.search(en):
            raise ValueError(f"scene {i} contains an unsupported absolute claim")
        if FACTUAL_RED_FLAGS_AR.search(ar):
            raise ValueError(f"scene {i} Arabic contains an unsupported absolute claim")
        if HONEY_ARCHAEOLOGY_CLAIM.search(en):
            raise ValueError(f"scene {i} contains an unverified ancient-honey edibility claim")
        english.append(en)
        arabic.append(ar)

    script = " ".join(english)
    total = word_count(script)
    if not 75 <= total <= 95:
        raise ValueError(f"narration has {total} words; expected 75-95")

    title = str(data.get("title", "")).strip()
    if not title or len(title) > 85 or not title.endswith("#Shorts") or re.search(r"[\u0600-\u06ff]", title):
        topic = str(data.get("topic") or scenes[0]["visual_subject"]).strip().title()
        title = f"{topic} — The Fact You Didn't Expect #Shorts"
        if len(title) > 85:
            title = "The Fact You Didn't Expect About This Animal #Shorts"

    description = str(data.get("description", "")).strip()
    description = re.sub(r"[\u0600-\u06ff]", "", description).strip()
    if len(re.findall(r"#[A-Za-z0-9_-]+", description)) != 5:
        description = "A surprising science fact explained in seconds. Watch the mechanism behind this remarkable subject. #Science #Facts #Nature #Animals #Shorts"

    data["script"] = script
    data["narration"] = script
    data["subtitle_ar"] = " ".join(arabic)
    data["hook"] = english[0]
    data["title"] = title
    data["description"] = description
    data.setdefault("topic", scenes[0]["visual_subject"].strip().title())
    data.setdefault("query", scenes[0]["pexels_query"].strip())
    data.setdefault("category", "Science")
    data["tags"] = normalize_tags(data, scenes)
    if not 8 <= len(data["tags"]) <= 12:
        raise ValueError("invalid tags")
    if any(not re.fullmatch(r"[a-z0-9_-]+", tag) for tag in data["tags"]):
        raise ValueError("invalid tag characters")
    if re.search(r"\b(follow for more|subscribe for more|like and subscribe)\b", script, re.I):
        raise ValueError("forced CTA in narration")
    return data


def fallback() -> dict:
    scenes = [
        {"text_en": "A honeybee can tell its colony exactly where food is hidden without making a sound.", "text_ar": "تستطيع نحلة العسل أن تخبر مستعمرتها بمكان الطعام المختبئ بدقة من دون إصدار صوت.", "visual_subject": "honeybee", "pexels_query": "honeybee"},
        {"text_en": "A worker bee performs a waggle dance, using movement to communicate the direction of a food source.", "text_ar": "تؤدي النحلة العاملة رقصة اهتزاز، مستخدمة الحركة للتواصل بشأن اتجاه مصدر الطعام.", "visual_subject": "honeybee", "pexels_query": "honeybee"},
        {"text_en": "The dance angle relates to the sun, helping other bees understand which direction they should fly.", "text_ar": "ترتبط زاوية الرقصة بالشمس، ما يساعد النحل الآخر على فهم الاتجاه الذي ينبغي أن يطير نحوه.", "visual_subject": "honeybee", "pexels_query": "honeybee"},
        {"text_en": "The dance duration and repetition also provide information about the approximate distance to the food.", "text_ar": "كما توفر مدة الرقصة وتكرارها معلومات عن المسافة التقريبية للوصول إلى الطعام.", "visual_subject": "beehive", "pexels_query": "beehive"},
        {"text_en": "One tiny insect can therefore guide an entire colony toward useful resources through movement alone.", "text_ar": "وهكذا تستطيع حشرة صغيرة توجيه مستعمرة كاملة نحو موارد مفيدة من خلال الحركة وحدها.", "visual_subject": "honeybee flowers", "pexels_query": "honeybee flowers"},
    ]
    return validate({"title": "How Honeybees Give Directions Without Words #Shorts", "description": "Honeybees communicate food directions through a remarkable waggle dance. Their movements help workers navigate toward useful resources. #Honeybees #Bees #Science #Nature #Shorts", "tags": ["honeybees", "bees", "waggle-dance", "science", "nature", "biology", "insects", "communication"], "query": "honeybee", "topic": "Honeybee communication", "category": "Science", "scenes": scenes, "provider": "deterministic-fallback"})


def main() -> None:
    providers = []
    errors = []
    if os.environ.get("OPENROUTER_API_KEY", "").strip(): providers.append(("OpenRouter", lambda: openrouter(os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GEMINI_API_KEY", "").strip(): providers.append(("Gemini", lambda: gemini(os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip(): providers.append(("Cloudflare", lambda: cloudflare(os.environ["CLOUDFLARE_API_TOKEN"].strip(), os.environ["CLOUDFLARE_ACCOUNT_ID"].strip())))

    data = None
    for name, fn in providers:
        print(f"AI provider={name} attempt=1/1", flush=True)
        try:
            data = validate(fn())
            data["provider"] = name
            print(f"AI provider={name} succeeded", flush=True)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            errors.append(f"{name} HTTP {exc.code}: {detail}")
            print(errors[-1], flush=True)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(errors[-1], flush=True)

    if data is None:
        print("All AI providers unavailable; using deterministic fallback.", flush=True)
        if errors: print("Provider summary: " + " | ".join(errors), flush=True)
        data = fallback()

    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"job.json written: {output}; provider={data.get('provider')}; topic={data.get('topic')}; words={word_count(data['script'])}", flush=True)


if __name__ == "__main__":
    main()
