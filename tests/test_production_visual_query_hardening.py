from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from production import _harden_story_visual_queries


class ProductionVisualQueryHardeningTests(unittest.TestCase):
    def _scene(self, query: str, index: int) -> dict:
        return {
            "visual_subject": "BMW M5 F90 engine automotive component",
            "pexels_query": query,
            "technical_component": f"engine component {index}",
            "section": "performance",
        }

    def test_hardening_repairs_duplicates_and_empty_queries_in_run_file(self):
        scenes = [
            self._scene("BMW M5 F90 engine performance", 1),
            self._scene("BMW M5 F90 engine performance", 2),
            self._scene("", 3),
        ] + [self._scene(f"BMW M5 F90 automotive scene {i}", i) for i in range(4, 26)]
        story = {"title": "BMW M5 F90", "description": "Automotive engineering", "tags": ["cars"], "scenes": scenes}
        with tempfile.TemporaryDirectory() as tmp_name:
            run = Path(tmp_name)
            (run / "long_story.json").write_text(json.dumps(story), encoding="utf-8")
            with patch.dict(os.environ, {"CAR_MODE": "1", "CAR_VEHICLE": "BMW M5 F90"}, clear=False):
                _harden_story_visual_queries(run)
            repaired = json.loads((run / "long_story.json").read_text(encoding="utf-8"))
        queries = [str(scene.get("pexels_query", "")).strip().casefold() for scene in repaired["scenes"]]
        self.assertEqual(len(queries), 25)
        self.assertEqual(len(queries), len(set(queries)))
        self.assertTrue(all(queries))

    def test_hardening_aborts_on_non_25_scene_story(self):
        with tempfile.TemporaryDirectory() as tmp_name:
            run = Path(tmp_name)
            (run / "long_story.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid 25-scene story"):
                _harden_story_visual_queries(run)


if __name__ == "__main__":
    unittest.main()
