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
    assert production["fallback"]["order"] == ["YOUTUBE_LLM", "GEMINI"]
    assert production["fallback"]["only_after_primary_failure"] is True

    assert ody["enabled"] is True
    assert ody["endpoint"] == "/api/v1/chat"
    assert ody["provider_keys_sent_to_odysseus"] is False
    assert ody["fallback"]["managed_by"] == "youtube_runtime"
    assert ody["fallback"]["order"] == ["YOUTUBE_LLM", "GEMINI"]

    workflow = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    assert "python scripts/production.py" in workflow
    assert "ODYSSEUS_GATEWAY_BASE_URL" in workflow
    assert "ODYSSEUS_GATEWAY_API_KEY" in workflow
    assert "PEXELS_API_KEY" in workflow
    assert "GEMINI_API_KEY" in workflow

    story = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
    assert "body=call(message,model=model)" in story
    assert "story['provider']=body.get('provider','Odysseus')" in story

    gateway = (ROOT / "scripts/odysseus_gateway.py").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" in gateway
    assert "YOUTUBE_LLM_API_KEY" in gateway
    assert "if e.code == 503 and _has_fallback()" in gateway

    print("SYSTEM_GATE=PASS")
    print("FILE_IMPORT_CONTRACT=PASS")
    print("ODYSSEUS_PRIMARY=PASS")
    print("YOUTUBE_FALLBACK_CHAIN=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FOUR_SHORTS_CONTRACT=PASS")


if __name__ == "__main__":
    main()
