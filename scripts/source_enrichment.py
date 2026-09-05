from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
SEARCH_TIMEOUT = max(5, int(os.getenv("SOURCE_SEARCH_TIMEOUT", "15")))
SOURCE_RETRIES = max(1, int(os.getenv("SOURCE_ENRICHMENT_RETRIES", "2")))

SPEC_RE = re.compile(r"\b(?:horsepower|hp|bhp|ps|nm|lb-ft|0-60|0\s*(?:to|-|–)\s*60|quarter mile|top speed|displacement|liter engine|litre engine|cubic|rpm|compression ratio|weight|curb weight)\b", re.I)

TRUSTED_GENERIC_DOMAINS = {
    "nhtsa.gov", "www.nhtsa.gov", "epa.gov", "www.epa.gov", "iihs.org", "www.iihs.org",
    "sae.org", "www.sae.org", "motortrend.com", "www.motortrend.com",
    "caranddriver.com", "www.caranddriver.com", "edmunds.com", "www.edmunds.com",
    "hagerty.com", "www.hagerty.com",
}

BRAND_DOMAINS = {
    "nissan": {"nissan-global.com", "www.nissan-global.com", "nissanusa.com", "www.nissanusa.com"},
    "toyota": {"toyota.com", "www.toyota.com"},
    "honda": {"honda.com", "www.honda.com"},
    "ford": {"ford.com", "www.ford.com"},
    "chevrolet": {"chevrolet.com", "www.chevrolet.com"},
    "porsche": {"porsche.com", "www.porsche.com"},
    "bmw": {"bmw.com", "www.bmw.com"},
    "mercedes": {"mercedes-benz.com", "www.mercedes-benz.com"},
    "audi": {"audi.com", "www.audi.com"},
    "lamborghini": {"lamborghini.com", "www.lamborghini.com"},
    "ferrari": {"ferrari.com", "www.ferrari.com"},
    "mclaren": {"mclaren.com", "www.mclaren.com"},
    "mazda": {"mazda.com", "www.mazda.com"},
    "subaru": {"subaru.com", "www.subaru.com"},
    "mitsubishi": {"mitsubishi-motors.com", "www.mitsubishi-motors.com"},
    "volkswagen": {"volkswagen.com", "www.volkswagen.com"},
    "hyundai": {"hyundai.com", "www.hyundai.com"},
    "tesla": {"tesla.com", "www.tesla.com"},
    "rimac": {"rimac-automobili.com", "www.rimac-automobili.com"},
}

TRUSTED_SOURCE_SEEDS = {
    "chevrolet": [
        {"url": "https://www.chevrolet.com/performance1/previous-year/corvette/stingray", "claim": "Official Chevrolet Corvette Stingray performance/specification reference.", "authority": "Chevrolet"},
        {"url": "https://www.chevrolet.com/ownercenter/content/dam/gmownercenter/gmna/dynamic/manuals/2022/chevrolet/corvette/2022-chevrolet-corvette-owners-manual.pdf", "claim": "Official Chevrolet Corvette owner-manual technical reference.", "authority": "Chevrolet Owner Center"},
    ],
}


def _domain(url: str) -> str:
    return urlparse(str(url)).netloc.casefold().split(":", 1)[0]


def _allowed_domains(vehicle: str) -> set[str]:
    domains = set(TRUSTED_GENERIC_DOMAINS)
    value = vehicle.casefold()
    for brand, brand_domains in BRAND_DOMAINS.items():
        if brand in value:
            domains.update(brand_domains)
    return domains


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


def _source_target_scenes(story: dict) -> list[int]:
    scenes = story.get("scenes", [])
    spec = [i for i, scene in enumerate(scenes, 1) if SPEC_RE.search(" ".join(str(scene.get(k, "")) for k in ("text_en", "technical_flow", "source_claim")))]
    if spec:
        return spec
    # Always register at least one trusted automotive reference even for a
    # qualitative episode; this prevents empty source manifests and gives the
    # final artifact a verifiable provenance anchor.
    return [1] if scenes else []


def _normalize_source(item: object, allowed: set[str]) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url", "")).strip()
    claim = str(item.get("claim", "")).strip()
    if not url.startswith("https://") or not claim or _domain(url) not in allowed:
        return None
    raw_numbers = item.get("scene_numbers", [])
    if not isinstance(raw_numbers, list):
        return None
    scene_numbers: list[int] = []
    for value in raw_numbers:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= 25 and number not in scene_numbers:
            scene_numbers.append(number)
    if not scene_numbers:
        return None
    return {
        "id": str(item.get("id", "")).strip()[:80],
        "claim": claim[:300],
        "url": url[:500],
        "authority": str(item.get("authority", "")).strip()[:120],
        "scene_numbers": scene_numbers,
        "source_type": str(item.get("source_type", "trusted_web")).strip()[:80] or "trusted_web",
    }


