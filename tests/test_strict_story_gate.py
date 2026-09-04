import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def valid_scene(index: int) -> dict:
    hook = index in {1, 7, 13, 19}
    lead = "A shocking historical mystery begins here, and the evidence raises a question no one expected." if hook else "The investigation continues as researchers compare records, witness accounts, and physical evidence from the event."
    filler = " Investigators keep examining details, timelines, locations, and surviving sources to understand what really happened."
    text_en = (lead + filler + " Additional clues reveal how the sequence developed over time.").strip()
    return {
        "id": index,
        "beat": "hook" if hook else "development",
        "text_en": text_en,
        "text_ar": "تستمر التحقيقات في دراسة السجلات والشهادات والأدلة المتبقية لفهم ما حدث بدقة وربط الأحداث ضمن تسلسلها الزمني.",
        "visual_subject": "historical archive investigation",
        "pexels_query": "historical archive investigation documents",
    }


def valid_story() -> dict:
    return {
        "title": "A Hidden Historical Mystery",
        "description": "A documented historical mystery explored through evidence and surviving records.",
        "tags": ["history", "mystery"],
        "scenes": [valid_scene(i) for i in range(1, 26)],
    }


class StrictStoryGateRegressionTests(unittest.TestCase):
    def test_valid_story_is_not_sent_through_llm_rewrite(self):
        story = valid_story()
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.call") as mocked_call:
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
            self.assertEqual(len(result["scenes"]), 25)
            mocked_call.assert_not_called()

    def test_invalid_scene_repair_cannot_shorten_english(self):
        story = valid_story()
        story["scenes"][0]["text_ar"] = "bad"
        original_english = story["scenes"][0]["text_en"]
        repaired = dict(story["scenes"][0])
        repaired["text_ar"] = "هذه ترجمة عربية سليمة للمشهد تحافظ على المعنى والمعلومات الرقمية والتسلسل الزمني بشكل كامل."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.call", return_value=json.dumps(repaired)):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        self.assertEqual(result["scenes"][0]["text_en"], original_english)


if __name__ == "__main__":
    unittest.main()
