from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from episode_blueprint import _technical_defaults


class EpisodeFormatTests(unittest.TestCase):
    def test_technical_annotation_defaults_are_complete(self):
        scene = {
            "text_en": "The turbocharger uses exhaust gas energy to spin a turbine and compressor, increasing intake airflow.",
            "visual_subject": "sports car turbo engine",
            "pexels_query": "sports car turbo engine",
        }
        data = _technical_defaults(scene, 12)
        for key in ("section", "technical_component", "technical_flow", "technical_motion", "failure_mode", "upgrade_note", "short_role"):
            self.assertTrue(str(data.get(key, "")).strip(), key)
        self.assertEqual(data["technical_component"], "Turbocharger")


if __name__ == "__main__":
    unittest.main()
