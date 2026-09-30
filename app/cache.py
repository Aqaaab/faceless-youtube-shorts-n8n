from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = Path(os.getenv("ACE_CACHE_DIR", str(ROOT / ".ace_cache")))


def stable_key(*parts: object) -> str:
    payload = json.dumps([str(p) for p in parts], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_file(namespace: str, key: str, suffix: str) -> Path:
    path = CACHE_ROOT / namespace
    path.mkdir(parents=True, exist_ok=True)
    safe_suffix = suffix if suffix.startswith(".") else "." + suffix
    return path / f"{key}{safe_suffix}"


def copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=target.name + ".", dir=target.parent, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        shutil.copy2(source, tmp)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def restore_file(namespace: str, key: str, suffix: str, target: Path) -> bool:
    source = cache_file(namespace, key, suffix)
    if not source.is_file() or source.stat().st_size == 0:
        return False
    copy_atomic(source, target)
    return True


def store_file(namespace: str, key: str, suffix: str, source: Path) -> Path:
    target = cache_file(namespace, key, suffix)
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        copy_atomic(source, target)
    return target


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
