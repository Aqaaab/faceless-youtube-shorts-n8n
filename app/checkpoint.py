from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE_NAME = ".ace_checkpoint.json"
PIPELINE_REVISION = "2026-10-production-v4"
CHECKPOINT_VERSION = 3


def _source_revision() -> str:
    return os.getenv("ACE_SOURCE_REVISION") or os.getenv("GITHUB_SHA") or "local"


RUNTIME_FINGERPRINT_FILES = (
    "app/production_contract.py",
    "app/blender_automotive.py",
    "app/story_visuals.py",
    "app/vertical_visuals.py",
    "scripts/automotive_model.py",
    "scripts/automotive_shots.py",
    "scripts/automotive_world.py",
    "scripts/vehicle_rig.py",
    "scripts/blender_automotive_scene.py",
    "scripts/build_persistent_asset.py",
)

def _runtime_fingerprint() -> str:
    h = hashlib.sha256()
    root = Path(__file__).resolve().parents[1]
    for rel in RUNTIME_FINGERPRINT_FILES:
        path = root / rel
        h.update(rel.encode("utf-8"))
        if path.is_file():
            h.update(path.read_bytes())
        else:
            h.update(b"<missing>")
    return h.hexdigest()

def _file_fingerprint(path: Path) -> dict:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "size": path.stat().st_size}


def signature(topic: str, profile: str, pipeline_revision: str = PIPELINE_REVISION, source_revision: str | None = None) -> str:
    raw = json.dumps(
        {
            "topic": topic.strip(),
            "profile": profile.strip(),
            "revision": pipeline_revision,
            "source_revision": source_revision or _source_revision(),
        },
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
        return {"version": CHECKPOINT_VERSION, "stages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": CHECKPOINT_VERSION, "stages": {}}
    return data if isinstance(data, dict) else {"version": CHECKPOINT_VERSION, "stages": {}}


def save(work: Path, state: dict) -> None:
    work.mkdir(parents=True, exist_ok=True)
    path = state_path(work)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def begin(work: Path, topic: str, profile: str, reset: bool = False) -> dict:
    existing = load(work)
    source_revision = _source_revision()
    sig = signature(topic, profile, source_revision=source_revision)
    compatible = (
        existing.get("version") == CHECKPOINT_VERSION
        and existing.get("run_signature") == sig
        and existing.get("source_revision") == source_revision
    )
    if reset or not compatible:
        existing = {"version": CHECKPOINT_VERSION, "stages": {}}
    existing.update(
        {
            "version": CHECKPOINT_VERSION,
            "pipeline_revision": PIPELINE_REVISION,
            "source_revision": source_revision,
            "runtime_fingerprint": _runtime_fingerprint(),
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
    if state.get("version") != CHECKPOINT_VERSION:
        return False
    if state.get("pipeline_revision") != PIPELINE_REVISION:
        return False
    if state.get("source_revision") != _source_revision():
        return False
    if state.get("runtime_fingerprint") != _runtime_fingerprint():
        return False

    recorded = info.get("artifact_fingerprints", {})
    for path in artifacts:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        expected = recorded.get(str(path))
        if not isinstance(expected, dict):
            return False
        try:
            actual = _file_fingerprint(path)
        except OSError:
            return False
        if actual != expected:
            return False
    return True


def mark(state: dict, work: Path, stage: str, status: str, artifacts: list[Path] | None = None, error: str | None = None) -> None:
    paths = artifacts or []
    fingerprints = {}
    if status == "done":
        for path in paths:
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"cannot mark stage {stage} done: missing artifact {path}")
            fingerprints[str(path)] = _file_fingerprint(path)
    state.setdefault("stages", {})[stage] = {
        "status": status,
        "artifacts": [str(p) for p in paths],
        "artifact_fingerprints": fingerprints,
        "error": error,
        "pipeline_revision": PIPELINE_REVISION,
        "source_revision": _source_revision(),
        "runtime_fingerprint": _runtime_fingerprint(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save(work, state)


def resume_enabled() -> bool:
    return os.getenv("ACE_RESUME", "1").strip() not in {"0", "false", "no"}
