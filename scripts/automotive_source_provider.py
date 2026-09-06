from __future__ import annotations

import re
from urllib.parse import quote

# Deterministic, credential-free automotive information provider.
# It deliberately returns only manufacturer/NHTSA domains already treated as trusted
# by source_enrichment.py. Remote reachability and redirect validation remain owned by
# source_enrichment.py so this provider never bypasses the existing provenance gate.

BRAND_SOURCE_CATALOG = {
    "nissan": ("https://www.nissan-global.com/EN/", "Official Nissan manufacturer and technology reference"),
    "toyota": ("https://global.toyota/en/", "Official Toyota manufacturer and technology reference"),
    "honda": ("https://global.honda/en/", "Official Honda manufacturer and engineering reference"),
    "ford": ("https://www.ford.com/", "Official Ford manufacturer and vehicle technology reference"),
    "chevrolet": ("https://www.chevrolet.com/", "Official Chevrolet vehicle and performance reference"),
    "porsche": ("https://www.porsche.com/international/", "Official Porsche vehicle and engineering reference"),
    "bmw": ("https://www.bmw.com/", "Official BMW vehicle and engineering reference"),
    "mercedes": ("https://www.mercedes-benz.com/", "Official Mercedes-Benz vehicle and engineering reference"),
    "audi": ("https://www.audi.com/", "Official Audi vehicle and technology reference"),
    "lamborghini": ("https://www.lamborghini.com/en-en/history/huracan-evo", "Official Lamborghini Huracan EVO technical, design and performance reference"),
    "ferrari": ("https://www.ferrari.com/en-EN/auto", "Official Ferrari road-car technical and design reference"),
    "mclaren": ("https://cars.mclaren.com/en", "Official McLaren road-car technical and engineering reference"),
    "mazda": ("https://www.mazda.com/en/", "Official Mazda vehicle and engineering reference"),
    "subaru": ("https://www.subaru.com/", "Official Subaru vehicle and engineering reference"),
    "mitsubishi": ("https://www.mitsubishi-motors.com/en/", "Official Mitsubishi Motors vehicle and engineering reference"),
    "volkswagen": ("https://www.volkswagen.com/", "Official Volkswagen vehicle and technology reference"),
    "hyundai": ("https://www.hyundai.com/worldwide/en", "Official Hyundai vehicle and technology reference"),
    "tesla": ("https://www.tesla.com/", "Official Tesla vehicle and technology reference"),
    "rimac": ("https://www.rimac-automobili.com/", "Official Rimac vehicle and electric-performance reference"),
}

# A small set of model-specific official pages where the model URL is stable and
# material to the current automotive catalogue. The generic brand source remains the
# fallback for every other vehicle so the provider is useful across the whole rotation.
MODEL_SOURCES = {
    "Lamborghini Huracan EVO": ("https://www.lamborghini.com/en-en/history/huracan-evo", "Official Lamborghini Huracan EVO technical, design and performance reference"),
    "Porsche 911 992 Carrera": ("https://www.porsche.com/international/models/911/carrera-models/911-carrera/", "Official Porsche 911 Carrera technical and performance reference"),
    "Chevrolet Corvette C8": ("https://www.chevrolet.com/performance1/previous-year/corvette/stingray", "Official Chevrolet Corvette Stingray performance and specification reference"),
}


def _find_brand(vehicle: str) -> str:
    value = vehicle.casefold()
    for brand in BRAND_SOURCE_CATALOG:
        if re.search(rf"\b{re.escape(brand)}\b", value):
            return brand
    # Mercedes-AMG is a frequent vehicle spelling but does not contain the word
    # "Mercedes-Benz". Keep the matching deterministic rather than relying on LLMs.
    if "mercedes-amg" in value or "mercedes benz" in value:
        return "mercedes"
    return ""


def discover_sources(*, vehicle: str, pillar: str, target_scenes: list[int]) -> list[dict]:
    scenes = [int(number) for number in target_scenes if 1 <= int(number) <= 25]
    if not scenes:
        return []

    exact = MODEL_SOURCES.get(vehicle.strip())
    brand = _find_brand(vehicle)
    selected = exact or BRAND_SOURCE_CATALOG.get(brand)
    if not selected:
        # NHTSA is intentionally used only as a controlled generic recovery anchor;
        # source_enrichment still verifies the URL and refuses unknown domains.
        selected = ("https://www.nhtsa.gov/vehicle-safety", "NHTSA vehicle-safety information reference")

    url, claim = selected
    source_id = "provider-" + re.sub(r"[^a-z0-9]+", "-", vehicle.casefold()).strip("-")[:50]
    return [
        {
            "id": source_id,
            "url": url,
            "claim": f"{claim}; editorial pillar: {pillar}.",
            "authority": "manufacturer / NHTSA",
            "scene_numbers": scenes,
            "source_type": "automotive_information_provider",
        }
    ]


__all__ = ["discover_sources"]
