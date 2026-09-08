from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        production_cfg = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
        car_cfg = json.loads((ROOT / "config/car_encyclopedia.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(production_cfg["version"], 9)
        self.assertEqual(production_cfg["niche"]["name"], "cars")
        self.assertEqual(production_cfg["niche"]["format"], "automotive encyclopedia")
        self.assertEqual(production_cfg["niche"]["config"], "config/car_encyclopedia.json")
        self.assertEqual(production_cfg["niche"]["topic_source"], "config/car_topics.json")
        self.assertEqual(production_cfg["niche"]["topic_selector"], "scripts/select_car_topic.py")
        self.assertEqual(production_cfg["niche"]["content_gate"], "scripts/car_content_gate.py")
        self.assertEqual(production_cfg["niche"]["episode_blueprint"], "scripts/episode_blueprint.py")
        self.assertEqual(production_cfg["niche"]["shorts_pipeline"], "scripts/car_shorts_pipeline.py")
        self.assertEqual(production_cfg["niche"]["technical_overlay"], "scripts/technical_overlay.py")
        self.assertEqual(production_cfg["niche"]["quality_gate"], "scripts/episode_quality_gate.py")
        episode = production_cfg["episode"]
        self.assertTrue(episode["master_is_source_of_truth"])
        self.assertTrue(episode["long_form_is_primary"])
        self.assertTrue(episode["shorts_derived_from_master"])
        self.assertTrue(episode["technical_visual_explanations"])
        self.assertTrue(episode["source_register"])
        self.assertTrue(episode["source_mapping_required_for_numeric_specs"])
        self.assertTrue(episode["stock_vs_modified_estimates_labeled"])
        primary = production_cfg["primary"]
        self.assertEqual(primary["name"], "Odysseus")
        self.assertEqual(primary["mode"], "http_gateway")
        self.assertEqual(primary["model_env"], "ODYSSEUS_STORY_MODEL")
        fallback = production_cfg["fallback"]
        self.assertEqual(fallback["order"], ["YOUTUBE_LLM", "GEMINI"])
        self.assertTrue(fallback["only_after_primary_failure"])
        self.assertTrue(fallback["provider_keys_stay_in_youtube"])
        production = production_cfg["production"]
        self.assertEqual(production["long_video_count"], 1)
        self.assertEqual(production["long_duration_seconds"], {"min": 420, "max": 900})
        self.assertFalse(production["long_artificial_padding"])
        self.assertEqual(production["short_count"], 4)
        self.assertEqual(production["short_duration_seconds"], {"min": 28, "max": 59})
        self.assertEqual(production["short_master_scene_window"], 2)
        self.assertFalse(production["short_artificial_padding"])
        self.assertEqual(production["short_resolution"], [1080, 1920])
        self.assertEqual(production["short_fps"], 30)
        self.assertEqual(production["long_scene_count"], 25)
        rules = production_cfg["rules"]
        for key in (
            "no_provider_keys_to_odysseus", "skip_disabled_providers", "fail_closed_on_primary_misconfiguration",
            "fallback_only_after_primary_failure", "fallback_never_skips_task", "preserve_provider_in_output",
            "niche_gate_required", "automotive_only", "shorts_must_reference_master_scenes", "shorts_must_be_unique",
            "shorts_use_two_scene_windows", "pexels_is_only_external_footage_source", "technical_overlay_is_locally_generated",
            "source_claims_must_not_be_invented", "legacy_content_generation_disabled", "canonical_renderer_only",
            "natural_duration_required", "no_frozen_frame_extension", "numeric_contract_centralized", "final_quality_gate_required",
        ):
            self.assertTrue(rules[key])
        daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
        recovery = (ROOT / ".github/workflows/production-recovery.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/production.py", daily)
        self.assertIn("python scripts/production.py", recovery)
        self.assertIn("python scripts/system_gate.py", daily)
        self.assertIn("CAR_MODE: '1'", daily)
        self.assertIn("CAR_MODE: '1'", recovery)
        self.assertIn("PEXELS_API_KEY", daily)
        self.assertIn("YOUTUBE_REFRESH_TOKEN", daily)
        self.assertIn("ODYSSEUS_GATEWAY_BASE_URL", daily)
        self.assertIn("ODYSSEUS_GATEWAY_API_KEY", daily)
        self.assertIn("workflow_run:", daily)
        self.assertIn("workflows: [Car Encyclopedia CI]", daily)
        self.assertIn("types: [completed]", daily)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", daily)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", daily)
        self.assertIn("github.event.workflow_run.event == 'push'", daily)
        self.assertIn("startsWith(github.event.workflow_run.head_commit.message, '[run-production]')", daily)
        self.assertNotIn("schedule:", daily)
        self.assertNotIn("cron:", daily)
        self.assertNotIn("push:", daily)
        self.assertIn("workflow_run:", recovery)
        self.assertIn("workflows: [Daily Production]", recovery)
        self.assertIn("types: [completed]", recovery)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", recovery)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", recovery)
        self.assertNotIn("workflows: [Car Encyclopedia CI]", recovery)
        self.assertNotIn("push:", recovery)
        self.assertNotIn("workflow_dispatch:", recovery)
        production_py = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
        for required_marker in (
            'run_gate("MANIFEST_HARDENING", harden_manifest, run)',
            'run_gate("PRODUCTION_QA", qa, run)',
            'run_gate("EPISODE_QUALITY_GATE", quality_gate)',
        ):
            self.assertIn(required_marker, production_py)
        for required_import in (
            "from strict_story_gate import main as strict_story",
            "from car_content_gate import main as car_gate",
            "from episode_blueprint import main as blueprint",
            "from car_shorts_pipeline import main as shorts",
            "from renderer import main as render",
            "from technical_overlay import main as technical_overlay",
        ):
            self.assertIn(required_import, production_py)
        self.assertIn('os.environ["CAR_MODE"] = "1"', production_py)
        self.assertIn("contract_hardening", production_py)
        required_files = [
            "config/car_encyclopedia.json", "config/car_topics.json", "scripts/car_content_gate.py",
            "scripts/car_shorts_pipeline.py", "scripts/episode_blueprint.py", "scripts/episode_quality_gate.py",
            "scripts/technical_overlay.py", "scripts/numeric_contract.py", "scripts/contract_hardening.py",
            "scripts/final_gate_runner.py",
        ]
        for rel in required_files:
            self.assertTrue((ROOT / rel).is_file(), f"required automotive file missing: {rel}")
        legacy_provider_config = "/".join(("config", "providers.json"))
        for rel in [
            "scripts/shorts_pipeline.py", "scripts/renderer_safe.py", ".github/workflows/odysseus-integration.yml",
            "scripts/provider_registry.py", legacy_provider_config, "scripts/post_car_numeric_repair.py",
        ]:
            self.assertFalse((ROOT / rel).exists(), f"legacy/redundant file remains: {rel}")
        for section in ["long_video", "shorts", "visual_style", "facts", "tuning", "quality", "safety"]:
            self.assertIn(section, car_cfg)
        self.assertEqual(car_cfg["long_video"]["scene_count"], 25)
        self.assertEqual(car_cfg["shorts"]["count"], 4)
        self.assertEqual(car_cfg["shorts"]["duration_seconds"]["min"], 28)
        self.assertEqual(car_cfg["shorts"]["duration_seconds"]["max"], 59)
        self.assertEqual(car_cfg["visual_style"]["external_media"], "Pexels only")
        self.assertTrue(car_cfg["facts"]["numeric_specs_require_source"])
        self.assertTrue(car_cfg["facts"]["source_register_required"])
        self.assertTrue(car_cfg["quality"]["master_is_source_of_truth"])
        self.assertTrue(car_cfg["quality"]["shorts_are_derived"])
        self.assertTrue(car_cfg["quality"]["automotive_only"])
        self.assertTrue(car_cfg["quality"]["fail_closed"])

    def test_topic_selector_and_workflow_propagation_contract(self):
        from scripts.select_car_topic import main as select_topic
        with patch.dict("os.environ", {"GITHUB_RUN_NUMBER": "281", "CAR_MODE": "1", "ALLOW_CUSTOM_CAR_TOPIC": "0"}, clear=False), patch("builtins.print") as printer:
            directive = select_topic()
        self.assertIn("AUTOMOTIVE NICHE ONLY", directive)
        lines = [call.args[0] for call in printer.call_args_list if call.args]
        values = dict(line.split("=", 1) for line in lines if "=" in line)
        self.assertTrue(values.get("VIDEO_TOPIC")); self.assertTrue(values.get("CAR_VEHICLE")); self.assertTrue(values.get("CAR_TOPIC_PILLAR"))
        self.assertIn("Subaru WRX STI", values["CAR_VEHICLE"])
        daily = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
        recovery = (ROOT / ".github/workflows/production-recovery.yml").read_text(encoding="utf-8")
        self.assertIn('cat "$topic_env" >> "$GITHUB_ENV"', daily)
        self.assertIn("- name: Validate selected topic propagation", daily)
        self.assertNotIn("push:", daily)
        self.assertIn("workflows: [Daily Production]", recovery)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", recovery)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", recovery)
        self.assertNotIn("github.event.workflow_run.event == 'push'", recovery)
        self.assertNotIn("startsWith(github.event.workflow_run.head_commit.message, '[run-production]')", recovery)
        self.assertIn("Publish master + four derived Shorts", recovery)


if __name__ == "__main__":
    unittest.main()
