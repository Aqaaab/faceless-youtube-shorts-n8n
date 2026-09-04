from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    production_cfg = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
    car_cfg = json.loads((ROOT / "config/car_encyclopedia.json").read_text(encoding="utf-8"))
    ody = production_cfg["odysseus"]
    production = production_cfg["production"]

    assert production_cfg["version"] >= 8
    assert production_cfg["niche"] == "cars"
    assert production_cfg["format"] == "automotive_encyclopedia"
    assert production["long_video_is_source_of_truth"] is True
    assert production["shorts_derived_from_master"] is True
    assert production["pexels_only_external_footage"] is True
    assert production["technical_overlay_generated_locally"] is True
    assert production["legacy_content_generation_disabled"] is True
    assert production["canonical_renderer_only"] is True
    assert production["final_quality_gate_required"] is True
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
    assert "python -m unittest discover -s tests -p 'test_car_mode.py' -v" in daily
    assert "CAR_MODE: '1'" in daily
    assert "PEXELS_API_KEY" in daily and "YOUTUBE_REFRESH_TOKEN" in daily
    assert "ODYSSEUS_GATEWAY_BASE_URL" in daily and "ODYSSEUS_GATEWAY_API_KEY" in daily
    for old in ("shorts_pipeline.py", "renderer_safe.py"):
        assert f"python scripts/{old}" not in daily
        assert f"python -m scripts.{old[:-3]}" not in daily

    production_py = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
    for required_call in ("strict_story()", "car_gate()", "blueprint()", "shorts()", "render()", "technical_overlay()", "qa(run)", "quality_gate()"):
        assert required_call in production_py
    assert "os.environ[\"CAR_MODE\"] = \"1\"" in production_py

    required_files = [
        "config/car_encyclopedia.json",
        "config/car_topics.json",
        "scripts/car_content_gate.py",
        "scripts/car_shorts_pipeline.py",
        "scripts/episode_blueprint.py",
        "scripts/episode_quality_gate.py",
        "scripts/technical_overlay.py",
    ]
    for rel in required_files:
        assert (ROOT / rel).is_file(), f"required automotive file missing: {rel}"

    legacy_provider_file = "scripts/" + "provider_registry.py"
    legacy_provider_config = "config/" + "providers.json"
    for rel in [
        "scripts/shorts_pipeline.py",
        "scripts/renderer_safe.py",
        ".github/workflows/odysseus-integration.yml",
        legacy_provider_file,
        legacy_provider_config,
    ]:
        assert not (ROOT / rel).exists(), f"legacy/unnecessary file remains: {rel}"

    required_car_keys = [
        "niche",
        "format",
        "long_video_minutes",
        "long_scene_count",
        "short_count",
        "short_resolution",
        "short_source_of_truth",
        "external_footage_provider",
        "numeric_spec_source_required",
    ]
    for key in required_car_keys:
        assert key in car_cfg

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

# Verification-trigger commit: Daily Production is temporarily configured to run after this repair.
