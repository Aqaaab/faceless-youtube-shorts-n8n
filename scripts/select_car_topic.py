from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "car_topics.json"
STOP = {"the", "complete", "car", "encyclopedia", "design", "cabin", "engine", "performance", "and", "a", "an", "of", "system"}


def _vehicle_from_topic(topic: str) -> str:
    head = topic.split("—", 1)[0].strip()
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", head)
    tokens = [t for t in tokens if t.casefold() not in STOP]
    return " ".join(tokens[:5]).strip()


def _pillar_for_topic(topic: str) -> str:
    """Choose an editorial pillar from the actual topic, not list-index coincidence."""
    text = topic.casefold()
    ev_word = bool(re.search(r"\bev\b", text))
    if ev_word or any(x in text for x in ("electric", "battery", "four-motor", "dual electric", "electric motor")):
        return "hybrid and EV technology"
    if any(x in text for x in ("turbo", "turbocharger", "airflow", "vr38dett", "s58", "b58", "coyote", "v8", "flat-six", "k20c1", "2jz")):
        return "engine and powertrain"
    if any(x in text for x in ("brake", "suspension", "chassis", "handling", "differential", "awd system")):
        return "chassis, suspension and brakes"
    if any(x in text for x in ("aerodynamic", "aero", "downforce", "spoiler", "exterior", "design")):
        return "car design and aerodynamics"
    if any(x in text for x in ("tuning", "upgrade", "performance", "competitor", "track")):
        return "performance and handling"
    if any(x in text for x in ("ownership", "reliability", "maintenance")):
        return "ownership technology and reliability"
    if any(x in text for x in ("motorsport", "rally", "racing")):
        return "motorsport-derived technology"
    return "car engineering"


def main() -> str:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    topics = list(cfg.get("topics", []))
    if not topics:
        raise RuntimeError("CAR_TOPIC_SELECTOR: no automotive topics configured")

    explicit = str(os.getenv("VIDEO_TOPIC", "")).strip()
    if explicit and os.getenv("ALLOW_CUSTOM_CAR_TOPIC", "0") == "1":
        topic = explicit
    else:
        raw_index = os.getenv("GITHUB_RUN_NUMBER") or os.getenv("CAR_TOPIC_INDEX")
        if raw_index:
            try:
                index = int(raw_index) % len(topics)
            except ValueError:
                index = 0
        else:
            index = datetime.now(timezone.utc).timetuple().tm_yday % len(topics)
        topic = topics[index]

    pillar = _pillar_for_topic(topic)
    vehicle = _vehicle_from_topic(topic) or "featured car"
    directive = (
        "AUTOMOTIVE NICHE ONLY. ONE VEHICLE PER EPISODE. Do not generate history, politics, general mystery, or unrelated topics. "
        f"Featured vehicle: {vehicle}. Editorial pillar: {pillar}. Episode topic: {topic}."
    )
    print(f"VIDEO_TOPIC={directive}")
    print(f"CAR_VEHICLE={vehicle}")
    print(f"CAR_TOPIC_PILLAR={pillar}")
    return directive


if __name__ == "__main__":
    main()
