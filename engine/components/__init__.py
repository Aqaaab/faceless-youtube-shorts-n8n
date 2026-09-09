from __future__ import annotations

import json
from pathlib import Path


_REGISTRY_PATH = Path(__file__).with_name("registry.json")


def load_registry() -> dict:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def resolve_component(value: str) -> tuple[str | None, dict | None]:
    needle = value.strip().lower()
    for component_id, data in load_registry()["components"].items():
        if needle == component_id or needle in {a.lower() for a in data["aliases"]}:
            return component_id, data
    return None, None
