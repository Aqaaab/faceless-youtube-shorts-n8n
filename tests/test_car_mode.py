from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from car_content_gate import _story_is_automotive
from car_shorts_pipeline import build_shorts


class CarModeTests(unittest.TestCase):
    def _story(self) -> dict:
        scenes = []
        for i in range(25):
            scenes.append({
                "text_en": f"This car engineering scene explains how the engine system works in a modern vehicle and why the component matters for performance and reliability {i}.",
                "text_ar": "يوضح هذا المشهد كيف يعمل نظام المحرك في سيارة حديثة ولماذا يؤثر هذا المكوّن في الأداء والاعتمادية.",
                "visual_subject": "modern car engine automotive component",
                "pexels_query": "modern car engine automotive",
                "beat": "hook" if i in (0, 6, 12, 18) else "development",
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

    def test_four_shorts_are_automotive(self):
        shorts = build_shorts(self._story())
        self.assertEqual(len(shorts), 4)
        self.assertEqual([x["scene_start"] for x in shorts], [1, 7, 13, 19])
        for short in shorts:
            self.assertIn("#Cars", short["description"])
            self.assertNotIn("#History", short["description"])


if __name__ == "__main__":
    unittest.main()