def _dedupe(sources: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for source in sources:
        key = source["url"].rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        source["id"] = source.get("id") or f"src-{len(result) + 1:02d}"
        result.append(source)
    return result


def _seed_recovery(target_scenes: list[int]) -> list[dict]:
    brand = _brand(_vehicle())
    normalized: list[dict] = []
    for seed in TRUSTED_SOURCE_SEEDS.get(brand, []):
        item = {**seed, "scene_numbers": list(target_scenes), "source_type": "trusted_official_seed"}
        source = _normalize_source(item, _allowed_domains(_vehicle()))
        if source:
            normalized.append(source)
    return _dedupe(normalized)


def _llm_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    prompt = {
        "task": "source_register_recovery",
        "vehicle": _vehicle(), "pillar": _pillar(), "story_title": story.get("title", ""),
        "target_scenes": target_scenes,
        "instructions": [
            "Return only HTTPS source URLs you are confident exist.",
            "Prefer official manufacturer pages, then NHTSA/EPA/IIHS/SAE, then established automotive publications.",
            "Never invent, guess, or synthesize a URL.",
            "Each source must include a concise factual claim and scene_numbers.",
        ],
        "return": "JSON only: {sources:[{url,claim,authority,scene_numbers}]}",
    }
    for attempt in range(SOURCE_RETRIES):
        try:
            body = call(json.dumps(prompt, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=120)
            candidate = extract_json(body)
            raw = candidate.get("sources", []) if isinstance(candidate, dict) else []
            if isinstance(raw, list):
                cleaned = [s for item in raw if (s := _normalize_source(item, _allowed_domains(_vehicle())))]
                if cleaned:
                    return _dedupe(cleaned)
        except Exception as exc:
            print(f"SOURCE_LLM_RECOVERY_RETRY={attempt + 1} error={exc}")
    return []


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.links: list[tuple[str, str]] = []; self._href = ""; self._text: list[str] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a": return
        attrs_dict = dict(attrs); self._href = html.unescape(attrs_dict.get("href") or ""); self._text = []
    def handle_data(self, data: str) -> None:
        if self._href: self._text.append(data)
    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href:
            text = re.sub(r"\s+", " ", " ".join(self._text)).strip(); self.links.append((self._href, text)); self._href = ""; self._text = []


def _unwrap_search_url(href: str) -> str:
    absolute = "https:" + href if href.startswith("//") else href
    parsed = urllib.parse.urlparse(absolute)
    query = urllib.parse.parse_qs(parsed.query)
    redirected = query.get("uddg", [None])[0]
    return urllib.parse.unquote(redirected) if redirected else absolute


def _search_links(query: str) -> list[tuple[str, str]]:
    url = f"https://html.duckduckgo.com/html/?{urllib.parse.urlencode({'q': query})}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AutomotiveSourceBot/2.0; +https://github.com/Aqaaab/faceless-youtube-shorts-n8n)"})
    with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parser = _LinkParser(); parser.feed(raw)
    return [(_unwrap_search_url(href), title) for href, title in parser.links]


def _web_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    vehicle = _vehicle(); allowed = _allowed_domains(vehicle); brand = _brand(vehicle)
    searches = [f'"{vehicle}" {_pillar()} official', f'"{vehicle}" specifications {brand}'.strip(), f'"{vehicle}" engineering {brand}'.strip()]
    candidates: list[dict] = []
    for query in searches:
        try:
            for absolute, title in _search_links(query):
                if not absolute.startswith("https://") or _domain(absolute) not in allowed:
                    continue
                if any(x["url"].rstrip("/").casefold() == absolute.rstrip("/").casefold() for x in candidates):
                    continue
                candidates.append({
                    "id": "", "claim": f"Reference page for {vehicle}: {title or 'vehicle-specific technical information'}"[:300],
                    "url": absolute[:500], "authority": _domain(absolute), "scene_numbers": list(target_scenes), "source_type": "trusted_web_search",
                })
                if len(candidates) >= 5: return _dedupe(candidates)
        except Exception as exc:
            print(f"SOURCE_WEB_SEARCH_ERROR query={query!r} error={exc}")
    return _dedupe(candidates)


def _build_sources(story: dict) -> list[dict]:
    target_scenes = _source_target_scenes(story)
    if not target_scenes:
        return []
    allowed = _allowed_domains(_vehicle())
    existing = [s for item in story.get("sources", []) if (s := _normalize_source(item, allowed))]
    existing = _dedupe(existing)
    mapped = {number for source in existing for number in source["scene_numbers"]}
    missing = [number for number in target_scenes if number not in mapped]
    if missing:
        recovered = _llm_recovery(story, missing); existing = _dedupe(existing + recovered)
        mapped = {number for source in existing for number in source["scene_numbers"]}; missing = [n for n in target_scenes if n not in mapped]
    if missing:
        recovered = _web_recovery(story, missing); existing = _dedupe(existing + recovered)
        mapped = {number for source in existing for number in source["scene_numbers"]}; missing = [n for n in target_scenes if n not in mapped]
    if missing:
        recovered = _seed_recovery(missing); existing = _dedupe(existing + recovered)
        mapped = {number for source in existing for number in source["scene_numbers"]}; missing = [n for n in target_scenes if n not in mapped]
    if missing:
        raise RuntimeError("SOURCE_ENRICHMENT: unable to map trusted sources to required scenes: " + ",".join(map(str, missing)))

    for index, scene in enumerate(story.get("scenes", []), 1):
        relevant = next((source for source in existing if index in source["scene_numbers"]), None)
        if relevant:
            scene["source_id"] = relevant["id"]
            if not str(scene.get("source_claim", "")).strip(): scene["source_claim"] = relevant["claim"]
    return existing


def main() -> dict:
    story = _load_story(); sources = _build_sources(story); story["sources"] = sources
    story["source_system"] = {
        "policy": "Vehicle-specific specifications require trusted source mapping; qualitative mechanisms still retain a provenance anchor.",
        "source_count": len(sources), "external_media": "Pexels only",
        "enrichment": "llm_recovery_then_trusted_web_search_then_official_seed",
        "trusted_domains": sorted(_allowed_domains(_vehicle())),
    }
    path = RUN / "long_story.json"; path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    blueprint = RUN / "episode_blueprint.json"
    if blueprint.is_file():
        data = json.loads(blueprint.read_text(encoding="utf-8")); data["sources"] = sources; data["source_system"] = story["source_system"]; data["scenes"] = story.get("scenes", [])
        blueprint.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SOURCE_ENRICHMENT=PASS sources={len(sources)} technical_target_scenes={','.join(map(str, target_scenes))}")
    return story


if __name__ == "__main__": main()
