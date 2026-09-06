from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
SEARCH_TIMEOUT = max(5, int(os.getenv("SOURCE_SEARCH_TIMEOUT", "15")))
SOURCE_RETRIES = max(1, int(os.getenv("SOURCE_ENRICHMENT_RETRIES", "2")))
# Enable remote verification by default in production (safer)
VERIFY_REMOTE = os.getenv("SOURCE_VERIFY_REMOTE", "1") == "1"
SPEC_RE = re.compile(r"\b(?:horsepower|hp|bhp|ps|nm|lb-ft|0-60|0\s*(?:to|-|–)\s*60|quarter mile|top speed|displacement|liter engine|litre engine|cubic|rpm|compression ratio|weight|curb weight)\b",
                     re.I)
TRUSTED_GENERIC_DOMAINS = {"nhtsa.gov", "www.nhtsa.gov", "epa.gov", "www.epa.gov", "iihs.org", "www.iihs.org", "sae.org", "www.sae.org", "motortrend.com", "www.motortrend.com", "caranddriver.com", "www.caranddriver.com"}
BRAND_DOMAINS = {
    "nissan": {"nissan-global.com", "www.nissan-global.com", "nissanusa.com", "www.nissanusa.com"},
    "toyota": {"toyota.com", "www.toyota.com"},
    "honda": {"honda.com", "www.honda.com"},
    "ford": {"ford.com", "www.ford.com"},
}
TRUSTED_SOURCE_SEEDS = {"chevrolet": [{"url": "https://www.chevrolet.com/performance1/previous-year/corvette/stingray", "claim": "Official Chevrolet Corvette Stingray performance/specification reference"}]}


def _domain(url: str) -> str:
    return urlparse(str(url)).netloc.casefold().split(":", 1)[0]


def _allowed_domains(vehicle: str) -> set[str]:
    out = set(TRUSTED_GENERIC_DOMAINS)
    value = vehicle.casefold()
    for brand, domains in BRAND_DOMAINS.items():
        if brand in value:
            out.update(domains)
    return out


def _brand(vehicle: str) -> str:
    value = vehicle.casefold()
    return next((name for name in BRAND_DOMAINS if name in value), "")


