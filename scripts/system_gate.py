from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    production = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
    encyclopedia = json.loads((ROOT / "config/car_encyclopedia.json").read_text(encoding="utf-8"))
    ody = json.loads((ROOT / "config/odysseus.json").read_text(encoding="utf-8"))

    required = [
        "scripts/odysseus_gateway.py", "scripts/odysseus_smoke.py", "scripts/story_pipeline.py",
        "scripts/strict_story_gate.py", "scripts/car_content_gate.py", "scripts/select_car_topic.py",
        "scripts/episode_blueprint.py", "scripts/car_shorts_pipeline.py", "scripts/renderer.py",
        "scripts/caption_hardening.py", "scripts/technical_overlay.py", "scripts/episode_quality_gate.py",
        "scripts/qa.py", "scripts/production.py", "scripts/youtube_upload.py", "scripts/system_gate.py",
    ]
    for rel in required:
        path = ROOT / rel
        assert path.is_file(), f"missing {rel}"
        ast.parse(path.read_text(encoding="utf-8"))

    forbidden_files = [
        "scripts/shorts_pipeline.py", "scripts/renderer_safe.py", ".github/workflows/odysseus-integration.yml",
        "scripts/provider_registry.py", "config/providers.json",
    ]
    for rel in forbidden_files:
        assert not (ROOT / rel).exists(), f"legacy/unnecessary file remains: {rel}"

    assert production["version"] >= 8
    assert production["niche"]["name"] == "cars"
    assert production["niche"]["format"] == "automotive encyclopedia"
    assert production["niche"]["quality_gate"] == "scripts/episode_quality_gate.py"
    assert production["episode"]["master_is_source_of_truth"] is True
    assert production["episode"]["shorts_derived_from_master"] is True
    assert production["episode"]["source_mapping_required_for_numeric_specs"] is True
    assert production["rules"]["automotive_only"] is True
    assert production["rules"]["pexels_is_only_external_footage_source"] is True
    assert production["rules"]["technical_overlay_is_locally_generated"] is True
    assert production["rules"]["legacy_content_generation_disabled"] is True
    assert production["rules"]["canonical_renderer_only"] is True
    assert production["rules"]["final_quality_gate_required"] is True

    assert encyclopedia["mode"] == "car_encyclopedia"
    assert encyclopedia["long_video"]["scene_count"] == 25
    assert encyclopedia["shorts"]["count"] == 4
    assert encyclopedia["facts"]["numeric_specs_require_source"] is True
    assert encyclopedia["tuning"]["stock_vs_modified_comparison"] is True
    assert encyclopedia["tuning"]["modified_numbers_are_estimates"] is True
    assert encyclopedia["visual_style"]["external_media"] == "Pexels only"

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
    assert {408, 429, 500, 502, 503, 504, "transport"}.issubset(set(ody["fallback"]["after_statuses"]))

    daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    assert "python scripts/production.py" in daily
    assert "python scripts/system_gate.py" in daily
    assert "python -m unittest discover -s tests -v" in daily
    assert "CAR_MODE: '1'" in daily
    assert "PEXELS_API_KEY" in daily and "YOUTUBE_REFRESH_TOKEN" in daily
    assert "ODYSSEUS_GATEWAY_BASE_URL" in daily and "ODYSSEUS_GATEWAY_API_KEY" in daily
    for old in ("shorts_pipeline.py", "renderer_safe.py"):
        assert old not in daily

    production_py = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
    for required_call in ("strict_story()", "car_gate()", "blueprint()", "shorts()", "render()", "technical_overlay()", "qa(run)", "quality_gate()"):
        assert required_call in production_py
    assert "os.environ[\"CAR_MODE\"] = \"1\"" in production_py
    assert "from renderer import main as render" in production_py and "renderer_safe" not in production_py

    blueprint = (ROOT / "scripts/episode_blueprint.py").read_text(encoding="utf-8")
    for field in ("technical_component", "technical_flow", "technical_motion", "failure_mode", "upgrade_note", "upgrade_requirements", "spec_status", "modified_estimate", "short_candidate_score"):
        assert field in blueprint
    assert "episode_blueprint.json" in blueprint and "sources.json" in blueprint

    shorts = (ROOT / "scripts/car_shorts_pipeline.py").read_text(encoding="utf-8")
    assert "source_from_long_video" in shorts and "REQUIRED_SHORTS = 4" in shorts
    assert "scene_start" in shorts and "scene_end" in shorts

    overlay = (ROOT / "scripts/technical_overlay.py").read_text(encoding="utf-8")
    assert "animated automotive technical HUD" in overlay
    assert "technical_component" in overlay and "technical_flow" in overlay and "technical_motion" in overlay

    quality = (ROOT / "scripts/episode_quality_gate.py").read_text(encoding="utf-8")
    for marker in ("NO_LEGACY_CONTENT=PASS", "FOUR_DERIVED_SHORTS=PASS", "SOURCE_REGISTER=PASS", "MEDIA_CONTRACT=PASS"):
        assert marker in quality

    story = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
    assert "from odysseus_gateway import call, extract_json" in story
    assert "normalize_story" in story and "repair_scene" in story and "arabic_proofread" in story and "CAR_MODE" in story

    strict = (ROOT / "scripts/strict_story_gate.py").read_text(encoding="utf-8")
    assert "strict_pre_render_story_audit_and_repair" in strict and "visual_subject" in strict and "text_ar" in strict and "_local_contract" in strict

    hardening = (ROOT / "scripts/caption_hardening.py").read_text(encoding="utf-8")
    assert "SAFE_SHORT_MARGIN_LR" in hardening and "SAFE_SHORT_MARGIN_V" in hardening and "landscape" in hardening and "make_vertical_ass" in hardening

    gateway = (ROOT / "scripts/odysseus_gateway.py").read_text(encoding="utf-8")
    assert "RETRYABLE_HTTP" in gateway and "GEMINI_DEFAULT_MODEL" in gateway and "YOUTUBE_LLM_MODEL" in gateway and "_fallback_call" in gateway and "time.sleep" in gateway

    smoke = (ROOT / "scripts/odysseus_smoke.py").read_text(encoding="utf-8")
    assert "RETRYABLE_HTTP" in smoke and "ODYSSEUS_SMOKE_TIMEOUT" in smoke and "ODYSSEUS_SMOKE_RETRIES" in smoke

    print("SYSTEM_GATE=PASS")
    print("CANONICAL_CAR_PIPELINE=PASS")
    print("LEGACY_PATHS_REMOVED=PASS")
    print("EPISODE_BLUEPRINT=PASS")
    print("FOUR_DERIVED_SHORTS=PASS")
    print("TECHNICAL_HUD=PASS")
    print("CAPTION_SAFE_ZONE=PASS")
    print("ODYSSEUS_PRIMARY=PASS")
    print("YOUTUBE_FALLBACK_CHAIN=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FINAL_QUALITY_GATE=PASS")


if __name__ == "__main__":
    main()
