from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))
SPEC_RE = re.compile(r"\b(?:horsepower|hp|bhp|ps|nm|lb-ft|0-60|0\s*(?:to|-|–)\s*60|quarter mile|top speed|displacement|liter engine|litre engine|cubic|rpm|compression ratio|weight|curb weight)\b", re.I)
CAR_RE = re.compile(r"\b(?:car|cars|automotive|automobile|vehicle|engine|turbo|brake|tire|wheel|suspension|differential|cooling|radiator|battery|electric|hybrid|drivetrain|transmission|horsepower|torque)\b", re.I)
LEGACY_RE = re.compile(r"(?:history mystery|history facts|the hidden story|colonial|tea party|historical event|war story)", re.I)
ALLOWED_SOURCE_DOMAINS = {
    "nhtsa.gov", "www.nhtsa.gov", "epa.gov", "www.epa.gov", "iihs.org", "www.iihs.org",
    "sae.org", "www.sae.org", "ford.com", "www.ford.com", "toyota.com", "www.toyota.com",
    "bmw.com", "www.bmw.com", "mercedes-benz.com", "www.mercedes-benz.com", "porsche.com", "www.porsche.com",
    "nissan-global.com", "www.nissan-global.com", "nissanusa.com", "www.nissanusa.com",
    "honda.com", "www.honda.com", "chevrolet.com", "www.chevrolet.com", "hyundai.com", "www.hyundai.com",
    "kia.com", "www.kia.com", "subaru.com", "www.subaru.com", "mazda.com", "www.mazda.com",
    "volvocars.com", "www.volvocars.com", "audi.com", "www.audi.com", "jaguar.com", "www.jaguar.com",
    "landrover.com", "www.landrover.com", "lamborghini.com", "www.lamborghini.com", "ferrari.com", "www.ferrari.com",
    "mclaren.com", "www.mclaren.com", "mitsubishi-motors.com", "www.mitsubishi-motors.com", "volkswagen.com", "www.volkswagen.com",
    "tesla.com", "www.tesla.com", "rimac-automobili.com", "www.rimac-automobili.com",
    "motortrend.com", "www.motortrend.com", "caranddriver.com", "www.caranddriver.com",
    "edmunds.com", "www.edmunds.com", "hagerty.com", "www.hagerty.com",
}


