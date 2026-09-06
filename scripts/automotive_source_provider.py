from __future__ import annotations

import re
from urllib.parse import quote_plus

# Credential-free automotive source resolver.  The catalogue is intentionally broad,
# but resolution does NOT depend on the vehicle being present in a model dictionary.
# A randomly selected vehicle is normalized to a brand, then given several candidate
# sources: official brand site first, reputable automotive research second, NHTSA last.
# source_enrichment.py remains responsible for remote verification and trusted-domain
# enforcement; this module never bypasses that provenance gate.

# Canonical brand -> official source URL.  These are public manufacturer / brand domains
# used as durable roots rather than brittle model-page URLs.
BRAND_SOURCE_CATALOG: dict[str, tuple[str, str]] = {
    # Japan
    "toyota": ("https://www.toyota.com/", "Official Toyota vehicle and engineering reference"),
    "lexus": ("https://www.lexus.com/", "Official Lexus vehicle and engineering reference"),
    "daihatsu": ("https://www.daihatsu.com/", "Official Daihatsu vehicle and engineering reference"),
    "honda": ("https://www.honda.com/", "Official Honda vehicle and engineering reference"),
    "acura": ("https://www.acura.com/", "Official Acura vehicle and engineering reference"),
    "nissan": ("https://www.nissan-global.com/EN/", "Official Nissan manufacturer and technology reference"),
    "infiniti": ("https://www.infinitiusa.com/", "Official INFINITI vehicle and technology reference"),
    "mazda": ("https://www.mazda.com/en/", "Official Mazda vehicle and engineering reference"),
    "subaru": ("https://www.subaru.com/", "Official Subaru vehicle and engineering reference"),
    "mitsubishi": ("https://www.mitsubishi-motors.com/en/", "Official Mitsubishi Motors vehicle and engineering reference"),
    "suzuki": ("https://www.globalsuzuki.com/", "Official Suzuki vehicle and engineering reference"),
    "isuzu": ("https://www.isuzu.co.jp/world/", "Official Isuzu vehicle and engineering reference"),
    # Germany / Europe
    "volkswagen": ("https://www.volkswagen.com/", "Official Volkswagen vehicle and technology reference"),
    "audi": ("https://www.audi.com/", "Official Audi vehicle and technology reference"),
    "porsche": ("https://www.porsche.com/international/", "Official Porsche vehicle and engineering reference"),
    "lamborghini": ("https://www.lamborghini.com/", "Official Lamborghini vehicle and engineering reference"),
    "bentley": ("https://www.bentleymotors.com/", "Official Bentley vehicle and engineering reference"),
    "bugatti": ("https://www.bugatti.com/", "Official Bugatti vehicle and engineering reference"),
    "bmw": ("https://www.bmw.com/", "Official BMW vehicle and engineering reference"),
    "mini": ("https://www.mini.com/", "Official MINI vehicle and engineering reference"),
    "rolls-royce": ("https://www.rolls-roycemotorcars.com/", "Official Rolls-Royce Motor Cars engineering reference"),
    "mercedes": ("https://www.mercedes-benz.com/", "Official Mercedes-Benz vehicle and engineering reference"),
    "smart": ("https://www.smart.com/", "Official smart vehicle and technology reference"),
    "maybach": ("https://www.mercedes-maybach.com/", "Official Mercedes-Maybach vehicle reference"),
    "mercedes-amg": ("https://www.mercedes-amg.com/", "Official Mercedes-AMG performance reference"),
    "opel": ("https://www.opel.com/", "Official Opel vehicle and technology reference"),
    "vauxhall": ("https://www.vauxhall.co.uk/", "Official Vauxhall vehicle and technology reference"),
    "peugeot": ("https://www.peugeot.com/", "Official Peugeot vehicle and technology reference"),
    "citroen": ("https://www.citroen.com/", "Official Citroen vehicle and technology reference"),
    "ds": ("https://www.dsautomobiles.com/", "Official DS Automobiles vehicle and technology reference"),
    "renault": ("https://www.renaultgroup.com/", "Official Renault Group automotive reference"),
    "dacia": ("https://www.dacia.com/", "Official Dacia vehicle and engineering reference"),
    "alpine": ("https://www.alpinecars.com/", "Official Alpine vehicle and engineering reference"),
    "fiat": ("https://www.fiat.com/", "Official FIAT vehicle and technology reference"),
    "abarth": ("https://www.abarth.com/", "Official Abarth performance vehicle reference"),
    "alfa romeo": ("https://www.alfaromeo.com/", "Official Alfa Romeo vehicle and engineering reference"),
    "maserati": ("https://www.maserati.com/", "Official Maserati vehicle and engineering reference"),
    "ferrari": ("https://www.ferrari.com/en-EN/auto", "Official Ferrari road-car technical and design reference"),
    "mclaren": ("https://cars.mclaren.com/", "Official McLaren road-car technical and engineering reference"),
    "aston martin": ("https://www.astonmartin.com/", "Official Aston Martin vehicle and engineering reference"),
    "lotus": ("https://www.lotuscars.com/", "Official Lotus vehicle and engineering reference"),
    "jaguar": ("https://www.jaguar.com/", "Official Jaguar vehicle and engineering reference"),
    "land rover": ("https://www.landrover.com/", "Official Land Rover vehicle and engineering reference"),
    "range rover": ("https://www.rangerover.com/", "Official Range Rover vehicle and engineering reference"),
    "volvo": ("https://www.volvocars.com/", "Official Volvo vehicle and safety engineering reference"),
    "polestar": ("https://www.polestar.com/", "Official Polestar vehicle and electric engineering reference"),
    "saab": ("https://www.saab.com/", "Saab brand and engineering reference"),
    "koenigsegg": ("https://www.koenigsegg.com/", "Official Koenigsegg vehicle and engineering reference"),
    "pagani": ("https://www.pagani.com/", "Official Pagani vehicle and engineering reference"),
    "rimac": ("https://www.rimac-automobili.com/", "Official Rimac electric-performance reference"),
    "zenvo": ("https://zenvoautomotive.com/", "Official Zenvo performance-vehicle reference"),
    "ineos": ("https://ineosgrenadier.com/", "Official INEOS Grenadier vehicle reference"),
    # United States
    "ford": ("https://www.ford.com/", "Official Ford manufacturer and vehicle technology reference"),
    "lincoln": ("https://www.lincoln.com/", "Official Lincoln vehicle and technology reference"),
    "chevrolet": ("https://www.chevrolet.com/", "Official Chevrolet vehicle and performance reference"),
    "cadillac": ("https://www.cadillac.com/", "Official Cadillac vehicle and engineering reference"),
    "buick": ("https://www.buick.com/", "Official Buick vehicle and technology reference"),
    "gmc": ("https://www.gmc.com/", "Official GMC vehicle and engineering reference"),
    "dodge": ("https://www.dodge.com/", "Official Dodge performance vehicle reference"),
    "ram": ("https://www.ramtrucks.com/", "Official Ram vehicle and engineering reference"),
    "chrysler": ("https://www.chrysler.com/", "Official Chrysler vehicle and technology reference"),
    "jeep": ("https://www.jeep.com/", "Official Jeep vehicle and engineering reference"),
    "tesla": ("https://www.tesla.com/", "Official Tesla vehicle and technology reference"),
    "rivian": ("https://rivian.com/", "Official Rivian electric vehicle and engineering reference"),
    "lucid": ("https://lucidmotors.com/", "Official Lucid electric vehicle and engineering reference"),
    "fisker": ("https://www.fiskerinc.com/", "Fisker vehicle reference"),
    "hummer": ("https://www.gmc.com/hummer", "Official GMC HUMMER EV reference"),
    "karma": ("https://www.karmanow.com/", "Karma Automotive vehicle and technology reference"),
    # South Korea
    "hyundai": ("https://www.hyundai.com/", "Official Hyundai vehicle and technology reference"),
    "genesis": ("https://www.genesis.com/", "Official Genesis vehicle and engineering reference"),
    "kia": ("https://www.kia.com/", "Official Kia vehicle and technology reference"),
    "kgm": ("https://www.kg-mobility.com/", "Official KGM vehicle and engineering reference"),
    "ssangyong": ("https://www.kg-mobility.com/", "Official KGM/SsangYong vehicle reference"),
    # China / new-energy manufacturers
    "byd": ("https://www.byd.com/", "Official BYD vehicle and battery-technology reference"),
    "denza": ("https://www.denza.com/", "Official DENZA vehicle and technology reference"),
    "yangwang": ("https://www.yangwangauto.com/", "Official YANGWANG vehicle and technology reference"),
    "fangchengbao": ("https://www.fangchengbao.com/", "Official Fangchengbao vehicle reference"),
    "geely": ("https://global.geely.com/", "Official Geely vehicle and technology reference"),
    "zeekr": ("https://www.zeekrglobal.com/", "Official ZEEKR vehicle and electric technology reference"),
    "lynk & co": ("https://www.lynkco.com/", "Official Lynk & Co vehicle and technology reference"),
    "chery": ("https://www.cheryinternational.com/", "Official Chery vehicle and engineering reference"),
    "exeed": ("https://www.exeedcars.com/", "Official EXEED vehicle reference"),
    "jetour": ("https://jetourglobal.com/", "Official JETOUR vehicle reference"),
    "omoda": ("https://omodaauto.com/", "Official OMODA vehicle reference"),
    "jaecoo": ("https://jaecoo.com/", "Official JAECOO vehicle reference"),
    "great wall": ("https://www.gwm-global.com/", "Official GWM vehicle and technology reference"),
    "gwm": ("https://www.gwm-global.com/", "Official GWM vehicle and technology reference"),
    "haval": ("https://www.gwm-global.com/", "Official HAVAL vehicle reference"),
    "tank": ("https://www.gwm-global.com/", "Official TANK vehicle reference"),
    "ora": ("https://www.gwm-global.com/", "Official ORA vehicle reference"),
    "nio": ("https://www.nio.com/", "Official NIO electric vehicle and technology reference"),
    "xpeng": ("https://www.xpeng.com/", "Official XPENG electric vehicle and technology reference"),
    "li auto": ("https://ir.lixiang.com/", "Official Li Auto vehicle and technology reference"),
    "seres": ("https://www.seres.com/", "SERES vehicle and technology reference"),
    "aito": ("https://aito.auto/", "Official AITO vehicle and technology reference"),
    "avatr": ("https://www.avatr.com/", "Official AVATR vehicle and technology reference"),
    "arcfox": ("https://www.arcfox.com/", "Official ARCFOX vehicle and technology reference"),
    "baic": ("https://www.baicglobal.com/", "Official BAIC vehicle and technology reference"),
    "bestune": ("https://www.bestune-global.com/", "Official Bestune vehicle reference"),
    "hongqi": ("https://www.faw-hongqi.com/", "Official Hongqi vehicle reference"),
    "saic": ("https://www.saicmotor.com/", "Official SAIC Motor automotive reference"),
    "mg": ("https://www.mgmotor.eu/", "Official MG Motor vehicle reference"),
    "wuling": ("https://www.wuling.com/", "Official Wuling vehicle reference"),
    "foton": ("https://www.foton-global.com/", "Official Foton vehicle reference"),
    "leapmotor": ("https://www.leapmotor.com/", "Official Leapmotor vehicle and technology reference"),
    "xiaomi": ("https://www.xiaomiev.com/", "Official Xiaomi EV vehicle and technology reference"),
    # India / Southeast Asia / Oceania
    "tata": ("https://www.tatamotors.com/", "Official Tata Motors vehicle and engineering reference"),
    "mahindra": ("https://www.mahindra.com/", "Official Mahindra vehicle and engineering reference"),
    "maruti": ("https://www.marutisuzuki.com/", "Official Maruti Suzuki vehicle reference"),
    "perodua": ("https://www.perodua.com.my/", "Official Perodua vehicle reference"),
    "proton": ("https://www.proton.com/", "Official Proton vehicle reference"),
    "vinfast": ("https://vinfastauto.com/", "Official VinFast electric vehicle reference"),
    "holden": ("https://www.holden.com.au/", "Holden brand vehicle reference"),
}

