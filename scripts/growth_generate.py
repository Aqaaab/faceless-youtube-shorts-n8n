#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
RUN_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT = Path(os.environ.get("GROWTH_CONTEXT_FILE", "learning/context.txt"))
LEARNING = Path(os.environ.get("LEARNING_DIR", CONTEXT.parent))
TRENDS = LEARNING / "trends.json"

OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
GEM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
CF_MODEL = os.environ.get("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")

PROMPT = '''Create ONE original, accurate, high-retention YouTube Shorts "Did You Know?" story. Return ONLY JSON.
Required keys: hook, script, subtitle_ar, title, description, tags, query, topic, category, scenes.
scenes must contain exactly 5 objects with text_en, text_ar, pexels_query.
Rules: 55-95 English narration words total; 7-28 words per scene; scene 1 is a strong visual curiosity hook and may be a draft hook that will be editorially refined; strongest concrete payoff in scene 4; scene 5 ends with a natural curiosity bridge, not generic filler; one verifiable fact or tightly related fact cluster; no invented statistics/dates/quotes; do not invent technical capabilities, engineering ratings, survival claims, or precise durations; every scene moves the story forward; short spoken sentences; all Arabic is only in Arabic fields; title <=90 chars and ends with #Shorts; description has 2-3 English sentences then exactly 5 hashtags; 8-12 lowercase ASCII tags; each Pexels query is 2-4 simple, concrete English words that visibly match that scene; no generic queries such as "abstract", "background", or "nature" alone; no emojis.
Arabic rules: every text_ar value must be a natural Modern Standard Arabic translation of its matching text_en, preserving names and meaning; never invent Arabic-looking words; use standard Arabic transliteration for proper names; keep the Arabic concise enough for Shorts subtitles.
TREND RULE: Use the supplied current YouTube trend signals to choose or adapt the topic when a signal is relevant to a factual Did You Know story. Prefer a high-scoring/rising signal, but never copy a trending video's title, wording, script, or unique concept. If the signals are weak or unsuitable, choose a strong evergreen fact instead.
LEARNING CONTEXT contains both channel-performance observations and trend-discovery data. Use channel performance to improve structure and topic selection, and use trend signals to improve topical timeliness. Reuse successful structures, never copy wording, titles, or topics verbatim.'''

SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "script": {"type": "string"},
        "subtitle_ar": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "query": {"type": "string"},
        "topic": {"type": "string"},
        "category": {"type": "string"},
        "scenes": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "text_en": {"type": "string"},
                    "text_ar": {"type": "string"},
                    "pexels_query": {"type": "string"},
                },
                "required": ["text_en", "text_ar", "pexels_query"],
            },
        },
    },
    "required": ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"],
}


def wc(s: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", s, re.UNICODE))


def extract(s: str):
    s = (s or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s, flags=re.I)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object")
    return json.loads(re.sub(r",\s*([}\]])", r"\1", s[a:b + 1].replace("\ufeff", "")))


def post(url: str, body: dict, headers: dict) -> dict:
    r = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(r, timeout=120) as x:
        return json.loads(x.read().decode("utf-8", "replace"))


def openrouter(p: str, key: str):
    d = post(
        OR_URL,
        {
            "model": OR_MODEL,
            "messages": [
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": p},
            ],
            "temperature": 0.18,
            "max_tokens": 3500,
            "response_format": {"type": "json_object"},
        },
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Aqaaab/faceless-youtube-shorts-n8n",
            "X-Title": "Shorts Growth Engine",
        },
    )
    c = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return extract(c)


def gemini(p: str, key: str):
    d = post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEM_MODEL}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": p}]}],
            "generationConfig": {
                "maxOutputTokens": 3500,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        },
        {"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    parts = ((d.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return extract("".join(str(x.get("text", "")) for x in parts if isinstance(x, dict)))


def cloudflare(p: str, key: str, account: str):
    d = post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CF_MODEL}",
        {
            "messages": [
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": p},
            ],
            "temperature": 0.18,
            "max_tokens": 3500,
            "response_format": {"type": "json_schema", "json_schema": SCHEMA},
        },
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    r = (d.get("result") or {}).get("response")
    return r if isinstance(r, dict) else extract(str(r or ""))


