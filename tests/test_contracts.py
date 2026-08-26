import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        c = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
        self.assertEqual(c["primary"]["name"], "Odysseus")
        self.assertIsNone(c["fallback"])
        self.assertEqual(c["production"]["long_video_count"], 1)
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

    def test_no_direct_provider_fallback(self):
        source = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("call_fallback", source)
        self.assertIn("provider=Odysseus", source)

    def test_no_stale_provider_references(self):
        forbidden = re.compile(r"provider_registry\.py|config/providers\.json|call_fallback|/api/chat")
        scanned = []
        # Scan production code and configuration only. The workflow contains
        # intentional negative guards and this test contains its own patterns.
        for base in (ROOT / "scripts", ROOT / "config"):
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".yml", ".yaml", ".json"}:
                    scanned.append(path)
                    text = path.read_text(encoding="utf-8")
                    self.assertIsNone(forbidden.search(text), f"stale provider reference in {path}")
        self.assertTrue(scanned)


if __name__ == "__main__":
    unittest.main()
