from __future__ import annotations

import sys
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import automotive_source_provider


class AutomotiveSourceProviderTests(unittest.TestCase):
    def test_lamborghini_model_source_covers_requested_scenes(self):
        sources = automotive_source_provider.discover_sources(
            vehicle="Lamborghini Huracan EVO",
            pillar="car design and aerodynamics",
            target_scenes=[2, 19, 20, 24, 25],
        )
        self.assertGreaterEqual(len(sources), 3)
        self.assertIn("lamborghini.com", sources[0]["url"])
        self.assertEqual(sources[0]["scene_numbers"], [2, 19, 20, 24, 25])
        self.assertEqual(sources[0]["source_type"], "automotive_information_provider")

    def test_random_ferrari_model_resolves_without_model_hardcoding(self):
        sources = automotive_source_provider.discover_sources(
            vehicle="Ferrari 488 GTB",
            pillar="engine and performance",
            target_scenes=[1, 7, 13, 21, 25],
        )
        self.assertGreaterEqual(len(sources), 3)
        self.assertIn("ferrari.com", sources[0]["url"])
        self.assertEqual(sources[0]["scene_numbers"], [1, 7, 13, 21, 25])

    def test_common_subbrand_alias_resolves_to_parent_source(self):
        sources = automotive_source_provider.discover_sources(
            vehicle="Mercedes-AMG GT 63",
            pillar="powertrain",
            target_scenes=[1, 2, 3],
        )
        self.assertGreaterEqual(len(sources), 3)
        self.assertTrue("mercedes-amg.com" in sources[0]["url"] or "mercedes-benz.com" in sources[0]["url"])

    def test_known_brand_has_no_llm_or_secret_dependency(self):
        sources = automotive_source_provider.discover_sources(
            vehicle="BMW M3 G80",
            pillar="engine and powertrain",
            target_scenes=[1, 2, 3],
        )
        self.assertGreaterEqual(len(sources), 3)
        self.assertIn("bmw.com", sources[0]["url"])
        self.assertEqual(sources[0]["scene_numbers"], [1, 2, 3])

    def test_unknown_vehicle_still_has_controlled_recovery_candidates(self):
        sources = automotive_source_provider.discover_sources(
            vehicle="Unknown Experimental Vehicle",
            pillar="car engineering",
            target_scenes=[1, 25],
        )
        self.assertGreaterEqual(len(sources), 3)
        self.assertEqual(sources[-1]["url"], "https://www.nhtsa.gov/vehicle-safety")
        self.assertEqual(sources[-1]["scene_numbers"], [1, 25])

    def test_empty_targets_return_no_sources(self):
        self.assertEqual(
            automotive_source_provider.discover_sources(
                vehicle="Porsche 911 992 Carrera",
                pillar="car engineering",
                target_scenes=[],
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