def validate(d: dict, strict_hook: bool = True):
    need = ["hook", "script", "subtitle_ar", "title", "description", "tags", "query", "topic", "category", "scenes"]
    if any(k not in d for k in need) or not isinstance(d["scenes"], list) or len(d["scenes"]) != 5:
        raise ValueError("invalid job shape")

    texts = []
    for i, s in enumerate(d["scenes"], 1):
        if any(not isinstance(s.get(k), str) or not s[k].strip() for k in ("text_en", "text_ar", "pexels_query")):
            raise ValueError(f"scene {i} missing field")
        if not 7 <= wc(s["text_en"]) <= 28:
            raise ValueError(f"scene {i} word count")
        if re.search(r"[\u0600-\u06ff]", s["text_en"]):
            raise ValueError("Arabic in English scene")
        if not 2 <= len(s["pexels_query"].split()) <= 4:
            raise ValueError("bad Pexels query")
        if all(token in s["pexels_query"].lower().split() for token in ("abstract", "background")):
            raise ValueError("generic Pexels query")
        texts.append(s["text_en"].strip())

    script = " ".join(texts)
    if not 55 <= wc(script) <= 95:
        raise ValueError("total word count")
    d["script"] = script
    d["hook"] = texts[0]

    hook_lower = d["hook"].strip().lower()
    if strict_hook:
        if hook_lower.startswith("did you know"):
            raise ValueError("weak hook prefix")
        if not 10 <= wc(d["hook"]) <= 18:
            raise ValueError("hook length")

    if not re.search(r"[\u0600-\u06ff]", str(d["subtitle_ar"])):
        raise ValueError("Arabic subtitle missing")
    if len(str(d["title"]).strip()) > 90 or not str(d["title"]).strip().endswith("#Shorts"):
        raise ValueError("bad title")
    if not isinstance(d["tags"], list) or not 8 <= len(d["tags"]) <= 12:
        raise ValueError("bad tags")
    d["tags"] = [str(x).strip().lower() for x in d["tags"]]
    if any(not re.fullmatch(r"[a-z0-9_-]+", x) for x in d["tags"]):
        raise ValueError("bad tag chars")
    if re.search(r"[\u0600-\u06ff]", "".join(str(d[k]) for k in ("title", "description", "query", "topic", "category"))):
        raise ValueError("Arabic metadata")


def attempt(name: str, fn):
    err = None
    for n in range(1, 4):
        try:
            d = fn()
            validate(d, strict_hook=False)
            d["provider"] = name
            return d
        except urllib.error.HTTPError as e:
            err = f'{name} HTTP {e.code}: {e.read().decode("utf-8", "replace")[:600]}'
            print(err)
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:
            err = f"{name}: {e}"
            print(err)
        if n < 3:
            time.sleep(min(3 * n + random.random(), 8))
    return err


def refine_content(name: str, d: dict, fn):
    """One lightweight editorial pass for Arabic quality, hook strength and visual matching."""
    repair_prompt = '''Return ONLY JSON with exactly these keys: hook, subtitle_ar, scenes.
Keep every English scene text EXACTLY unchanged except scene 1, which may be rewritten as the stronger hook requested below.
Keep the same topic and factual meaning.
Tasks:
1) Rewrite hook into a natural 10-18 word English curiosity hook that does NOT start with "Did you know?".
2) Translate every scene's text_en into natural Modern Standard Arabic. Preserve meaning, proper names, quantities and units. Never invent Arabic-looking words or add facts.
3) Make subtitle_ar exactly the corrected Arabic translation of scene 1.
4) Rewrite every pexels_query into 2-4 concrete English words that visibly match that scene; use specific nouns/places/objects/actions, not generic words.
Return scenes with text_en unchanged for scenes 2-5, plus corrected text_ar and pexels_query.

CURRENT JOB:
''' + json.dumps(
        {
            "hook": d.get("hook", ""),
            "subtitle_ar": d.get("subtitle_ar", ""),
            "scenes": d.get("scenes", []),
        },
        ensure_ascii=False,
    )

    out = fn(repair_prompt)
    if not isinstance(out, dict) or not isinstance(out.get("scenes"), list) or len(out["scenes"]) != 5:
        raise ValueError("editorial refinement returned invalid JSON")

    english_before = [s["text_en"] for s in d["scenes"]]
    english_after = [s.get("text_en", "") for s in out["scenes"]]
    if english_before[1:] != english_after[1:]:
        raise ValueError("editorial refinement changed English narration")

    d["hook"] = str(out.get("hook", d["hook"])).strip()
    d["subtitle_ar"] = str(out.get("subtitle_ar", "")).strip()
    for i, s in enumerate(out["scenes"]):
        d["scenes"][i]["text_ar"] = str(s.get("text_ar", "")).strip()
        d["scenes"][i]["pexels_query"] = str(s.get("pexels_query", "")).strip()

    d["scenes"][0]["text_en"] = d["hook"]
    d["script"] = " ".join(s["text_en"].strip() for s in d["scenes"])
    d["subtitle_ar"] = d["scenes"][0]["text_ar"]
    validate(d, strict_hook=True)
    return d


