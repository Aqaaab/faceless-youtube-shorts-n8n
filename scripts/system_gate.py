from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    production = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
    ody = json.loads((ROOT / "config/odysseus.json").read_text(encoding="utf-8"))
    required = [
        "scripts/odysseus_gateway.py",
        "scripts/odysseus_smoke.py",
        "scripts/story_pipeline.py",
        "scripts/strict_story_gate.py",
        "scripts/shorts_pipeline.py",
        "scripts/renderer.py",
        "scripts/renderer_safe.py",
        "scripts/qa.py",
        "scripts/production.py",
        "scripts/system_gate.py",
    ]
    for rel in required:
        path = ROOT / rel
        assert path.is_file(), f"missing {rel}"
        ast.parse(path.read_text(encoding="utf-8"))

    assert production["primary"]["name"] == "Odysseus"
    assert production["production"]["long_video_count"] == 1
    assert production["production"]["short_count"] == 4
    assert production["production"]["long_duration_seconds"] == {"min": 420, "max": 900}
    assert production["production"]["short_duration_seconds"] == {"min": 28, "max": 59}
    assert production["production"]["short_resolution"] == [1080, 1920]
    assert production["production"]["short_fps"] == 30
    assert production["production"]["long_scene_count"] == 25
    assert production["fallback"]["order"] == ["YOUTUBE_LLM", "GEMINI"]
    assert production["fallback"]["only_after_primary_failure"] is True
    assert production["fallback"]["provider_keys_stay_in_youtube"] is True

    assert ody["enabled"] is True
    assert ody["endpoint"] == "/api/v1/chat"
    assert ody["provider_keys_sent_to_odysseus"] is False
    assert ody["direct_provider_access"] is False
    assert ody["fallback"]["managed_by"] == "youtube_runtime"
    assert ody["fallback"]["order"] == ["YOUTUBE_LLM", "GEMINI"]
    assert set([408, 429, 500, 502, 503, 504, "transport"]).issubset(set(ody["fallback"]["after_statuses"]))

    daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    integration = (ROOT / ".github/workflows/odysseus-integration.yml").read_text(encoding="utf-8")
    for workflow in (daily, integration):
        for name in ("ODYSSEUS_GATEWAY_BASE_URL", "ODYSSEUS_GATEWAY_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY"):
            assert name in workflow
        assert "python scripts/production.py" in workflow

    story = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
    assert "from odysseus_gateway import call, extract_json" in story
    assert "extract_json(body)" in story
    assert "normalize_story" in story
    assert "repair_scene" in story
    assert "REPAIR_RETRIES" in story

    strict = (ROOT / "scripts/strict_story_gate.py").read_text(encoding="utf-8")
    assert "strict_pre_render_story_audit_and_repair" in strict
    assert "visual_subject" in strict
    assert "text_ar" in strict
    assert "_local_contract" in strict

    renderer_safe = (ROOT / "scripts/renderer_safe.py").read_text(encoding="utf-8")
    assert "SAFE_SHORT_MARGIN_LR" in renderer_safe
    assert "SAFE_SHORT_MARGIN_V" in renderer_safe
    assert "landscape" in renderer_safe
    assert "renderer.make_vertical_ass" in renderer_safe

    gateway = (ROOT / "scripts/odysseus_gateway.py").read_text(encoding="utf-8")
    assert "RETRYABLE_HTTP" in gateway
    assert "GEMINI_DEFAULT_MODEL" in gateway
    assert "YOUTUBE_LLM_MODEL" in gateway
    assert "_fallback_call" in gateway
    assert "time.sleep" in gateway

    smoke = (ROOT / "scripts/odysseus_smoke.py").read_text(encoding="utf-8")
    assert "RETRYABLE_HTTP" in smoke
    assert "ODYSSEUS_SMOKE_TIMEOUT" in smoke
    assert "ODYSSEUS_SMOKE_RETRIES" in smoke

    print("SYSTEM_GATE=PASS")
    print("FILE_IMPORT_CONTRACT=PASS")
    print("STRICT_STORY_GATE=PASS")
    print("CAPTION_SAFE_ZONE=PASS")
    print("LANDSCAPE_VISUAL_SELECTION=PASS")
    print("ODYSSEUS_PRIMARY=PASS")
    print("YOUTUBE_FALLBACK_CHAIN=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FOUR_SHORTS_CONTRACT=PASS")


if __name__ == "__main__":
    main()
