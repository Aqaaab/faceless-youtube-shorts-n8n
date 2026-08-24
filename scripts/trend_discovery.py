#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEARNING = Path(os.environ.get("LEARNING_DIR", ROOT / "learning"))
LEARNING.mkdir(parents=True, exist_ok=True)
STATE = LEARNING / "trends.json"
CONTEXT = Path(os.environ.get("GROWTH_CONTEXT_FILE", LEARNING / "context.txt"))
API_KEY = os.environ.get("YOUTUBE_DATA_API_KEY", "").strip()
REGIONS = [x.strip().upper() for x in os.environ.get("TREND_REGIONS", "US,GB,CA,AU").split(",") if x.strip()]
MAX_RESULTS = max(5, min(50, int(os.environ.get("TREND_MAX_RESULTS", "25"))))

STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you", "are", "was",
    "what", "how", "why", "when", "where", "who", "will", "about", "into", "just", "have",
    "has", "new", "more", "than", "their", "they", "them", "his", "her", "its", "our",
    "today", "official", "video", "shorts", "short", "episode", "part", "full", "live",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "shorts-growth-engine/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def tokens(title: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", title.lower())
    return [w for w in words if w not in STOP and not w.isdigit()]


def fetch_region(region: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": str(MAX_RESULTS),
        "key": API_KEY,
    })
    data = get_json("https://www.googleapis.com/youtube/v3/videos?" + params)
    out = []
    for item in data.get("items", []):
        sn = item.get("snippet", {})
        st = item.get("statistics", {})
        out.append({
            "id": item.get("id", ""),
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "category_id": sn.get("categoryId", ""),
            "published_at": sn.get("publishedAt", ""),
            "views": int(st.get("viewCount", 0) or 0),
            "region": region,
        })
    return out


def main() -> int:
    if not API_KEY:
        print("Trend discovery skipped: YOUTUBE_DATA_API_KEY is not configured.")
        return 0

    previous = {}
    if STATE.is_file():
        try:
            previous = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    videos: list[dict] = []
    errors = []
    for region in REGIONS:
        try:
            videos.extend(fetch_region(region))
        except Exception as exc:
            errors.append(f"{region}: {exc}")

    if not videos and errors:
        raise RuntimeError("All trend requests failed: " + " | ".join(errors))

    counts = Counter()
    examples: dict[str, dict] = {}
    for v in videos:
        for word in set(tokens(v["title"])):
            counts[word] += 1
            examples.setdefault(word, v)

    old_counts = previous.get("keyword_counts", {}) if isinstance(previous, dict) else {}
    scored = []
    for word, count in counts.items():
        old = int(old_counts.get(word, 0) or 0)
        growth = count - old
        score = count * 10 + max(growth, 0) * 25
        scored.append((score, growth, count, word))
    scored.sort(reverse=True)

    rising = []
    for score, growth, count, word in scored[:40]:
        ex = examples[word]
        rising.append({"keyword": word, "score": score, "growth": growth, "appearances": count, "example_title": ex["title"], "region": ex["region"]})

    now = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps({
        "updated_at": now,
        "regions": REGIONS,
        "keyword_counts": dict(counts),
        "rising": rising,
        "sample_videos": videos[:100],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "TREND DISCOVERY (YouTube mostPopular snapshots; use only as trend signals, never as copy targets)",
        f"Updated: {now}",
        f"Regions: {', '.join(REGIONS)}",
        "Top rising signals:",
    ]
    for x in rising[:15]:
        lines.append(f"- {x['keyword']} | score={x['score']} growth={x['growth']} appearances={x['appearances']} | example={x['example_title']}")
    if errors:
        lines.append("Warnings: " + " | ".join(errors))

    existing = CONTEXT.read_text(encoding="utf-8", errors="replace") if CONTEXT.is_file() else ""
    marker = "\n\n--- TREND DISCOVERY ---\n"
    existing = existing.split(marker, 1)[0]
    CONTEXT.write_text((existing + marker + "\n".join(lines) + "\n")[-18000:], encoding="utf-8")
    print("Trend discovery complete. Top signals:")
    for x in rising[:10]:
        print(f"  {x['keyword']}: score={x['score']} growth={x['growth']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
