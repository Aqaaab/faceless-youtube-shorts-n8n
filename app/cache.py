from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = Path(os.getenv("ACE_CACHE_DIR", str(ROOT / ".ace_cache")))
CACHE_CONTRACT_VERSION = "wangp-cache-v1"


def stable_key(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_file(namespace: str, key: str, suffix: str) -> Path:
    path = CACHE_ROOT / namespace
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{key}{suffix}"


def scene_key(*, topic: str, profile: str, scene_id: int, duration: float, aspect_ratio: str,
              model_type: str, prompt: str, reference_id: str, seed: int, contract: str = CACHE_CONTRACT_VERSION) -> str:
    return stable_key(contract, topic.strip(), profile.strip(), scene_id, round(float(duration), 3), aspect_ratio,
                      model_type, prompt, reference_id, seed)


def restore_file(namespace: str, key: str, suffix: str, target: Path) -> bool:
    source = cache_file(namespace, key, suffix)
    if not source.is_file() or source.stat().st_size == 0:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def store_file(namespace: str, key: str, suffix: str, source: Path) -> Path:
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(source)
    target = cache_file(namespace, key, suffix)
    shutil.copy2(source, target)
    return target
