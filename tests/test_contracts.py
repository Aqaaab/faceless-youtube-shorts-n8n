import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        c = json.loads((ROOT / "config/production.json").read_text(encoding="utf-8"))
        self.assertEqual(c["primary"]["name"], "Odysseus")
        fallback = c.get("fallback") or {}
        self.assertEqual(fallback.get("order"), ["YOUTUBE_LLM", "GEMINI"])
        self.assertTrue(fallback.get("only_after_primary_failure"))
        self.assertTrue(fallback.get("provider_keys_stay_in_youtube"))
        self.assertEqual(c["production"]["long_video_count"], 1)
        self.assertEqual(c["production"]["short_count"], 4)
        self.assertEqual(c["production"]["long_duration_seconds"], {"min": 420, "max": 900})
        self.assertEqual(c["production"]["short_duration_seconds"], {"min": 28, "max": 59})
        self.assertEqual(c["production"]["short_resolution"], [1080, 1920])
        self.assertEqual(c["production"]["short_fps"], 30)
        self.assertEqual(c["production"]["long_scene_count"], 25)

    def test_gateway_defaults_and_retry_contract(self):
        from odysseus_gateway import GEMINI_DEFAULT_MODEL, GEMINI_FALLBACK_MODELS, _gemini_models
        self.assertEqual(GEMINI_DEFAULT_MODEL, "gemini-3.7-flash")
        self.assertIn(GEMINI_DEFAULT_MODEL, GEMINI_FALLBACK_MODELS)
        models = _gemini_models()
        self.assertEqual(models[0], GEMINI_DEFAULT_MODEL)
        self.assertEqual(len(models), len(set(models)))
        self.assertEqual(set(models), set(GEMINI_FALLBACK_MODELS))
        with patch.dict("os.environ", {"GEMINI_MODEL": "custom-model", "GEMINI_FALLBACK_MODELS": "a,b,a"}, clear=False):
            self.assertEqual(_gemini_models(), ["custom-model", "a", "b"])

    def test_story_word_counter(self):
        from story_pipeline import words
        self.assertEqual(words("one two three"), 3)
        self.assertEqual(words("hello, world! 42 times"), 3)

    def test_short_count_ranges_and_standalone_titles(self):
        from shorts_pipeline import build_shorts
        story = {
            "title": "A Strange Historical Mystery",
            "scenes": [
                {"id": i, "beat": "hook" if i in {0, 6, 12, 18} else "setup", "text_en": f"This is the shocking hook for scene {i} that makes viewers curious."}
                for i in range(25)
            ],
        }
        shorts = build_shorts(story)
        self.assertEqual(len(shorts), 4)
        self.assertEqual([(s["scene_start"], s["scene_end"]) for s in shorts], [(1, 6), (7, 12), (13, 18), (19, 24)])
        self.assertEqual([len(s["scenes"]) for s in shorts], [6, 6, 6, 6])
        self.assertTrue(all("part" not in s["title"].lower() for s in shorts))
        self.assertEqual(len({s["title"] for s in shorts}), 4)
        self.assertTrue(all(18 <= len(s["title"]) <= 68 for s in shorts))
        self.assertTrue(all("#History" in s["description"] for s in shorts))

    def test_renderer_safe_is_only_a_compatibility_shim(self):
        source = (ROOT / "scripts/renderer_safe.py").read_text(encoding="utf-8")
        self.assertIn("def main", source)
        self.assertIn("renderer.main()", source)
        self.assertNotIn("textwrap.wrap", source)
        self.assertNotIn("renderer.make_ass =", source)

    def test_renderer_has_dedicated_vertical_subtitle_contract(self):
        source = (ROOT / "scripts/renderer.py").read_text(encoding="utf-8")
        self.assertIn("def make_vertical_ass", source)
        self.assertIn("PlayResX=1080", source)
        self.assertIn("PlayResY=1920", source)
        self.assertIn("baked_after_9x16_crop", source)
        self.assertIn("render_manifest.json", source)

    def test_fallback_chain_is_not_direct_provider_fallback_in_story_pipeline(self):
        source = (ROOT / "scripts/story_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("call_fallback", source)
        self.assertIn("odysseus_gateway", source)
        self.assertIn("provider", source)
        self.assertIn("arabic_proofread", source)

    def test_no_stale_provider_references(self):
        forbidden = re.compile(r"provider_registry\.py|config/providers\.json|/api/chat")
        scanned = []
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
