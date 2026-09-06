from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

from odysseus_gateway import call, extract_json
from automotive_source_provider import discover_sources

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
SEARCH_TIMEOUT = max(5, int(os.getenv("SOURCE_SEARCH_TIMEOUT", "15")))
SOURCE_RETRIES = max(1, int(os.getenv("SOURCE_ENRICHMENT_RETRIES", "2")))
VERIFY_REMOTE = os.getenv("SOURCE_VERIFY_REMOTE", "1") == "1"
SPEC_RE = re.compile(r"\b(?:horsepower|hp|bhp|ps|nm|lb-ft|0-60|0\s*(?:to|-|–)\s*60|quarter mile|top speed|displacement|liter engine|litre engine|cubic|rpm|compression ratio|weight|curb weight)\b", re.I)
TRUSTED_GENERIC_DOMAINS = {"nhtsa.gov", "www.nhtsa.gov", "epa.gov", "www.epa.gov", "iihs.org", "www.iihs.org", "sae.org", "www.sae.org", "motortrend.com", "www.motortrend.com", "caranddriver.com", "www.caranddriver.com"}
BRAND_DOMAINS = {
    "nissan": {"nissan-global.com", "www.nissan-global.com", "nissanusa.com", "www.nissanusa.com"},
    "toyota": {"toyota.com", "www.toyota.com"},
    "lexus": {"lexus.com", "www.lexus.com"},
    "daihatsu": {"daihatsu.com", "www.daihatsu.com"},
    "honda": {"honda.com", "www.honda.com"},
    "acura": {"acura.com", "www.acura.com"},
    "infiniti": {"infinitiusa.com", "www.infinitiusa.com"},
    "ford": {"ford.com", "www.ford.com"},
    "lincoln": {"lincoln.com", "www.lincoln.com"},
    "chevrolet": {"chevrolet.com", "www.chevrolet.com"},
    "cadillac": {"cadillac.com", "www.cadillac.com"},
    "buick": {"buick.com", "www.buick.com"},
    "gmc": {"gmc.com", "www.gmc.com"},
    "porsche": {"porsche.com", "www.porsche.com", "newsroom.porsche.com", "files.porsche.com"},
    "bmw": {"bmw.com", "www.bmw.com", "bmw-m.com", "www.bmw-m.com"},
    "mini": {"mini.com", "www.mini.com"},
    "rolls-royce": {"rolls-roycemotorcars.com", "www.rolls-roycemotorcars.com"},
    "mercedes": {"mercedes-benz.com", "www.mercedes-benz.com", "media.mercedes-benz.com", "group-media.mercedes-benz.com"},
    "mercedes-amg": {"mercedes-amg.com", "www.mercedes-amg.com", "mercedes-benz.com", "www.mercedes-benz.com"},
    "maybach": {"mercedes-maybach.com", "www.mercedes-maybach.com", "mercedes-benz.com", "www.mercedes-benz.com"},
    "smart": {"smart.com", "www.smart.com"},
    "audi": {"audi.com", "www.audi.com", "audi-mediacenter.com", "www.audi-mediacenter.com"},
    "lamborghini": {"lamborghini.com", "www.lamborghini.com", "preowned.lamborghini.com"},
    "bentley": {"bentleymotors.com", "www.bentleymotors.com"},
    "bugatti": {"bugatti.com", "www.bugatti.com"},
    "mclaren": {"mclaren.com", "cars.mclaren.com", "www.mclaren.com", "www.cars.mclaren.com"},
    "mazda": {"mazda.com", "www.mazda.com"},
    "subaru": {"subaru.com", "www.subaru.com", "media.subaru.com"},
    "mitsubishi": {"mitsubishi-motors.com", "www.mitsubishi-motors.com"},
    "suzuki": {"globalsuzuki.com", "www.globalsuzuki.com"},
    "isuzu": {"isuzu.co.jp", "www.isuzu.co.jp"},
    "volkswagen": {"volkswagen.com", "www.volkswagen.com", "media.volkswagen.com"},
    "opel": {"opel.com", "www.opel.com"},
    "vauxhall": {"vauxhall.co.uk", "www.vauxhall.co.uk"},
    "peugeot": {"peugeot.com", "www.peugeot.com"},
    "citroen": {"citroen.com", "www.citroen.com"},
    "ds": {"dsautomobiles.com", "www.dsautomobiles.com"},
    "renault": {"renaultgroup.com", "www.renaultgroup.com", "renault.com", "www.renault.com"},
    "dacia": {"dacia.com", "www.dacia.com"},
    "alpine": {"alpinecars.com", "www.alpinecars.com"},
    "fiat": {"fiat.com", "www.fiat.com"},
    "abarth": {"abarth.com", "www.abarth.com"},
    "alfa romeo": {"alfaromeo.com", "www.alfaromeo.com"},
    "maserati": {"maserati.com", "www.maserati.com"},
    "ferrari": {"ferrari.com", "www.ferrari.com"},
    "aston martin": {"astonmartin.com", "www.astonmartin.com"},
    "lotus": {"lotuscars.com", "www.lotuscars.com"},
    "jaguar": {"jaguar.com", "www.jaguar.com"},
    "land rover": {"landrover.com", "www.landrover.com"},
    "range rover": {"rangerover.com", "www.rangerover.com"},
    "volvo": {"volvocars.com", "www.volvocars.com"},
    "polestar": {"polestar.com", "www.polestar.com"},
    "saab": {"saab.com", "www.saab.com"},
    "koenigsegg": {"koenigsegg.com", "www.koenigsegg.com"},
    "pagani": {"pagani.com", "www.pagani.com"},
    "rimac": {"rimac-automobili.com", "www.rimac-automobili.com"},
    "zenvo": {"zenvoautomotive.com", "www.zenvoautomotive.com"},
    "ineos": {"ineosgrenadier.com", "www.ineosgrenadier.com"},
    "tesla": {"tesla.com", "www.tesla.com"},
    "rivian": {"rivian.com", "www.rivian.com"},
    "lucid": {"lucidmotors.com", "www.lucidmotors.com"},
    "fisker": {"fiskerinc.com", "www.fiskerinc.com"},
    "hummer": {"gmc.com", "www.gmc.com"},
    "karma": {"karmanow.com", "www.karmanow.com"},
    "hyundai": {"hyundai.com", "www.hyundai.com", "hyundainews.com"},
    "genesis": {"genesis.com", "www.genesis.com"},
    "kia": {"kia.com", "www.kia.com"},
    "kgm": {"kg-mobility.com", "www.kg-mobility.com"},
    "ssangyong": {"kg-mobility.com", "www.kg-mobility.com"},
    "byd": {"byd.com", "www.byd.com"},
    "denza": {"denza.com", "www.denza.com"},
    "yangwang": {"yangwangauto.com", "www.yangwangauto.com"},
    "fangchengbao": {"fangchengbao.com", "www.fangchengbao.com"},
    "geely": {"geely.com", "global.geely.com", "www.geely.com"},
    "zeekr": {"zeekrglobal.com", "www.zeekrglobal.com"},
    "lynk & co": {"lynkco.com", "www.lynkco.com"},
    "chery": {"cheryinternational.com", "www.cheryinternational.com"},
    "exeed": {"exeedcars.com", "www.exeedcars.com"},
    "jetour": {"jetourglobal.com", "www.jetourglobal.com"},
    "omoda": {"omodaauto.com", "www.omodaauto.com"},
    "jaecoo": {"jaecoo.com", "www.jaecoo.com"},
    "great wall": {"gwm-global.com", "www.gwm-global.com"},
    "gwm": {"gwm-global.com", "www.gwm-global.com"},
    "haval": {"gwm-global.com", "www.gwm-global.com"},
    "tank": {"gwm-global.com", "www.gwm-global.com"},
    "ora": {"gwm-global.com", "www.gwm-global.com"},
    "nio": {"nio.com", "www.nio.com"},
    "xpeng": {"xpeng.com", "www.xpeng.com"},
    "li auto": {"lixiang.com", "ir.lixiang.com", "www.lixiang.com"},
    "seres": {"seres.com", "www.seres.com"},
    "aito": {"aito.auto", "www.aito.auto"},
    "avatr": {"avatr.com", "www.avatr.com"},
    "arcfox": {"arcfox.com", "www.arcfox.com"},
    "baic": {"baicglobal.com", "www.baicglobal.com"},
    "bestune": {"bestune-global.com", "www.bestune-global.com"},
    "hongqi": {"faw-hongqi.com", "www.faw-hongqi.com"},
    "saic": {"saicmotor.com", "www.saicmotor.com"},
    "mg": {"mgmotor.eu", "www.mgmotor.eu"},
    "wuling": {"wuling.com", "www.wuling.com"},
    "foton": {"foton-global.com", "www.foton-global.com"},
    "leapmotor": {"leapmotor.com", "www.leapmotor.com"},
    "xiaomi": {"xiaomiev.com", "www.xiaomiev.com"},
    "tata": {"tatamotors.com", "www.tatamotors.com"},
    "mahindra": {"mahindra.com", "www.mahindra.com"},
    "maruti": {"marutisuzuki.com", "www.marutisuzuki.com"},
    "perodua": {"perodua.com.my", "www.perodua.com.my"},
    "proton": {"proton.com", "www.proton.com"},
    "vinfast": {"vinfastauto.com", "www.vinfastauto.com"},
    "holden": {"holden.com.au", "www.holden.com.au"},
    "changan": {"globalchangan.com", "www.globalchangan.com"},
    "dongfeng": {"dongfeng-global.com", "www.dongfeng-global.com"},
    "faw": {"faw.com", "www.faw.com"},
    "general motors": {"gm.com", "www.gm.com"},
    "stellantis": {"stellantis.com", "www.stellantis.com"},
}
TRUSTED_SOURCE_SEEDS = {
    "chevrolet": [{"url": "https://www.chevrolet.com/performance1/previous-year/corvette/stingray", "claim": "Official Chevrolet Corvette Stingray performance/specification reference"}],
    "porsche": [
        {"url": "https://www.porsche.com/international/models/911/carrera-models/911-carrera/", "claim": "Official Porsche 911 Carrera technical and performance reference"},
        {"url": "https://newsroom.porsche.com/en/press-kits/60-Years-Porsche-911/8.-Generation-Porsche-911%2C-%28992%29%2C-seit-2018.html", "claim": "Official Porsche Newsroom reference for the 992 generation and Porsche engineering architecture"},
    ],
    "lamborghini": [{"url": "https://www.lamborghini.com/en-en/history/huracan-evo", "claim": "Official Lamborghini Huracan EVO technical, design and performance reference"}],
}


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
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("SOURCE_ENRICHMENT: long_story.json must be an object")
    return data


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
    return {"id": str(item.get("id", "")).strip()[:80], "claim": claim[:300], "url": url[:500], "authority": str(item.get("authority", "")).strip()[:120], "scene_numbers": nums, "source_type": str(item.get("source_type", "")).strip()[:80]}


