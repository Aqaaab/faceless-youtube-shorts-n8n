import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        c = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
        self.assertEqual(c["niche"]["name"], "cars")
        self.assertEqual(c["niche"]["format"], "automotive encyclopedia")
        self.assertEqual(c["primary"]["name"], "Odysseus")
        self.assertEqual(c["production"]["long_video_count"], 1)
        self.assertEqual(c["production"]["short_count"], 4)
        self.assertEqual(c["production"]["long_duration_seconds"], {"min": 420, "max": 900})
        self.assertEqual(c["production"]["short_duration_seconds"], {"min": 28, "max": 59})
        self.assertEqual(c["production"]["short_resolution"], [1080, 1920])
        self.assertTrue(c["episode"]["master_is_source_of_truth"])
        self.assertTrue(c["episode"]["shorts_derived_from_master"])
        self.assertTrue(c["rules"]["automotive_only"])
        self.assertTrue(c["rules"]["pexels_is_only_external_footage_source"])

    def test_gateway_defaults_and_retry_contract(self):
        from odysseus_gateway import GEMINI_DEFAULT_MODEL, GEMINI_FALLBACK_MODELS, _gemini_models
        self.assertEqual(GEMINI_DEFAULT_MODEL, "gemini-3.7-flash")
        self.assertIn(GEMINI_DEFAULT_MODEL, GEMINI_FALLBACK_MODELS)
        models = _gemini_models()
        self.assertEqual(models[0], GEMINI_DEFAULT_MODEL)
        self.assertEqual(len(models), len(set(models)))
        self.assertEqual(set(models), set(GEMINI_FALLBACK_MODELS))
        with patch.dict("os.environ", {"GEMINI_MODEL": "custom-model", "GEMINI_FALLBACK_MODELS": "a,b,a"}, clear=False):
            self.assertEqual(_gemini_models(), ["custom-model", "a", "b"])

    def test_story_word_counter(self):
        from story_pipeline import words
        self.assertEqual(words("one two three"), 3)
        self.assertEqual(words("hello, world! 42 times"), 3)

    def test_car_shorts_contract(self):
        from car_shorts_pipeline import build_shorts
        story = {
            "title": "Nissan GT-R Explained",
            "scenes": [
                {
                    "id": i,
                    "beat": "hook" if i == 0 else "setup",
                    "text_en": f"This automotive engine scene explains the car and its mechanical system in detail for viewers. Scene {i}.",
                    "visual_subject": "sports car automotive footage",
                    "pexels_query": f"sports car engine automotive scene {i}",
                    "short_candidate_score": 60 - i,
                    "short_role": ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"][i % 4],
                }
                for i in range(25)
            ],
        }
        shorts = build_shorts(story)
        self.assertEqual(len(shorts), 4)
        self.assertEqual(len({s["scene_start"] for s in shorts}), 4)
        self.assertTrue(all(s["scene_start"] == s["scene_end"] for s in shorts))
        self.assertTrue(all(s["source_from_long_video"] for s in shorts))
        self.assertTrue(all(1 <= s["scene_start"] <= 25 for s in shorts))

    def test_renderer_has_vertical_subtitle_contract(self):
        source = (ROOT / "scripts/renderer.py").read_text(encoding="utf-8")
        self.assertIn("def make_vertical_ass", source)
        self.assertIn("PlayResX: 1080", source)
        self.assertIn("PlayResY: 1920", source)
        self.assertIn("baked_after_9x16_crop", source)
        self.assertIn("render_manifest.json", source)

    def test_production_uses_canonical_renderer(self):
        source = (ROOT / "scripts/production.py").read_text(encoding="utf-8")
        self.assertIn("from renderer import main as render", source)
        self.assertNotIn("renderer_safe", source)
        self.assertIn("episode_quality_gate", source)

    def test_episode_blueprint_contract(self):
        source = (ROOT / "scripts/episode_blueprint.py").read_text(encoding="utf-8")
        for field in ("technical_component", "technical_flow", "technical_motion", "failure_mode", "upgrade_note", "upgrade_requirements", "spec_status", "modified_estimate", "short_candidate_score"):
            self.assertIn(field, source)
        self.assertIn("episode_blueprint.json", source)
        self.assertIn("sources.json", source)

    def test_quality_gate_contract(self):
        source = (ROOT / "scripts/episode_quality_gate.py").read_text(encoding="utf-8")
        self.assertIn("NO_LEGACY_CONTENT=PASS", source)
        self.assertIn("FOUR_DERIVED_SHORTS=PASS", source)
        self.assertIn("SOURCE_REGISTER=PASS", source)
        self.assertIn("MEDIA_CONTRACT=PASS", source)

    def test_no_legacy_files(self):
        for rel in (
            "scripts/shorts_pipeline.py",
            "scripts/renderer_safe.py",
            ".github/workflows/odysseus-integration.yml",
            "scripts/provider_registry.py",
            "config/providers.json",
        ):
            self.assertFalse((ROOT / rel).exists(), f"legacy file still present: {rel}")

    def test_no_stale_provider_references(self):
        # Keep this test focused on active provider endpoints/config references.
        # Deleted legacy filenames are validated separately by test_no_legacy_files.
        forbidden = re.compile(r"config/providers\.json|/api/chat")
        scanned = []
        for base in (ROOT / "scripts", ROOT / "config", ROOT / ".github/workflows"):
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".yml", ".yaml", ".json"}:
                    scanned.append(path)
                    text = path.read_text(encoding="utf-8")
                    self.assertIsNone(forbidden.search(text), f"stale provider reference in {path}")
        self.assertTrue(scanned)

    def test_topic_selector_and_workflow_propagation_contract(self):
        from select_car_topic import main as select_topic

        with patch.dict("os.environ", {"GITHUB_RUN_NUMBER": "281", "CAR_MODE": "1", "ALLOW_CUSTOM_CAR_TOPIC": "0"}, clear=False), patch("builtins.print") as printer:
            directive = select_topic()

        self.assertIn("AUTOMOTIVE NICHE ONLY", directive)
        lines = [call.args[0] for call in printer.call_args_list if call.args]
        values = dict(line.split("=", 1) for line in lines if "=" in line)
        self.assertTrue(values.get("VIDEO_TOPIC"))
        self.assertTrue(values.get("CAR_VEHICLE"))
        self.assertTrue(values.get("CAR_TOPIC_PILLAR"))
        self.assertIn("Subaru WRX STI", values["CAR_VEHICLE"])

        workflow = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
        self.assertIn('cat "$topic_env" >> "$GITHUB_ENV"', workflow)
        self.assertIn("- name: Validate selected topic propagation", workflow)
        self.assertIn('test -n "$VIDEO_TOPIC"', workflow)
        self.assertNotIn('test -n "${VIDEO_TOPIC:-}"\n          test "${CAR_MODE:-0}" = "1"\n      - name: Install runtime', workflow)


if __name__ == "__main__":
    unittest.main()