def load_trends() -> str:
    if not TRENDS.is_file():
        return "No trend snapshot available; use evergreen facts."
    try:
        d = json.loads(TRENDS.read_text(encoding="utf-8"))
        rising = d.get("rising", []) if isinstance(d, dict) else []
        if not isinstance(rising, list) or not rising:
            return "No usable trend signals; use evergreen facts."
        lines = []
        for x in rising[:15]:
            if not isinstance(x, dict):
                continue
            lines.append(
                f"- keyword={x.get('keyword', '')} | score={x.get('score', 0)} | growth={x.get('growth', 0)} | appearances={x.get('appearances', 0)} | region={x.get('region', '')} | example={x.get('example_title', '')}"
            )
        return "\n".join(lines) or "No usable trend signals; use evergreen facts."
    except Exception as e:
        return f"No usable trend signals (read error: {e}); use evergreen facts."


def main():
    ctx = CONTEXT.read_text(encoding="utf-8", errors="replace")[-9000:] if CONTEXT.is_file() else "No historical data yet; optimize for curiosity, clarity, originality and visual match."
    trends = load_trends()
    p = PROMPT + "\n\nCURRENT TREND SIGNALS\n" + trends + "\n\nLEARNING CONTEXT\n" + ctx

    providers = []
    if os.getenv("OPENROUTER_API_KEY"):
        key = os.environ["OPENROUTER_API_KEY"]
        providers.append(("OpenRouter", lambda prompt, key=key: openrouter(prompt, key)))
    if os.getenv("GEMINI_API_KEY"):
        key = os.environ["GEMINI_API_KEY"]
        providers.append(("Gemini", lambda prompt, key=key: gemini(prompt, key)))
    if os.getenv("CLOUDFLARE_API_TOKEN") and os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        key = os.environ["CLOUDFLARE_API_TOKEN"]
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        providers.append(("Cloudflare Workers AI", lambda prompt, key=key, account=account: cloudflare(prompt, key, account)))

    if not providers:
        raise SystemExit("No AI provider configured")

    for name, fn in providers:
        r = attempt(name, lambda fn=fn: fn(p))
        if not isinstance(r, dict):
            continue

        try:
            r = refine_content(name, r, fn)
        except Exception as exc:
            print(f"{name} editorial refinement failed: {exc}")
            try:
                validate(r, strict_hook=True)
                print(f"{name} fallback draft passed strict validation.")
            except Exception as strict_exc:
                print(f"{name} fallback draft rejected: {strict_exc}")
                continue

        r.update(
            {
                "voice": os.getenv("VOICE", "af_bella"),
                "speed": float(os.getenv("SPEED", "1.0")),
                "lang": os.getenv("KOKORO_LANG", "en-us"),
                "music": os.getenv("MUSIC_ENABLED", "true").lower() == "true",
                "music_volume": float(os.getenv("MUSIC_VOLUME", "0.10")),
                "animation": os.getenv("ANIMATION_ENABLED", "true").lower() == "true",
                "ads": os.getenv("ADS_ENABLED", "false").lower() == "true",
                "narration": r["script"],
                "pexels_query": r["scenes"][0]["pexels_query"],
            }
        )
        (RUN_DIR / "job.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Growth-optimized job written")
        return

    raise SystemExit("All configured AI providers failed")


if __name__ == "__main__":
    main()
