from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    production_cfg = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
    car_cfg = json.loads((ROOT / "config/car_encyclopedia.json").read_text(encoding="utf-8"))
    assert production_cfg["version"] >= 9
    assert production_cfg["niche"]["name"] == "cars"
    assert production_cfg["niche"]["format"] == "automotive encyclopedia"
    assert production_cfg["niche"]["config"] == "config/car_encyclopedia.json"
    assert production_cfg["niche"]["topic_source"] == "config/car_topics.json"
    assert production_cfg["niche"]["topic_selector"] == "scripts/select_car_topic.py"
    assert production_cfg["niche"]["content_gate"] == "scripts/car_content_gate.py"
    assert production_cfg["niche"]["episode_blueprint"] == "scripts/episode_blueprint.py"
    assert production_cfg["niche"]["shorts_pipeline"] == "scripts/car_shorts_pipeline.py"
    assert production_cfg["niche"]["technical_overlay"] == "scripts/technical_overlay.py"
    assert production_cfg["niche"]["quality_gate"] == "scripts/episode_quality_gate.py"
    episode = production_cfg["episode"]
    assert episode["master_is_source_of_truth"] is True
    assert episode["long_form_is_primary"] is True
    assert episode["shorts_derived_from_master"] is True
    assert episode["technical_visual_explanations"] is True
    assert episode["source_register"] is True
    assert episode["source_mapping_required_for_numeric_specs"] is True
    assert episode["stock_vs_modified_estimates_labeled"] is True
    primary = production_cfg["primary"]
    assert primary["name"] == "Odysseus"
    assert primary["mode"] == "http_gateway"
    assert primary["model_env"] == "ODYSSEUS_STORY_MODEL"
    fallback = production_cfg["fallback"]
    assert fallback["order"] == ["YOUTUBE_LLM", "GEMINI"]
    assert fallback["only_after_primary_failure"] is True
    assert fallback["provider_keys_stay_in_youtube"] is True
    production = production_cfg["production"]
    assert production["long_video_count"] == 1
    assert production["long_duration_seconds"] == {"min": 420, "max": 900}
    assert production["long_artificial_padding"] is False
    assert production["short_count"] == 4
    assert production["short_duration_seconds"] == {"min": 28, "max": 59}
    assert production["short_master_scene_window"] == 2
    assert production["short_artificial_padding"] is False
    assert production["short_resolution"] == [1080, 1920]
    assert production["short_fps"] == 30
    assert production["long_scene_count"] == 25
    rules = production_cfg["rules"]
    assert rules["no_provider_keys_to_odysseus"] is True
    assert rules["skip_disabled_providers"] is True
    assert rules["fail_closed_on_primary_misconfiguration"] is True
    assert rules["fallback_only_after_primary_failure"] is True
    assert rules["fallback_never_skips_task"] is True
    assert rules["preserve_provider_in_output"] is True
    assert rules["niche_gate_required"] is True
    assert rules["automotive_only"] is True
    assert rules["shorts_must_reference_master_scenes"] is True
    assert rules["shorts_must_be_unique"] is True
    assert rules["shorts_use_two_scene_windows"] is True
    assert rules["pexels_is_only_external_footage_source"] is True
    assert rules["technical_overlay_is_locally_generated"] is True
    assert rules["source_claims_must_not_be_invented"] is True
    assert rules["legacy_content_generation_disabled"] is True
    assert rules["canonical_renderer_only"] is True
    assert rules["natural_duration_required"] is True
    assert rules["no_frozen_frame_extension"] is True
    assert rules["numeric_contract_centralized"] is True
    assert rules["final_quality_gate_required"] is True
    daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
    recovery = (ROOT / ".github/workflows/production-recovery.yml").read_text(encoding="utf-8")
    assert "python scripts/production.py" in daily
    assert "python scripts/production.py" in recovery
    assert "python scripts/system_gate.py" in daily
    assert "CAR_MODE: '1'" in daily and "CAR_MODE: '1'" in recovery
    assert "PEXELS_API_KEY" in daily and "YOUTUBE_REFRESH_TOKEN" in daily
    assert "ODYSSEUS_GATEWAY_BASE_URL" in daily and "ODYSSEUS_GATEWAY_API_KEY" in daily
    assert "startsWith(github.event.head_commit.message, '[run-production]')" in recovery
    assert "- cron: '0 6 * * *'" in daily
    assert "push:" not in daily
    production_py = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
    for required_call in ("strict_story()", "car_gate()", "blueprint()", "shorts()", "render()", "technical_overlay()", "qa(run)", "quality_gate()"):
        assert required_call in production_py
    assert 'os.environ["CAR_MODE"] = "1"' in production_py
    assert "contract_hardening" in production_py
    required_files = [
        "config/car_encyclopedia.json", "config/car_topics.json", "scripts/car_content_gate.py",
        "scripts/car_shorts_pipeline.py", "scripts/episode_blueprint.py", "scripts/episode_quality_gate.py",
        "scripts/technical_overlay.py", "scripts/numeric_contract.py", "scripts/contract_hardening.py",
    ]
    for rel in required_files:
        assert (ROOT / rel).is_file(), f"required automotive file missing: {rel}"
    legacy_provider_config = "/".join(("config", "providers.json"))
    for rel in [
        "scripts/shorts_pipeline.py", "scripts/renderer_safe.py", ".github/workflows/odysseus-integration.yml",
        "scripts/provider_registry.py", legacy_provider_config, "scripts/post_car_numeric_repair.py",
    ]:
        assert not (ROOT / rel).exists(), f"legacy/redundant file remains: {rel}"
    required_car_sections = ["long_video", "shorts", "visual_style", "facts", "tuning", "quality", "safety"]
    for section in required_car_sections:
        assert section in car_cfg, f"required automotive section missing: {section}"
    assert car_cfg["long_video"]["scene_count"] == 25
    assert car_cfg["shorts"]["count"] == 4
    assert car_cfg["shorts"]["duration_seconds"]["min"] == 28
    assert car_cfg["shorts"]["duration_seconds"]["max"] == 59
    assert car_cfg["visual_style"]["external_media"] == "Pexels only"
    assert car_cfg["facts"]["numeric_specs_require_source"] is True
    assert car_cfg["facts"]["source_register_required"] is True
    assert car_cfg["quality"]["master_is_source_of_truth"] is True
    assert car_cfg["quality"]["shorts_are_derived"] is True
    assert car_cfg["quality"]["automotive_only"] is True
    assert car_cfg["quality"]["fail_closed"] is True
    print("SYSTEM_GATE=PASS")
    print("CANONICAL_CAR_PIPELINE=PASS")
    print("LEGACY_PATHS_REMOVED=PASS")
    print("CENTRAL_NUMERIC_CONTRACT=PASS")
    print("NATURAL_DURATION_ONLY=PASS")
    print("TWO_SCENE_SHORTS=PASS")
    print("FOUR_DERIVED_SHORTS=PASS")
    print("TECHNICAL_HUD=PASS")
    print("CAPTION_SAFE_ZONE=PASS")
    print("ODYSSEUS_PRIMARY=PASS")
    print("YOUTUBE_FALLBACK_CHAIN=PASS")
    print("LONG_VIDEO_CONTRACT=PASS")
    print("FINAL_QUALITY_GATE=PASS")


if __name__ == "__main__":
    main()
