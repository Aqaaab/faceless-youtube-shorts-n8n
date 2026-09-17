from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE_SUFFIXES = {".py", ".yml", ".yaml", ".json"}
SOURCE_DIRS = (ROOT / "app", ROOT / "tests", ROOT / "scripts")


def _source_text() -> str:
    chunks = []
    for root in SOURCE_DIRS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_zero_cost_contract_workflow_and_artifact_fields():
    production = (ROOT / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
    assert 'ODYSSEUS_MAX_ATTEMPTS: "3"' in production
    assert 'ODYSSEUS_REQUEST_TIMEOUT: "60"' in production
    assert "fallback_count" in production
    assert "paid_services_used" in production
    assert "cost_usd" in production


def test_zero_cost_contract_source_has_no_provider_literal():
    needle = "open" + "router"
    assert needle not in _source_text().lower()
