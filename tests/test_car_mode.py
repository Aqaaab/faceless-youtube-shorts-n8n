from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from car_content_gate import _harden_vehicle_identity, _story_is_automotive, _vehicle_anchor_count, _vehicle_visual_anchor_count
from car_shorts_pipeline import build_shorts


class CarModeTests(unittest.TestCase):
    def _story(self) -> dict:
        scenes = []
        for i in range(25):
            scenes.append({
                "text_en": f"This car engineering scene explains how the engine system works in a modern vehicle and why the component matters for performance and reliability {i}.",
                "text_ar": "يوضح هذا المشهد كيف يعمل نظام المحرك في سيارة حديثة ولماذا يؤثر هذا المكوّن في الأداء والاعتمادية.",
                "visual_subject": "modern car engine automotive component",
                "pexels_query": f"modern car engine automotive scene {i}",
                "beat": "hook" if i in (0, 6, 12, 18) else "development",
                "short_role": ["vehicle_hook", "technical_explainer", "performance_upgrade", "competitive_edge"][i % 4],
                "short_candidate_score": 60 - i,
            })
        return {
            "title": "How Turbocharging Changes a Performance Car",
            "description": "Automotive engineering explained with real car technology and practical details.",
            "tags": ["cars", "automotive", "car engineering"],
            "scenes": scenes,
        }

    def test_automotive_story_passes(self):
        with patch.dict(os.environ, {"CAR_VEHICLE": ""}, clear=False):
            self.assertTrue(_story_is_automotive(self._story()))

    def test_history_story_fails(self):
        story = self._story()
        story["title"] = "The Tea Tax Treachery"
        story["description"] = "Boston Tea Party history"
        story["tags"] = ["history", "boston tea party"]
        for scene in story["scenes"]:
            scene["text_en"] = "This historical scene explains the Boston Tea Party and a colonial event involving ships and parliament."
            scene["visual_subject"] = "historical ship"
            scene["pexels_query"] = "old colonial ship harbor"
        with patch.dict(os.environ, {"CAR_VEHICLE": ""}, clear=False):
            self.assertFalse(_story_is_automotive(story))

    def test_vehicle_identity_is_hardened_without_rewriting_narration(self):
        story = self._story()
        original_text = [scene["text_en"] for scene in story["scenes"]]
        with patch.dict(os.environ, {"CAR_VEHICLE": "Toyota GR Supra A90 A91"}, clear=False):
            self.assertEqual(_vehicle_anchor_count(story), 0)
            self.assertEqual(_vehicle_visual_anchor_count(story), 0)
            hardened = _harden_vehicle_identity(story)
            self.assertGreaterEqual(_vehicle_anchor_count(hardened), 8)
            self.assertGreaterEqual(_vehicle_visual_anchor_count(hardened), 8)
            self.assertEqual([scene["text_en"] for scene in hardened["scenes"]], original_text)
            self.assertTrue(_story_is_automotive(hardened))
            for scene in hardened["scenes"][:8]:
                self.assertIn("toyota", scene["visual_subject"].casefold())
                self.assertTrue(scene["pexels_query"])

    def test_vehicle_identity_uses_only_visual_fields(self):
        story = self._story()
        with patch.dict(os.environ, {"CAR_VEHICLE": "Toyota GR Supra A90 A91"}, clear=False):
            hardened = _harden_vehicle_identity(story)
            for scene in hardened["scenes"][:8]:
                self.assertIn("Toyota GR Supra A90 A91", scene["visual_subject"])
                self.assertIn("Toyota GR Supra A90 A91", scene["pexels_query"])

    def test_four_shorts_are_automotive_two_scene_windows(self):
        shorts = build_shorts(self._story())
        self.assertEqual(len(shorts), 4)
        self.assertEqual([(x["scene_start"], x["scene_end"]) for x in shorts], [(1, 2), (7, 8), (13, 14), (19, 20)])
        self.assertTrue(all(len(x["scenes"]) == 2 for x in shorts))
        self.assertTrue(all(x["source_from_long_video"] for x in shorts))


if __name__ == "__main__":
    unittest.main()