def _load(name: str) -> dict:
    path = RUN / name
    if not path.is_file():
        raise RuntimeError(f"QUALITY_GATE: missing {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _duration(path: Path) -> float:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ], text=True)
    return float(raw.strip())


def _domain(url: str) -> str:
    return urlparse(url).netloc.casefold().split(":", 1)[0]


def _validate_sources(story: dict) -> None:
    sources = story.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("QUALITY_GATE: source register is empty")
    by_id: dict[str, dict] = {}
    mapped: dict[int, set[str]] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise RuntimeError("QUALITY_GATE: malformed source entry")
        source_id = str(item.get("id", "")).strip()
        url = str(item.get("url", "")).strip()
        claim = str(item.get("claim", "")).strip()
        if not source_id or not url.startswith("https://") or not claim:
            raise RuntimeError("QUALITY_GATE: every source needs id, https URL and claim")
        domain = _domain(url)
        if domain not in ALLOWED_SOURCE_DOMAINS:
            raise RuntimeError(f"QUALITY_GATE: source domain not allowlisted: {domain}")
        scene_numbers = item.get("scene_numbers", [])
        if not isinstance(scene_numbers, list) or not all(isinstance(x, int) and 1 <= x <= 25 for x in scene_numbers):
            raise RuntimeError("QUALITY_GATE: source scene_numbers must contain valid scene indexes")
        if source_id in by_id:
            raise RuntimeError(f"QUALITY_GATE: duplicate source id: {source_id}")
        by_id[source_id] = item
        for number in scene_numbers:
            mapped.setdefault(number, set()).add(source_id)

    for index, scene in enumerate(story.get("scenes", []), 1):
        text = " ".join(str(scene.get(k, "")) for k in ("text_en", "technical_flow", "source_claim"))
        if not SPEC_RE.search(text):
            continue
        source_ids = mapped.get(index, set())
        if not source_ids:
            raise RuntimeError(f"QUALITY_GATE: specification in scene {index} has no mapped trusted source")
        scene_source_id = str(scene.get("source_id", "")).strip()
        if not scene_source_id or scene_source_id not in source_ids:
            raise RuntimeError(f"QUALITY_GATE: specification in scene {index} has no valid source_id mapping")
        source_claim = str(scene.get("source_claim", "")).strip()
        if not source_claim:
            raise RuntimeError(f"QUALITY_GATE: specification in scene {index} is missing source_claim")


def _validate_story(story: dict) -> None:
    scenes = story.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("QUALITY_GATE: master must contain exactly 25 scenes")
    title = str(story.get("title", "")).strip()
    topic = str(os.getenv("VIDEO_TOPIC", ""))
    if not title or not CAR_RE.search(title + " " + topic):
        raise RuntimeError("QUALITY_GATE: master title/topic is not clearly automotive")
    seen_queries: set[str] = set()
    for index, scene in enumerate(scenes, 1):
        blob = " ".join(str(scene.get(k, "")) for k in ("text_en", "visual_subject", "pexels_query", "technical_component", "technical_flow", "section"))
        if LEGACY_RE.search(blob):
            raise RuntimeError(f"QUALITY_GATE: legacy non-automotive language detected in scene {index}")
        if not CAR_RE.search(blob):
            raise RuntimeError(f"QUALITY_GATE: scene {index} is not clearly automotive")
        query = re.sub(r"\s+", " ", str(scene.get("pexels_query", "")).strip()).casefold()
        if not query or query in seen_queries:
            raise RuntimeError(f"QUALITY_GATE: duplicate/empty Pexels query at scene {index}")
        seen_queries.add(query)
        for key in ("section", "technical_component", "technical_flow", "technical_motion", "failure_mode", "upgrade_note", "source_claim"):
            if not str(scene.get(key, "")).strip():
                raise RuntimeError(f"QUALITY_GATE: scene {index} missing {key}")


def _validate_shorts(plan: dict) -> None:
    shorts = plan.get("shorts")
    if not isinstance(shorts, list) or len(shorts) != 4:
        raise RuntimeError("QUALITY_GATE: exactly 4 Shorts are required")
    used_scenes: set[int] = set()
    roles: set[str] = set()
    for short in shorts:
        sid = int(short["id"])
        start = int(short["scene_start"])
        end = int(short["scene_end"])
        if not (1 <= start <= end <= 25) or start != end:
            raise RuntimeError(f"QUALITY_GATE: Short {sid} must map to exactly one master scene")
        if start in used_scenes:
            raise RuntimeError(f"QUALITY_GATE: Shorts reuse master scene {start}")
        used_scenes.add(start)
        role = str(short.get("role", "")).strip().casefold()
        if role:
            roles.add(role)
        if short.get("source_from_long_video") is not True:
            raise RuntimeError(f"QUALITY_GATE: Short {sid} is not marked derived from master")
        scene_blob = " ".join(str(x.get(k, "")) for x in short.get("scenes", []) for k in ("text_en", "visual_subject", "pexels_query"))
        if not CAR_RE.search(scene_blob):
            raise RuntimeError(f"QUALITY_GATE: Short {sid} is not automotive")
    expected = {"vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"}
    if roles and roles != expected:
        raise RuntimeError(f"QUALITY_GATE: Shorts roles mismatch: {sorted(roles)}")


def _validate_media(plan: dict) -> None:
    video = RUN / "video.mp4"
    if not video.is_file() or video.stat().st_size == 0:
        raise RuntimeError("QUALITY_GATE: master video missing or empty")
    duration = _duration(video)
    if not 420.0 <= duration <= 900.5:
        raise RuntimeError(f"QUALITY_GATE: master duration {duration:.2f}s outside 420-900s")
    for short in plan["shorts"]:
        sid = int(short["id"])
        path = RUN / "shorts" / f"short-{sid}.mp4"
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"QUALITY_GATE: Short {sid} missing or empty")
        duration = _duration(path)
        if not 28.0 <= duration <= 59.5:
            raise RuntimeError(f"QUALITY_GATE: Short {sid} duration {duration:.2f}s outside 28-59s")


def main() -> None:
    story = _load("long_story.json")
    blueprint = _load("episode_blueprint.json") if (RUN / "episode_blueprint.json").is_file() else story
    plan = _load("shorts_plan.json")
    _validate_story(story)
    if len(blueprint.get("scenes", [])) != 25:
        raise RuntimeError("QUALITY_GATE: episode blueprint must contain 25 scenes")
    _validate_sources(story)
    _validate_shorts(plan)
    _validate_media(plan)
    print("EPISODE_QUALITY_GATE=PASS")
    print("AUTOMOTIVE_ONLY=PASS")
    print("MASTER_25_SCENES=PASS")
    print("FOUR_DERIVED_SHORTS=PASS")
    print("SOURCE_REGISTER=PASS")
    print("NO_LEGACY_CONTENT=PASS")
    print("MEDIA_CONTRACT=PASS")


if __name__ == "__main__":
    main()
