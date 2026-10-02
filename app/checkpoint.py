from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE_NAME = ".ace_checkpoint.json"


def signature(topic: str, profile: str, pipeline_revision: str = "2026-10-production-v1") -> str:
    raw = json.dumps(
        {"topic": topic.strip(), "profile": profile.strip(), "revision": pipeline_revision},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def state_path(work: Path) -> Path:
    return work / STATE_NAME


def load(work: Path) -> dict:
    path = state_path(work)
    if not path.is_file():
        return {"version": 1, "stages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "stages": {}}
    return data if isinstance(data, dict) else {"version": 1, "stages": {}}


def save(work: Path, state: dict) -> None:
    work.mkdir(parents=True, exist_ok=True)
    path = state_path(work)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def begin(work: Path, topic: str, profile: str, reset: bool = False) -> dict:
    existing = load(work)
    sig = signature(topic, profile)
    if reset or existing.get("run_signature") not in (None, sig):
        existing = {"version": 1, "stages": {}}
    existing.update(
        {
            "version": 1,
            "run_signature": sig,
            "topic": topic,
            "profile": profile,
            "started_at": existing.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save(work, existing)
    return existing


def stage_done(state: dict, stage: str, artifacts: list[Path]) -> bool:
    info = state.get("stages", {}).get(stage)
    if not isinstance(info, dict) or info.get("status") != "done":
        return False
    return all(path.is_file() and path.stat().st_size > 0 for path in artifacts)


def mark(state: dict, work: Path, stage: str, status: str, artifacts: list[Path] | None = None, error: str | None = None) -> None:
    state.setdefault("stages", {})[stage] = {
        "status": status,
        "artifacts": [str(p) for p in (artifacts or [])],
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save(work, state)


def resume_enabled() -> bool:
    return os.getenv("ACE_RESUME", "1").strip() not in {"0", "false", "no"}
