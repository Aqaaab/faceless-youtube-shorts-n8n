import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from visual_generation import build_visual_prompt
from visual_plan import _mode


class VisualGenerationTests(unittest.TestCase):
    def test_prompt_locks_vehicle_identity_and_separate_overlay(self):
        prompt = build_visual_prompt({"vehicle": "2021 Subaru WRX STI", "visual_subject": "engine bay close-up", "technical_component": "Turbocharger"})
        self.assertIn("2021 Subaru WRX STI", prompt)
        self.assertIn("do not substitute another make or model", prompt.lower())
        self.assertIn("separate local technical overlay", prompt.lower())

    def test_scene_modes_are_visual_functions(self):
        self.assertEqual(_mode({"short_role": "vehicle_hook", "visual_subject": "vehicle identity"}, 1), "hero")
        self.assertEqual(_mode({"technical_component": "Turbocharger", "visual_subject": "turbo airflow"}, 8), "technical_animation")
        self.assertEqual(_mode({"technical_component": "EV battery", "visual_subject": "battery architecture"}, 12), "xray")


if __name__ == "__main__":
    unittest.main()