def _normalize_url(url: str) -> str:
    try:
        parsed = urlparse(str(url).strip())
    except Exception:
        return str(url).strip()
    params = parse_qs(parsed.query, keep_blank_values=True)
    parts = []
    for key in sorted(params.keys(), key=str.casefold):
        for value in sorted(params[key]):
            parts.append(f"{key}={value}")
    query = "&".join(parts)
    scheme = parsed.scheme.casefold()
    netloc = parsed.netloc.casefold()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def _dedupe(sources: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        key = (_normalize_url(str(source.get("url", ""))), str(source.get("claim", "")).strip()[:100].casefold())
        if key in seen:
            continue
        seen.add(key)
        item = dict(source)
        item["id"] = str(item.get("id") or f"src-{len(result) + 1:02d}")[:80]
        result.append(item)
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
        elif source["source_type"] == "trusted_official_seed" and not VERIFY_REMOTE:
            out.append(source)
    return _dedupe(out)


def _extract_json_value(body: dict) -> object:
    value = body.get("response")
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise ValueError("LLM response is not text or JSON")
    text = value.strip().replace("\ufeff", "")
    object_start, object_end = text.find("{"), text.rfind("}")
    array_start, array_end = text.find("["), text.rfind("]")
    candidates: list[str] = []
    if array_start >= 0 and array_end > array_start and (object_start < 0 or array_start < object_start):
        candidates.append(text[array_start : array_end + 1])
    if object_start >= 0 and object_end > object_start:
        candidates.append(text[object_start : object_end + 1])
    if array_start >= 0 and array_end > array_start and not candidates:
        candidates.append(text[array_start : array_end + 1])
    last_error: Exception | None = None
    for raw in candidates:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                return repair_json(raw, return_objects=True)
            except Exception as repair_exc:
                last_error = repair_exc
    raise ValueError(f"Invalid LLM JSON: {last_error}")


def _source_items_from_payload(candidate: object) -> list[object]:
    if isinstance(candidate, list):
        return candidate
    if not isinstance(candidate, dict):
        return []
    for key in ("sources", "source_register", "items"):
        value = candidate.get(key)
        if isinstance(value, list):
            return value
    single = candidate.get("source")
    return [single] if isinstance(single, dict) else []


def _llm_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    allowed = _allowed_domains(_vehicle())
    prompt = {"task": "source_register_recovery", "vehicle": _vehicle(), "pillar": _pillar(), "story_title": story.get("title", ""), "target_scenes": target_scenes, "requirements": {"return_json": "object_with_sources_or_top_level_array", "every_source_must_cover": target_scenes, "https_only": True, "trusted_domains_only": sorted(allowed), "no_markdown": True}}
    for attempt in range(SOURCE_RETRIES):
        try:
            response = call(json.dumps(prompt, ensure_ascii=False), model=os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story"), timeout=120)
            try:
                candidate = extract_json(response)
            except ValueError:
                candidate = _extract_json_value(response)
            raw = _source_items_from_payload(candidate)
            if not raw:
                try:
                    alternative = _extract_json_value(response)
                except ValueError:
                    alternative = None
                if alternative is not candidate:
                    raw = _source_items_from_payload(alternative)
            if isinstance(raw, list):
                cleaned = [s for item in raw if (s := _normalize_source(item, allowed))]
                cleaned = _verified_sources(cleaned, allowed)
                if cleaned:
                    return cleaned
        except Exception as exc:
            print(f"SOURCE_LLM_RECOVERY_RETRY={attempt + 1} error={str(exc)[:300]}")
    return []


def _web_recovery(story: dict, target_scenes: list[int]) -> list[dict]:
    allowed = _allowed_domains(_vehicle())
    discovered = discover_sources(vehicle=_vehicle(), pillar=_pillar(), target_scenes=target_scenes)
    normalized = [s for item in discovered if (s := _normalize_source(item, allowed))]
    verified = _verified_sources(normalized, allowed)
    if verified:
        print(f"SOURCE_PROVIDER=PASS provider=automotive_source_provider sources={len(verified)}")
    else:
        print("SOURCE_PROVIDER=EMPTY provider=automotive_source_provider")
    return verified


def _build_sources(story: dict) -> list[dict]:
    target = _source_target_scenes(story)
    if not target:
        return []
    allowed = _allowed_domains(_vehicle())
    normalized_existing = _dedupe([s for item in story.get("sources", []) if (s := _normalize_source(item, allowed))])
    had_existing_register = bool(normalized_existing)
    existing = _verified_sources(normalized_existing, allowed)
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
    if missing and not had_existing_register:
        existing = _dedupe(existing + _seed_recovery(missing))
        mapped = {n for s in existing for n in s["scene_numbers"]}
        missing = [n for n in target if n not in mapped]
    if missing:
        raise RuntimeError("SOURCE_ENRICHMENT: unable to map trusted sources to required scenes: " + ",".join(map(str, missing)))
    for index, scene in enumerate(story.get("scenes", []), 1):
        source = next((s for s in existing if index in s["scene_numbers"]), None)
        if not source:
            raise RuntimeError(f"SOURCE_ENRICHMENT: scene {index} has no mapped trusted source")
        scene["source_id"] = source["id"]
        scene["source_url"] = source["url"]
        scene["source_claim"] = source["claim"]
    story["sources"] = existing
    return existing
