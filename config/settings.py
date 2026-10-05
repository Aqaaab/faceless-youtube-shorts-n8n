"""Central runtime settings with environment-backed defaults."""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(os.getenv("ENGINE_ROOT", "."))
RUN = BASE / "work"


def get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value


def get_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def get_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
