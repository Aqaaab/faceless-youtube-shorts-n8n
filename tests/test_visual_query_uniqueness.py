from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from story_pipeline import _repair_duplicate_queries, _visual_query_ok, validate_story


class VisualQueryUniquenessTests(unittest.TestCase):
    def _scene(self, query: str, index: int) -> dict:
        return {
            "text_en": (
                f"This automotive scene explains how the engine system works in a modern vehicle and why the component matters "
                f"for performance and reliability in practical driving conditions during daily road use, highway acceleration, "
                f"thermal management, mechanical response, fuel efficiency, and long term ownership expectations for drivers {index}."
            ),
            "text_ar": "هذا المشهد يشرح كيفية عمل نظام المحرك في سيارة حديثة ولماذا يؤثر هذا المكوّن في الأداء والاعتمادية أثناء القيادة.",
            "visual_subject": "BMW M5 F90 engine automotive component",
            "pexels_query": query,
            "beat": "hook" if index in (1, 7, 13, 19) else "development",
            "section": f"Engine system detail {index}",
            "technical_component": "engine system",
            "technical_flow": "engine airflow and performance",
            "technical_motion": "engine components moving",
            "failure_mode": "reduced engine response",
            "upgrade_note": "modern engine calibration",
            "source_claim": "Automotive engineering reference",
        }

    def test_duplicate_query_is_repaired_deterministically(self):
        scenes = [self._scene("BMW M5 F90 engine performance", i) for i in range(1, 4)]
        with patch.dict(os.environ, {"CAR_MODE": "1", "CAR_VEHICLE": "BMW M5 F90"}, clear=False):
            _repair_duplicate_queries(scenes)
        queries = [scene["pexels_query"].casefold() for scene in scenes]
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all(_visual_query_ok(scene) for scene in scenes))

    def test_empty_query_is_replaced(self):
        scenes = [self._scene("BMW M5 F90 engine performance", 1), self._scene("", 2)]
        with patch.dict(os.environ, {"CAR_MODE": "1", "CAR_VEHICLE": "BMW M5 F90"}, clear=False):
            _repair_duplicate_queries(scenes)
        self.assertTrue(scenes[1]["pexels_query"])
        self.assertNotEqual(scenes[0]["pexels_query"].casefold(), scenes[1]["pexels_query"].casefold())
        self.assertTrue(_visual_query_ok(scenes[1]))

    def test_validate_story_rejects_duplicate_queries_after_normalization(self):
        scenes = [self._scene(f"BMW M5 F90 engine scene {i}", i) for i in range(1, 26)]
        scenes[1]["pexels_query"] = scenes[0]["pexels_query"]
        story = {
            "title": "BMW M5 F90 Engine Technology Explained",
            "description": "Automotive engineering explained with practical car technology.",
            "tags": ["cars", "automotive", "BMW"],
            "scenes": scenes,
        }
        with patch.dict(os.environ, {"CAR_MODE": "1"}, clear=False):
            with self.assertRaisesRegex(ValueError, "duplicate Pexels query"):
                validate_story(story)


if __name__ == "__main__":
    unittest.main()