# Common spellings, sub-brands and parent-group names. Values point into the canonical
# catalogue, so a random selector can emit many real-world spellings without special-case
# source logic.
BRAND_ALIASES: dict[str, str] = {
    "mercedes-benz": "mercedes",
    "mercedes benz": "mercedes",
    "benz": "mercedes",
    "mb": "mercedes",
    "amg": "mercedes-amg",
    "mercedes amg": "mercedes-amg",
    "rolls royce": "rolls-royce",
    "alfa-romeo": "alfa romeo",
    "alfa": "alfa romeo",
    "aston-martin": "aston martin",
    "landrover": "land rover",
    "range-rover": "range rover",
    "great wall motors": "great wall",
    "great wall motor": "great wall",
    "kg mobility": "kgm",
    "kg-mobility": "kgm",
    "ssang-yong": "ssangyong",
    "lixiang": "li auto",
    "li": "li auto",
    "saic motor": "saic",
    "changan automobile": "changan",
    "changan": "changan",
    "dongfeng": "dongfeng",
    "dfm": "dongfeng",
    "faw": "faw",
    "jaguar land rover": "land rover",
    "jlr": "land rover",
    "gm": "general motors",
    "general motors": "general motors",
    "stellantis": "stellantis",
    "volkswagen group": "volkswagen",
    "vw": "volkswagen",
}

