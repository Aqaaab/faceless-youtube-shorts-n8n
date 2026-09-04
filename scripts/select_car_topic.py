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


def main() -> str:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    topics = list(cfg.get("topics", []))
    pillars = list(cfg.get("pillars", []))
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

    pillar = pillars[index % len(pillars)] if pillars else "automotive engineering"
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
