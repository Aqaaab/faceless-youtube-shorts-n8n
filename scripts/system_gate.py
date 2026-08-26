from __future__ import annotations
import ast, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    production = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
    ody = json.loads((ROOT / "config/odysseus.json").read_text(encoding="utf-8"))
    required = [
        "scripts/odysseus_gateway.py",
        "scripts/story_pipeline.py",
        "scripts/shorts_pipeline.py",
        "scripts/renderer.py",
        "scripts/qa.py",
        "scripts/production.py",
        "scripts/system_gate.py",
    ]
    for rel in required:
        path = ROOT / rel
        assert path.is_file(), f"missing {rel}"
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"))

    assert production["primary"]["name"] == "Odysseus"
    assert production["production"]["long_video_count"] == 1
    assert production["production"]["short_count"] == 4
    assert production["production"]["long_duration_seconds"] == {"min": 420, "max": 900}
    assert production["production"]["short_duration_seconds"] == {"min": 28, "max": 59}
    assert production["production"]["short_resolution"] == [1080, 1920]

    assert ody["enabled"] is True
    assert ody["endpoint"] == "/api/v1/chat"
    assert ody["provider_keys_sent_to_odysseus"] is False
    assert ody["fallback"] is None

    workflow = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    assert "python scripts/production.py" in workflow
    assert "ODYSSEUS_GATEWAY_BASE_URL" in workflow
    assert "ODYSSEUS_GATEWAY_API_KEY" in workflow
    assert "PEXELS_API_KEY" in workflow
    assert "provider_registry.py" not in workflow
    assert "ai_router.py" not in workflow
    assert "/api/chat" not in workflow

    story = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
    assert "call_fallback" not in story
    assert "provider=Odysseus" in story

    print("SYSTEM_GATE=PASS")
    print("FILE_IMPORT_CONTRACT=PASS")
    print("ODYSSEUS_ONLY=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FOUR_SHORTS_CONTRACT=PASS")