# Parent brands used only for source resolution when a sub-brand does not maintain a
# sufficiently stable public root. These entries are additive to the catalogue.
BRAND_SOURCE_CATALOG.update({
    "changan": ("https://www.globalchangan.com/", "Official Changan vehicle and technology reference"),
    "dongfeng": ("https://www.dongfeng-global.com/", "Official Dongfeng vehicle reference"),
    "faw": ("https://www.faw.com/", "Official FAW automotive reference"),
    "general motors": ("https://www.gm.com/", "Official General Motors automotive reference"),
    "stellantis": ("https://www.stellantis.com/", "Official Stellantis automotive group reference"),
    "saab": ("https://www.saab.com/", "Saab engineering reference"),
})

MODEL_SOURCES = {
    "Lamborghini Huracan EVO": ("https://www.lamborghini.com/en-en/history/huracan-evo", "Official Lamborghini Huracan EVO technical, design and performance reference"),
    "Porsche 911 992 Carrera": ("https://www.porsche.com/international/models/911/carrera-models/911-carrera/", "Official Porsche 911 Carrera technical and performance reference"),
    "Chevrolet Corvette C8": ("https://www.chevrolet.com/performance1/previous-year/corvette/stingray", "Official Chevrolet Corvette Stingray performance and specification reference"),
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def _find_brand(vehicle: str) -> str:
    value = _normalize_text(vehicle)
    # Prefer longest names first so "land rover" wins over shorter aliases.
    candidates: list[tuple[int, int, str]] = []
    for raw, canonical in BRAND_ALIASES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(raw)}(?![a-z0-9])", value):
            candidates.append((len(raw), 0, canonical))
    for brand in BRAND_SOURCE_CATALOG:
        if re.search(rf"(?<![a-z0-9]){re.escape(brand)}(?![a-z0-9])", value):
            candidates.append((len(brand), 1, brand))
    if not candidates:
        # Controlled substring fallback handles forms such as "MercedesAMG GT".
        for raw, canonical in BRAND_ALIASES.items():
            if raw.replace(" ", "").replace("-", "") in value.replace(" ", "").replace("-", ""):
                candidates.append((len(raw), 0, canonical))
        for brand in BRAND_SOURCE_CATALOG:
            if brand.replace(" ", "").replace("-", "") in value.replace(" ", "").replace("-", ""):
                candidates.append((len(brand), 1, brand))
    return max(candidates, key=lambda item: (item[0], -item[1]))[2] if candidates else ""


