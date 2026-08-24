#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RUN_DIR = Path(os.environ.get("RUN_DIR", "data/run"))
JOB_FILE = RUN_DIR / "job.json"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

MIN_WORDS = 75
MAX_WORDS = 95
BANNED_CTA = re.compile(r"\b(follow for more|subscribe for more|like and subscribe|follow us)\b", re.I)
GENERIC = {"nature", "background", "abstract", "object", "thing", "scene", "person", "people", "landscape", "random"}


def words(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", text))


def pexels_has_result(query: str) -> bool:
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY is missing")
    params = urllib.parse.urlencode({"query": query, "orientation": "portrait", "size": "large", "per_page": "5"})
    req = urllib.request.Request(
        "https://api.pexels.com/videos/search?" + params,
        headers={"Authorization": PEXELS_API_KEY, "Accept": "application/json", "User-Agent": "faceless-youtube-shorts/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        return bool(data.get("videos"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        if exc.code in {401, 403}:
            raise RuntimeError(f"Pexels rejected the API request with HTTP {exc.code}. The GitHub secret exists, but the key is invalid, restricted, or blocked. Response: {body}") from exc
        if exc.code == 429:
            raise RuntimeError("Pexels rate limit (HTTP 429); retry the workflow later.") from exc
        if 500 <= exc.code < 600:
            raise RuntimeError(f"Pexels server error HTTP {exc.code}; retry the workflow.") from exc
        raise RuntimeError(f"Pexels HTTP {exc.code}: {body}") from exc


def main() -> int:
    if not JOB_FILE.is_file():
        print(f"ERROR: missing {JOB_FILE}", file=sys.stderr)
        return 1
    job = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    scenes = job.get("scenes") or []
    if len(scenes) != 5:
        print("ERROR: exactly 5 scenes are required", file=sys.stderr)
        return 1

    english = [str(s.get("text_en", "")).strip() for s in scenes]
    arabic = [str(s.get("text_ar", "")).strip() for s in scenes]
    script = " ".join(english)
    subtitle_ar = " ".join(arabic)
    count = words(script)
    if not MIN_WORDS <= count <= MAX_WORDS:
        print(f"ERROR: narration has {count} words; expected {MIN_WORDS}-{MAX_WORDS}", file=sys.stderr)
        return 1
    if BANNED_CTA.search(script):
        print("ERROR: forced CTA detected in narration", file=sys.stderr)
        return 1

    for i, scene in enumerate(scenes, 1):
        if not re.search(r"[\u0600-\u06ff]", arabic[i - 1]):
            print(f"ERROR: scene {i} Arabic translation is missing", file=sys.stderr)
            return 1
        if re.search(r"[\u0600-\u06ff]", english[i - 1]):
            print(f"ERROR: scene {i} English narration contains Arabic", file=sys.stderr)
            return 1
        query = " ".join(str(scene.get("pexels_query", "")).lower().split())
        if not query or not 1 <= len(query.split()) <= 3 or any(token in GENERIC for token in query.split()):
            print(f"ERROR: scene {i} has an invalid Pexels query: {query!r}", file=sys.stderr)
            return 1
        try:
            if not pexels_has_result(query):
                print(f"ERROR: Pexels returned no clips for scene {i}: {query!r}", file=sys.stderr)
                return 1
        except RuntimeError as exc:
            print(f"ERROR: scene {i} Pexels preflight failed: {exc}", file=sys.stderr)
            return 1

    job["script"] = script
    job["narration"] = script
    job["subtitle_ar"] = subtitle_ar
    job["quality_preflight"] = {"passed": True, "word_count": count, "pexels_checked": True, "arabic_only_overlay": True}
    JOB_FILE.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Preflight PASS: {count} narration words, 5 Pexels queries verified, Arabic-only overlay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