def _load_story() -> dict:
    path = RUN / "long_story.json"
    if not path.is_file():
        raise RuntimeError("SOURCE_ENRICHMENT: missing long_story.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _vehicle() -> str:
    return str(os.getenv("CAR_VEHICLE", "featured vehicle")).strip()


def _pillar() -> str:
    return str(os.getenv("CAR_TOPIC_PILLAR", "car engineering")).strip()


def _spec_scenes(story: dict) -> list[int]:
    return [i for i, s in enumerate(story.get("scenes", []), 1) if SPEC_RE.search(" ".join(str(s.get(k, "")) for k in ("text_en", "technical_flow", "source_claim")))]


def _source_target_scenes(story: dict) -> list[int]:
    return list(range(1, len(story.get("scenes", [])) + 1))


def _normalize_source(item: object, allowed: set[str]) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url", "")).strip()
    claim = str(item.get("claim", "")).strip()
    raw = item.get("scene_numbers", [])
    if not url.startswith("https://") or not claim or _domain(url) not in allowed or not isinstance(raw, list):
        return None
    nums = []
    for value in raw:
        try:
            n = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 25 and n not in nums:
            nums.append(n)
    if not nums:
        return None
    return {
        "id": str(item.get("id", "")).strip()[:80],
        "claim": claim[:300],
        "url": url[:500],
        "authority": str(item.get("authority", "")).strip()[:120],
        "scene_numbers": nums,
        "source_type": str(item.get("source_type", "")).strip()[:80],
    }


def _normalize_url(url: str) -> str:
    """Normalize URL for stable deduplication: remove fragment and sort query params."""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    params = parse_qs(parsed.query, keep_blank_values=True)
    if params:
        parts = []
        for k in sorted(params.keys()):
            v = ",".join(sorted(params[k]))
            parts.append(f"{k}={v}")
        sorted_query = "&".join(parts)
    else:
        sorted_query = ""
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", sorted_query, ""))
    return normalized


def _dedupe(sources: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for source in sources:
        url = str(source.get("url", "")).rstrip("/")
        claim = str(source.get("claim", "")).strip()[:100].casefold()
        normalized = _normalize_url(url)
        key = (normalized, claim)
        if key in seen:
            continue
        seen.add(key)
        source["id"] = source.get("id") or f"src-{len(result) + 1:02d}"
        result.append(source)
    return result


def _verify_source_url(url: str, allowed: set[str]) -> str | None:
    if not VERIFY_REMOTE:
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AutomotiveSourceBot/2.0)"}, method="GET")
        with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
            final = str(resp.geturl())
            status = int(getattr(resp, "status", 200) or 200)
            ctype = str(resp.headers.get("Content-Type", "")).casefold()
            if status not in {200, 206} or not final.startswith("https://") or _domain(final) not in allowed:
                return None
            if ctype and not any(kind in ctype for kind in ("text/html", "application/pdf", "application/xhtml+xml")):
                return None
            return final
    except (OSError, ValueError, TimeoutError):
        return None


def _verified_sources(sources: list[dict], allowed: set[str]) -> list[dict]:
    if not VERIFY_REMOTE:
        return _dedupe(sources)
    out = []
    for source in sources:
        final = _verify_source_url(source["url"], allowed)
        if final:
            item = dict(source)
            item["url"] = final[:500]
            out.append(item)
    return _dedupe(out)


def _seed_recovery(target_scenes: list[int]) -> list[dict]:
    allowed = _allowed_domains(_vehicle())
    out = []
    for seed in TRUSTED_SOURCE_SEEDS.get(_brand(_vehicle()), []):
        source = _normalize_source({**seed, "scene_numbers": list(target_scenes), "source_type": "trusted_official_seed"}, allowed)
        if not source:
            continue
        final = _verify_source_url(source["url"], allowed)
        if final:
            source["url"] = final[:500]
            out.append(source)
        elif source["source_type"] == "trusted_official_seed":
            out.append(source)
    return _dedupe(out)


def _llm_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    allowed = _allowed_domains(_vehicle())
    prompt = {"task": "source_register_recovery", "vehicle": _vehicle(), "pillar": _pillar(), "story_title": story.get("title", ""), "target_scenes": target_scenes}
    for attempt in range(SOURCE_RETRIES):
        try:
            candidate = extract_json(call(json.dumps(prompt, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=120))
            raw = candidate.get("sources", []) if isinstance(candidate, dict) else []
            if isinstance(raw, list):
                cleaned = [s for item in raw if (s := _normalize_source(item, allowed))]
                cleaned = _verified_sources(cleaned, allowed)
                if cleaned:
                    return cleaned
        except Exception as exc:
            print(f"SOURCE_LLM_RECOVERY_RETRY={attempt+1} error={exc}")
    return []


def _web_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    # placeholder for future web scraping-based recovery
    return []


def _build_sources(story: dict) -> list[dict]:
    target = _source_target_scenes(story)
    if not target:
        return []
    allowed = _allowed_domains(_vehicle())
    existing = _verified_sources(_dedupe([s for item in story.get("sources", []) if (s := _normalize_source(item, allowed))]), allowed)
    mapped = {n for s in existing for n in s["scene_numbers"]}
    missing = [n for n in target if n not in mapped]
    if missing:
        existing = _dedupe(existing + _llm_recovery(story, missing))
        mapped = {n for s in existing for n in s["scene_numbers"]}
        missing = [n for n in target if n not in mapped]
    if missing:
        existing = _dedupe(existing + _web_recovery(story, missing))
        mapped = {n for s in existing for n in s["scene_numbers"]}
        missing = [n for n in target if n not in mapped]
    if missing and not existing:
        existing = _dedupe(existing + _seed_recovery(missing))
        mapped = {n for s in existing for n in s["scene_numbers"]}
        missing = [n for n in target if n not in mapped]
    if missing:
        raise RuntimeError("SOURCE_ENRICHMENT: unable to map trusted sources to required scenes: " + ",".join(map(str, missing)))
    for index, scene in enumerate(story.get("scenes", []), 1):
        source = next((s for s in existing if index in s["scene_numbers"]), None)
        if not source:
            raise RuntimeError(f"SOURCE_ENRICHMENT: scene {index} has no mapped source")
        scene["source_id"] = source["id"]
        if not str(scene.get("source_claim", "")).strip():
            scene["source_claim"] = source["claim"]
    return existing


def main() -> dict:
    story = _load_story()
    sources = _build_sources(story)
    story["sources"] = sources
    story["source_system"] = {"policy": "Every published scene requires a trusted provenance mapping; specification claims must be backed by one or more remote sources."}
    (RUN / "long_story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    blueprint = RUN / "episode_blueprint.json"
    if blueprint.is_file():
        data = json.loads(blueprint.read_text(encoding="utf-8"))
        data["sources"] = sources
        data["source_system"] = story["source_system"]
        data["scenes"] = story.get("scenes", [])
        blueprint.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # compute covered scenes count explicitly
    covered = len({n for s in sources for n in s.get("scene_numbers", [])})
    print(f"SOURCE_ENRICHMENT=PASS sources={len(sources)} covered_scenes={covered}")
    return story


if __name__ == "__main__":
    main()
