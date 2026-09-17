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


def test_contract_zero_cost_01_no_forbidden_paid_route_in_source():
    needle = "open" + "router"
    assert needle not in _source_text().lower()


def test_contract_zero_cost_02_max_attempts_is_at_least_three():
    workflow = (ROOT / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
    assert 'ODYSSEUS_MAX_ATTEMPTS: "3"' in workflow
    assert 'ODYSSEUS_REQUEST_TIMEOUT: "60"' in workflow


def test_contract_zero_cost_03_zero_cost_fallback_contract_is_free_only():
    workflow = (ROOT / ".github" / "workflows" / "production.yml").read_text(encoding="utf-8")
    assert "fallback_count" in workflow
    assert "fallbacks" in workflow
    assert "cost_usd" in workflow
    assert "paid_services_used" in workflow
    assert "paid_models_allowed" in workflow
    assert "openrouter-free" in workflow


def test_contract_zero_cost_04_no_paid_api_keys_in_ci_or_source():
    text = _source_text().lower()
    key_names = (
        "open" + "router" + "_api_key",
        "open" + "ai" + "_api_key",
        "anthropic" + "_api_key",
        "cohere" + "_api_key",
    )
    for key_name in key_names:
        assert key_name not in text


def test_contract_zero_cost_05_invalid_json_retries(monkeypatch):
    from app import core

    class Response:
        status_code = 200
        headers = {}
        ok = True

        def __init__(self, content):
            self._content = content
            self.text = json.dumps(content)

        def json(self):
            return {"response": self._content}

    responses = iter([Response("not-json"), Response(json.dumps({"ok": True}))])
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setenv("ODYSSEUS_GATEWAY_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("ODYSSEUS_GATEWAY_API_KEY", "test")
    monkeypatch.setenv("ODYSSEUS_MAX_ATTEMPTS", "3")
    monkeypatch.setattr(core.requests, "post", post)
    monkeypatch.setattr(core.time, "sleep", lambda _: None)
    assert core.ask_odysseus("system", "user") == {"ok": True}
    assert len(calls) == 2