def _search_url(domain: str, query: str) -> str:
    # Search pages are secondary candidates. source_enrichment.py validates the final
    # host, so these never become an alternate trust boundary.
    encoded = quote_plus(query)
    if domain == "caranddriver":
        return f"https://www.caranddriver.com/search/?q={encoded}"
    return f"https://www.motortrend.com/search/?q={encoded}"


def _provider_candidates(vehicle: str, pillar: str, canonical_brand: str) -> list[tuple[str, str, str]]:
    query = f"{vehicle} {pillar} automotive specifications engineering"
    selected = BRAND_SOURCE_CATALOG.get(canonical_brand)
    candidates: list[tuple[str, str, str]] = []
    if selected:
        url, claim = selected
        candidates.append((url, claim, "official_manufacturer"))
    # Keep reputable automotive publications as resilience candidates. These are already
    # part of source_enrichment.py's trusted generic allow-list.
    candidates.append((_search_url("caranddriver", query), f"Car and Driver research results for {vehicle}; editorial pillar: {pillar}.", "trusted_automotive_search"))
    candidates.append((_search_url("motortrend", query), f"MotorTrend research results for {vehicle}; editorial pillar: {pillar}.", "trusted_automotive_search"))
    # NHTSA is the controlled universal fallback for vehicles whose manufacturer site is
    # unknown or unavailable. It is deliberately last.
    candidates.append(("https://www.nhtsa.gov/vehicle-safety", f"NHTSA vehicle-safety information reference for {vehicle}.", "regulatory_fallback"))
    return candidates


def discover_sources(*, vehicle: str, pillar: str, target_scenes: list[int]) -> list[dict]:
    scenes = sorted({int(number) for number in target_scenes if 1 <= int(number) <= 25})
    if not scenes:
        return []

    vehicle_name = vehicle.strip() or "featured vehicle"
    exact = MODEL_SOURCES.get(vehicle_name)
    brand = _find_brand(vehicle_name)
    candidates = []
    if exact:
        candidates.append((exact[0], exact[1], "official_model"))
    candidates.extend(_provider_candidates(vehicle_name, pillar, brand))

    result: list[dict] = []
    seen: set[str] = set()
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_text(vehicle_name)).strip("-")[:50] or "vehicle"
    for index, (url, claim, source_type) in enumerate(candidates, 1):
        if url in seen:
            continue
        seen.add(url)
        result.append({
            "id": f"provider-{slug}-{index}",
            "url": url,
            "claim": claim,
            "authority": "manufacturer / trusted automotive / NHTSA",
            "scene_numbers": scenes,
            "source_type": "automotive_information_provider",
            "provider_role": source_type,
        })
    return result


__all__ = ["discover_sources"]
