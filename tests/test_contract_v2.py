import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ContractV2Tests(unittest.TestCase):
    def test_story_contract_is_single_source_of_truth(self):
        from story_contract import SCENE_WORDS_MIN, SCENE_WORDS_MAX, SCENE_WORDS_TARGET_MIN, SCENE_WORDS_TARGET_MAX, EXPECTED_SCENES
        from story_pipeline import MIN_WORDS, MAX_WORDS, TARGET_MIN_WORDS, TARGET_MAX_WORDS
        import strict_story_gate
        self.assertEqual((MIN_WORDS, MAX_WORDS, TARGET_MIN_WORDS, TARGET_MAX_WORDS), (SCENE_WORDS_MIN, SCENE_WORDS_MAX, SCENE_WORDS_TARGET_MIN, SCENE_WORDS_TARGET_MAX))
        self.assertEqual((strict_story_gate.MIN_EN_WORDS, strict_story_gate.MAX_EN_WORDS), (SCENE_WORDS_MIN, SCENE_WORDS_MAX))
        self.assertEqual(strict_story_gate.EXPECTED_SCENES, EXPECTED_SCENES)

    def test_numeric_identifier_examples(self):
        from numeric_contract import numeric_facts, same_numeric_facts
        identifiers = "R35 V6 911GT3 2JZ-GTE A80 Mk4"
        self.assertEqual(numeric_facts(identifiers, "en"), {})
        self.assertTrue(same_numeric_facts("The car reaches 300 km/h in 4.1 seconds.", "تصل السيارة إلى ٣٠٠ كم/س خلال ٤٫١ ثانية."))

    def test_youtube_metadata_preflight_is_local(self):
        from youtube_upload import _validate_metadata_contract
        _validate_metadata_contract({"title": "Automotive Engineering", "description": "A valid production description.", "tags": ["cars", "engineering"]})
        with self.assertRaises(ValueError):
            _validate_metadata_contract({"title": "", "description": "x", "tags": []})

    def test_recovery_has_canonical_pythonpath(self):
        text = (ROOT / ".github/workflows/production-recovery.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH: ${{ github.workspace }}/scripts", text)
        self.assertIn("-r requirements.txt", text)

    def test_daily_has_canonical_pythonpath(self):
        text = (ROOT / ".github/workflows/daily-production.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH: ${{ github.workspace }}/scripts", text)
        self.assertIn("-r requirements.txt", text)


if __name__ == "__main__":
    unittest.main()
