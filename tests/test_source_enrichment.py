from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import source_enrichment


class SourceEnrichmentTests(unittest.TestCase):
    def _story(self):
        scenes = []
        for index in range(1, 26):
            scenes.append({
                "text_en": "The Corvette engine produces 495 horsepower using airflow and torque management." if index == 1 else "This automotive scene explains a vehicle mechanism clearly.",
                "technical_flow": "engine → drivetrain → wheels",
                "source_claim": "Vehicle-specific technical reference required." if index == 1 else "General automotive mechanism.",
            })
        return {"title": "Corvette C8 Engine", "scenes": scenes, "sources": []}

    def test_spec_scene_is_detected(self):
        story = self._story()
        self.assertEqual(source_enrichment._spec_scenes(story), [1])

    def test_existing_trusted_source_maps_scene(self):
        story = self._story()
        story["sources"] = [{
            "id": "src-01",
            "url": "https://www.chevrolet.com/",
            "claim": "Chevrolet Corvette technical reference",
            "scene_numbers": [1],
        }]
        with patch.dict(source_enrichment.os.environ, {"CAR_VEHICLE": "Chevrolet Corvette C8"}, clear=False):
            sources = source_enrichment._build_sources(story)
        self.assertEqual(len(sources), 1)
        self.assertEqual(story["scenes"][0]["source_id"], "src-01")

    def test_missing_sources_fail_closed(self):
        story = self._story()
        with patch.dict(source_enrichment.os.environ, {"CAR_VEHICLE": "Chevrolet Corvette C8"}, clear=False):
            with patch.object(source_enrichment, "_llm_recovery", return_value=[]), patch.object(source_enrichment, "_web_recovery", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "unable to map trusted sources"):
                    source_enrichment._build_sources(story)


if __name__ == "__main__":
    unittest.main()
