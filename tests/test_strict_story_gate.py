import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def valid_scene(index: int) -> dict:
    hook = index in {1, 7, 13, 19}
    lead = "A surprising engineering detail raises a question about how this performance car achieves its result, and the answer reveals why the system matters." if hook else "The engineering analysis continues as researchers compare the component design, operating conditions, and supporting systems to explain how the vehicle works and why the detail matters."
    filler = " The scene connects the visible hardware to its operating behavior and practical limits. Viewers can follow the mechanism, the surrounding systems, and the engineering tradeoffs without relying on unsupported claims."
    text_en = (lead + filler).strip()
    return {
        "id": index,
        "beat": "hook" if hook else "development",
        "text_en": text_en,
        "text_ar": "يوضح هذا المشهد كيف يعمل النظام الهندسي في السيارة ولماذا يؤثر تصميمه في الأداء والاعتمادية مع الحفاظ على المعلومات الواردة في النص الأصلي بدقة.",
        "visual_subject": "modern performance car engineering",
        "pexels_query": "modern performance car engineering",
    }


def valid_story() -> dict:
    return {
        "title": "Performance Car Engineering",
        "description": "Automotive engineering explained through real vehicle systems and practical details.",
        "tags": ["cars", "automotive", "engineering"],
        "scenes": [valid_scene(i) for i in range(1, 26)],
    }


