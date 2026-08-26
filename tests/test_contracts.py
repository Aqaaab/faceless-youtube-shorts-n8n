import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        c = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
        self.assertEqual(c["primary"]["name"], "Odysseus")
        self.assertEqual(c["production"]["short_count"], 4)
        self.assertEqual(c["production"]["long_duration_seconds"], {"min": 420, "max": 900})
        self.assertEqual(c["production"]["short_duration_seconds"], {"min": 28, "max": 59})
        self.assertEqual(c["production"]["short_resolution"], [1080, 1920])
        self.assertEqual(c["production"]["long_scene_count"], 25)

    def test_story_word_counter(self):
        from story_pipeline import words
        self.assertEqual(words("one two three"), 3)
        self.assertEqual(words("hello, world! 42 times"), 3)

    def test_short_count_and_ranges(self):
        from shorts_pipeline import build_shorts
        story = {"title": "T", "scenes": [{"id": i} for i in range(25)]}
        shorts = build_shorts(story)
        self.assertEqual(len(shorts), 4)
        self.assertEqual(
            [(s["scene_start"], s["scene_end"]) for s in shorts],
            [(1, 6), (7, 12), (13, 18), (19, 24)],
        )
        self.assertEqual([len(s["scenes"]) for s in shorts], [6, 6, 6, 6])


if __name__ == "__main__":
    unittest.main()
