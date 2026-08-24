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
Create ONE factual, high-retention YouTube Shorts story in English with accurate Modern Standard Arabic subtitles.
Return ONLY JSON. Exactly 5 scenes. Each scene fields: text_en,text_ar,visual_subject,pexels_query.
Total narration must be 75-95 English words; each scene must be 12-21 English words.
Scene 1 must be a strong curiosity hook: no greeting, no generic introduction, no 'today', no 'did you know'.
Use a concrete verifiable fact and do not invent numbers, dates, quotations, or scientific claims.
Scenes 2-4 develop and explain the fact. Scene 5 gives a memorable payoff and must NOT contain a forced CTA.
Every Arabic scene must faithfully translate its English scene. Never mistranslate named animals or scientific terms.
visual_subject must name the literal main subject visible in the footage. pexels_query must be 1-3 concrete English words naming that subject; never generic words such as nature, background, person, landscape, object, random.
Use visually varied scenes while keeping the same factual subject.
script must equal all text_en joined with single spaces. subtitle_ar must equal all text_ar joined with single spaces.
Title <=85 characters, English only, curiosity-driven, ends with #Shorts.
Description: 2 concise English sentences followed by exactly 5 hashtags. Tags: 8-12 lowercase English tokens. No emojis. Metadata must contain no Arabic.
""".strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", text))


def extract_json(text: str) -> dict:
    text = (text or "").strip().replace("\ufeff", "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    raw = text[start:end + 1]
    try:
        return json.loads(raw)
    except Exception as first:
        try:
            from json_repair import repair_json
            obj = repair_json(raw, return_objects=True)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        raise ValueError("invalid JSON") from first


def post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def openrouter(key: str) -> dict:
    payload = post(
        OPENROUTER_URL,
        {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": PROMPT},
            ],
            "temperature": 0.15,
            "max_tokens": 4200,
            "response_format": {"type": "json_object"},
        },
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Faceless YouTube Shorts",
        },
    )
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if not content:
        raise ValueError("OpenRouter returned empty content")
    return extract_json(content)


def gemini(key: str) -> dict:
    payload = post(
        GEMINI_URL,
        {
            "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
            "generationConfig": {"temperature": 0.15, "maxOutputTokens": 4200, "responseMimeType": "application/json"},
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return extract_json("".join(x.get("text", "") for x in parts if isinstance(x, dict)))


def cloudflare(key: str, account: str) -> dict:
    payload = post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CLOUDFLARE_MODEL}",
        {
            "messages": [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": PROMPT},
            ],
            "temperature": 0.15,
            "max_tokens": 4200,
        },
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    result = payload.get("result") or {}
    content = result.get("response")
    return content if isinstance(content, dict) else extract_json(content or "")


def derive_tags(data: dict, scenes: list[dict]) -> list[str]:
    existing = data.get("tags")
    if isinstance(existing, list):
        tags = [str(x).lower().strip() for x in existing if str(x).strip()]
    else:
        tags = []
    seed_text = " ".join([
        str(data.get("topic", "")),
        str(data.get("query", "")),
        str(data.get("category", "")),
        str(scenes[0].get("visual_subject", "")),
    ])
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9-]*", seed_text.lower())
    for token in candidates:
        if token not in tags and token not in {"the", "and", "of", "for", "a"}:
            tags.append(token)
    for token in ("science", "facts", "nature", "learning", "animals", "shorts"):
        if token not in tags:
            tags.append(token)
    return tags[:12]


def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("provider response must be an object")

    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 5:
        raise ValueError("exactly 5 scenes required")

    english = []
    arabic = []
    generic = {"nature", "background", "abstract", "person", "people", "thing", "object", "landscape", "scene", "random"}
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {i} invalid")
        for key in ("text_en", "text_ar", "visual_subject", "pexels_query"):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f"scene {i} missing {key}")
        wc = word_count(scene["text_en"])
        if not 12 <= wc <= 21:
            raise ValueError(f"scene {i} has {wc} words; expected 12-21")
        query_words = scene["pexels_query"].lower().split()
        if not 1 <= len(query_words) <= 3 or any(x in generic for x in query_words):
            raise ValueError(f"scene {i} has weak visual query")
        if re.search(r"[\u0600-\u06ff]", scene["text_en"]):
            raise ValueError(f"scene {i} English contains Arabic")
        if not re.search(r"[\u0600-\u06ff]", scene["text_ar"]):
            raise ValueError(f"scene {i} Arabic translation missing")
        english.append(scene["text_en"].strip())
        arabic.append(scene["text_ar"].strip())

    script = " ".join(english)
    subtitle_ar = " ".join(arabic)
    data["script"] = script
    data["narration"] = script
    data["subtitle_ar"] = subtitle_ar
    data["hook"] = english[0]

    # These values can be reconstructed deterministically from the scenes when an
    # AI provider omits them. Required production semantics must never depend on
    # optional metadata fields being returned by a provider.
    data.setdefault("query", scenes[0]["pexels_query"])
    data.setdefault("topic", scenes[0]["visual_subject"].strip().title())
    data.setdefault("category", "Science")
    data.setdefault("title", f"{data['topic']} — The Fact You Didn't Expect #Shorts")
    data.setdefault("description", f"A surprising fact about {data['topic']}. Watch how it works in a few seconds. #Science #Nature #Facts #Shorts #Learning")
    data["tags"] = derive_tags(data, scenes)

    total = word_count(script)
    if not 75 <= total <= 95:
        raise ValueError(f"narration has {total} words; expected 75-95")
    if len(str(data["title"])) > 85 or not str(data["title"]).endswith("#Shorts"):
        raise ValueError("invalid title")
    if re.search(r"[\u0600-\u06ff]", "".join(str(data[k]) for k in ("title", "description", "query", "topic", "category"))):
        raise ValueError("metadata contains Arabic")
    if not 8 <= len(data["tags"]) <= 12:
        raise ValueError("invalid tags")
    if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in data["tags"]):
        raise ValueError("invalid tag characters")
    if re.search(r"\b(follow for more|subscribe for more|like and subscribe)\b", script, re.I):
        raise ValueError("forced CTA in narration")
    return data


def fallback() -> dict:
    scenes = [
        {"text_en": "A honeybee can tell its colony where food is hiding without saying a word.", "text_ar": "تستطيع نحلة العسل إخبار مستعمرتها بمكان الطعام المختبئ من دون أن تنطق بكلمة.", "visual_subject": "honeybee", "pexels_query": "honeybee"},
        {"text_en": "A worker performs a waggle dance, and the direction of that movement points toward the food.", "text_ar": "تؤدي نحلة عاملة رقصة اهتزاز، ويشير اتجاه تلك الحركة نحو مصدر الطعام.", "visual_subject": "honeybee", "pexels_query": "honeybee"},
        {"text_en": "The angle is linked to the sun, helping other bees understand which way they should fly.", "text_ar": "ترتبط الزاوية بالشمس، ما يساعد النحل الآخر على فهم الاتجاه الذي ينبغي أن يطير نحوه.", "visual_subject": "beehive", "pexels_query": "beehive"},
        {"text_en": "The duration and repetition of the dance also carry information about how far the journey is.", "text_ar": "كما تنقل مدة الرقصة وتكرارها معلومات عن المسافة التي تستغرقها الرحلة.", "visual_subject": "beehive", "pexels_query": "beehive"},
        {"text_en": "One tiny insect can therefore guide an entire colony toward useful food sources through movement alone.", "text_ar": "وهكذا تستطيع حشرة صغيرة توجيه مستعمرة كاملة نحو مصادر الطعام المفيدة من خلال الحركة وحدها.", "visual_subject": "honeybees flowers", "pexels_query": "honeybees flowers"},
    ]
    data = {
        "title": "How Honeybees Give Directions Without Words #Shorts",
        "description": "Honeybees communicate food directions through a remarkable waggle dance. Their movements help workers navigate toward useful resources. #Honeybees #Bees #Science #Nature #AnimalFacts",
        "tags": ["honeybees", "bees", "waggle-dance", "science", "nature", "biology", "insects", "animalfacts", "communication"],
        "query": "honeybee",
        "topic": "Honeybee communication",
        "category": "Science",
        "scenes": scenes,
        "provider": "deterministic-fallback",
    }
    return validate(data)


def main() -> None:
    errors = []
    providers = []
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        providers.append(("OpenRouter", lambda: openrouter(os.environ["OPENROUTER_API_KEY"].strip())))
    if os.environ.get("GEMINI_API_KEY", "").strip():
        providers.append(("Gemini", lambda: gemini(os.environ["GEMINI_API_KEY"].strip())))
    if os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() and os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip():
        providers.append(("Cloudflare", lambda: cloudflare(os.environ["CLOUDFLARE_API_TOKEN"].strip(), os.environ["CLOUDFLARE_ACCOUNT_ID"].strip())))

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
            if exc.code == 429:
                print(f"{name} is rate-limited; no retry will be attempted.", flush=True)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(errors[-1], flush=True)

    if data is None:
        print("All AI providers unavailable; using deterministic fallback.", flush=True)
        if errors:
            print("Provider summary: " + " | ".join(errors), flush=True)
        data = fallback()

    output = RUN_DIR / "job.json"
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"job.json written: {output}; provider={data.get('provider')}; topic={data.get('topic')}; words={word_count(data['script'])}", flush=True)


if __name__ == "__main__":
    main()