class StrictStoryGateRegressionTests(unittest.TestCase):
    def _env(self, tmp: str) -> dict[str, str]:
        return {"RUN_DIR": tmp, "CAR_MODE": "0", "CAR_VEHICLE": ""}

    def test_valid_story_is_not_sent_through_llm_rewrite(self):
        story = valid_story()
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, self._env(tmp), clear=False), patch("strict_story_gate.call") as mocked_call:
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
        repaired["text_ar"] = "هذه ترجمة عربية سليمة للمشهد تحافظ على المعنى والمعلومات والتفاصيل الهندسية الواردة في النص الأصلي وتوضح آلية العمل والأهمية للمشاهد بدقة كاملة."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, self._env(tmp), clear=False), patch("strict_story_gate.call", return_value={"response": "{}"}), patch("strict_story_gate.extract_json", return_value=repaired):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        self.assertEqual(result["scenes"][0]["text_en"], original_english)

    def test_short_english_scene_can_be_repaired_without_looping(self):
        story = valid_story()
        story["scenes"][0]["text_en"] = "A hidden engineering detail appeared suddenly."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, self._env(tmp), clear=False), patch("strict_story_gate.call", side_effect=RuntimeError("mocked model failure")):
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        repaired = result["scenes"][0]
        self.assertGreaterEqual(strict_story_gate._word_count_en(repaired["text_en"]), 40)
        self.assertLessEqual(strict_story_gate._word_count_en(repaired["text_en"]), 75)
        self.assertTrue(strict_story_gate._is_hook(repaired))
        strict_story_gate._validate_scene(repaired, 1)

    def test_local_fallback_never_returns_short_scene(self):
        import strict_story_gate
        with patch.dict(os.environ, {"CAR_MODE": "1", "CAR_VEHICLE": "Nissan GT-R R35"}, clear=False):
            repaired = strict_story_gate._local_repair(
                {"text_en": "", "text_ar": "", "visual_subject": "", "pexels_query": "", "beat": ""},
                1,
                "Nissan GT-R R35 engineering",
            )
        self.assertGreaterEqual(strict_story_gate._word_count_en(repaired["text_en"]), 40)
        self.assertLessEqual(strict_story_gate._word_count_en(repaired["text_en"]), 75)
        self.assertTrue(strict_story_gate._same_numeric_facts(repaired["text_en"], repaired["text_ar"]))
        self.assertEqual(strict_story_gate._numbers(repaired["text_en"], "en"), strict_story_gate._numbers(repaired["text_ar"], "ar"))
        strict_story_gate._validate_scene(repaired, 1)
        self.assertIn("Nissan GT-R R35", repaired["text_en"])

    def test_local_fallback_with_ascii_fact_preserves_exact_value(self):
        import strict_story_gate
        with patch.dict(os.environ, {"CAR_MODE": "1", "CAR_VEHICLE": "Nissan GT-R R35"}, clear=False):
            repaired = strict_story_gate._local_repair(
                {
                    "text_en": "The Nissan GT-R R35 engine produces 565 horsepower during the documented test. Engineers compare the measured output with the documented operating conditions, supporting hardware, cooling behavior, and calibration strategy to understand the result precisely without adding unsupported claims during the technical review.",
                    "text_ar": "ينتج محرك السيارة قوة مختلفة في النص العربي دون تطابق رقمي، بينما يراجع الفريق المكونات وظروف التشغيل وسلوك التبريد والمعايرة ضمن تحليل فني دقيق.",
                    "visual_subject": "Nissan GT-R R35 engine",
                    "pexels_query": "Nissan GT-R R35 engine",
                    "beat": "development",
                },
                2,
                "Nissan GT-R R35 engineering",
            )
        self.assertEqual(strict_story_gate._numbers(repaired["text_en"], "en"), Counter({"565": 1}))
        self.assertEqual(strict_story_gate._numbers(repaired["text_ar"], "ar"), Counter({"565": 1}))
        self.assertIn("565", repaired["text_ar"])
        strict_story_gate._validate_scene(repaired, 2)

    def test_invalid_hook_can_rewrite_english(self):
        story = valid_story()
        story["scenes"][0]["text_en"] = (
            "Researchers documented the engineering change and compared surviving technical records from several sources. "
            "The evidence shows how the system works and what engineers learned from the design over time."
        )
        story["scenes"][0]["beat"] = "hook"
        repaired = dict(story["scenes"][0])
        repaired["text_en"] = "What surprising engineering detail changed the way this performance car delivers its result? The answer reveals a clever interaction between the main system and its supporting hardware, giving viewers a clear reason to keep watching and understand the mechanism."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, self._env(tmp), clear=False), patch("strict_story_gate.call", return_value={"response": "{}"}), patch("strict_story_gate.extract_json", return_value=repaired) as mocked_extract:
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        self.assertNotEqual(result["scenes"][0]["text_en"], story["scenes"][0]["text_en"])
        self.assertTrue(strict_story_gate._is_hook(result["scenes"][0]))
        strict_story_gate._validate_scene(result["scenes"][0], 1)
        mocked_extract.assert_called()

    def test_numeric_model_identifier_is_not_treated_as_a_fact(self):
        import strict_story_gate
        en = "The Nissan GT-R R35 uses a twin turbo V6 layout for a compact performance package."
        ar = "تستخدم نيسان جي تي آر R35 منظومة V6 مزدوجة التوربو ضمن حزمة أداء مدمجة."
        self.assertNotIn("35", strict_story_gate._numbers(en, "en"))
        self.assertNotIn("35", strict_story_gate._numbers(ar, "ar"))
        self.assertNotIn("5", strict_story_gate._numbers(en, "en"))
        self.assertNotIn("5", strict_story_gate._numbers(ar, "ar"))
        self.assertTrue(strict_story_gate._same_numeric_facts(en, ar))

    def test_numeric_fact_mismatch_is_fixed_locally_without_llm(self):
        story = valid_story()
        scene = story["scenes"][5]
        scene["text_en"] = (
            "The engineering test compares seven temperature checks across the system while researchers review the supporting hardware, operating conditions, cooling behavior, and calibration strategy to understand why the measured values remain stable during repeated performance testing. "
            "The comparison also shows how the measurement process supports reliable conclusions when the same hardware is evaluated under controlled conditions."
        )
        scene["text_ar"] = "يقارن الاختبار الهندسي ثماني عمليات فحص لدرجة الحرارة عبر النظام، ويراجع الباحثون المكونات والظروف التشغيلية وسلوك التبريد واستراتيجية المعايرة لفهم سبب استقرار القيم المقاسة أثناء الاختبارات المتكررة للأداء. كما يوضح التحليل كيف تساعد عملية القياس على الوصول إلى نتائج موثوقة عند تقييم المكونات نفسها ضمن ظروف مضبوطة."
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            (run / "long_story.json").write_text(json.dumps(story, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, self._env(tmp), clear=False), patch("strict_story_gate.call") as mocked_call:
                import strict_story_gate
                strict_story_gate.RUN = run
                result = strict_story_gate.main()
        final_scene = result["scenes"][5]
        self.assertTrue(strict_story_gate._same_numeric_facts(final_scene["text_en"], final_scene["text_ar"]))
        self.assertEqual(strict_story_gate._numbers(final_scene["text_ar"], "ar"), strict_story_gate._numbers(final_scene["text_en"], "en"))
        mocked_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
