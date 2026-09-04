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
    filler = " Investigators keep examining details, timelines, locations, and surviving sources to understand what really happened. Additional clues reveal how the sequence developed over time and why witnesses remembered it differently."
    text_en = (lead + filler).strip()
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

    def test_invalid_scene_repair_keeps_valid_english(self):
        story = valid_story()
        story["scenes"][0]["text_ar"] = "سيئة"
        original_english = story["scenes"][0]["text_en"]
        repaired = dict(story["scenes"][0])
        repaired["text_ar"] = "هذه ترجمة عربية سليمة للمشهد تحافظ على المعنى والمعلومات والتسلسل الزمني بشكل كامل وتوضح التفاصيل المذكورة في النص الأصلي بدقة."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.call", return_value={"response": "{}"}), patch("strict_story_gate.extract_json", return_value=repaired):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        self.assertEqual(result["scenes"][0]["text_en"], original_english)

    def test_short_english_scene_can_be_repaired_without_looping(self):
        story = valid_story()
        story["scenes"][0]["text_en"] = "A hidden mystery emerged suddenly."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.call", side_effect=RuntimeError("mocked model failure")):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        repaired = result["scenes"][0]
        self.assertGreaterEqual(strict_story_gate._word_count_en(repaired["text_en"]), 40)
        self.assertLessEqual(strict_story_gate._word_count_en(repaired["text_en"]), 75)
        self.assertTrue(strict_story_gate._is_hook(repaired))

    def test_invalid_hook_can_rewrite_english(self):
        story = valid_story()
        story["scenes"][0]["text_en"] = (
            "Researchers documented the event and compared surviving records from several archives. "
            "The evidence shows how the sequence unfolded and what investigators learned from it over time."
        )
        story["scenes"][0]["beat"] = "hook"
        repaired = dict(story["scenes"][0])
        repaired["text_en"] = "What shocking detail did investigators discover when the hidden record finally surfaced? This evidence changed the story and raised new questions about what witnesses had missed. Researchers then compared surviving documents to understand how the mystery unfolded."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.extract_json", return_value=repaired):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        self.assertNotEqual(result["scenes"][0]["text_en"], story["scenes"][0]["text_en"])
        self.assertTrue(strict_story_gate._is_hook(result["scenes"][0]))

    def test_numeric_fact_mismatch_is_fixed_before_validation(self):
        story = valid_story()
        scene = story["scenes"][6]
        scene["text_en"] = (
            "What shocking detail did investigators discover about the hidden record? "
            "Seven witnesses described the same unusual event, while researchers compared surviving documents "
            "and physical evidence to understand why the accounts were so consistent over time and across locations."
        )
        scene["text_ar"] = "ما التفاصيل الصادمة التي اكتشفها الباحثون؟ وصف ثمانية شهود الحدث نفسه، ثم قارن الباحثون السجلات والأدلة المتبقية لفهم ما حدث بدقة ضمن سياقه التاريخي."
        repaired = dict(scene)
        repaired["text_ar"] = "ما التفاصيل الصادمة التي اكتشفها الباحثون؟ وصف ثمانية شهود الحدث نفسه، ثم قارن الباحثون السجلات والأدلة المتبقية لفهم ما حدث بدقة ضمن سياقه التاريخي."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"RUN_DIR": tmp}, clear=False), patch("strict_story_gate.extract_json", return_value=repaired):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        final_scene = result["scenes"][6]
        self.assertTrue(strict_story_gate._same_numeric_facts(final_scene["text_en"], final_scene["text_ar"]))
        self.assertEqual(strict_story_gate._numbers(final_scene["text_ar"], "ar"), strict_story_gate._numbers(final_scene["text_en"], "en"))


if __name__ == "__main__":
    unittest.main()
