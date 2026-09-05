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

    def test_source_target_covers_every_scene(self):
        story = self._story()
        self.assertEqual(source_enrichment._source_target_scenes(story), list(range(1, 26)))

    def test_existing_trusted_source_for_one_scene_does_not_silently_pass(self):
        story = self._story()
        story["sources"] = [{
            "id": "src-01",
            "url": "https://www.chevrolet.com/",
            "claim": "Chevrolet Corvette technical reference",
            "scene_numbers": [1],
        }]
        with patch.dict(source_enrichment.os.environ, {"CAR_VEHICLE": "Chevrolet Corvette C8"}, clear=False):
            with patch.object(source_enrichment, "_llm_recovery", return_value=[]), patch.object(source_enrichment, "_web_recovery", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "unable to map trusted sources"):
                    source_enrichment._build_sources(story)

    def test_corvette_official_seed_recovers_complete_coverage_when_dynamic_sources_fail(self):
        story = self._story()
        with patch.dict(source_enrichment.os.environ, {"CAR_VEHICLE": "Chevrolet Corvette C8"}, clear=False):
            with patch.object(source_enrichment, "_llm_recovery", return_value=[]), patch.object(source_enrichment, "_web_recovery", return_value=[]):
                sources = source_enrichment._build_sources(story)
        self.assertGreaterEqual(len(sources), 1)
        self.assertTrue(all(source["source_type"] == "trusted_official_seed" for source in sources))
        covered = {number for source in sources for number in source["scene_numbers"]}
        self.assertEqual(covered, set(range(1, 26)))
        self.assertEqual(story["scenes"][0]["source_id"], sources[0]["id"])
        self.assertEqual(story["scenes"][24]["source_id"], sources[0]["id"])

    def test_unknown_vehicle_without_sources_fails_closed(self):
        story = self._story()
        with patch.dict(source_enrichment.os.environ, {"CAR_VEHICLE": "Unknown Experimental Vehicle"}, clear=False):
            with patch.object(source_enrichment, "_llm_recovery", return_value=[]), patch.object(source_enrichment, "_web_recovery", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "unable to map trusted sources"):
                    source_enrichment._build_sources(story)

    def test_remote_verification_rejects_redirect_to_untrusted_domain(self):
        class Response:
            status = 200
            def geturl(self):
                return "https://evil.example/redirected"
            @property
            def headers(self):
                return {"Content-Type": "text/html"}
            def __enter__(self): return self
            def __exit__(self, *args): return False

        with patch.dict(source_enrichment.os.environ, {"SOURCE_VERIFY_REMOTE": "1"}, clear=False):
            source_enrichment.VERIFY_REMOTE = True
            with patch.object(source_enrichment.urllib.request, "urlopen", return_value=Response()):
                self.assertIsNone(source_enrichment._verify_source_url("https://www.chevrolet.com/example", {"www.chevrolet.com"}))
            source_enrichment.VERIFY_REMOTE = False


if __name__ == "__main__":
    unittest.main()
