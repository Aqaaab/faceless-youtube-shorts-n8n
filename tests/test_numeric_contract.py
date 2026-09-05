import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from numeric_contract import numeric_facts, same_numeric_facts, align_arabic_numeric_facts
import strict_story_gate


class NumericContractTests(unittest.TestCase):
    def test_bare_count_words_are_not_facts(self):
        self.assertTrue(same_numeric_facts("one car uses a clever system", "تستخدم السيارة نظاماً ذكياً"))
        self.assertEqual(numeric_facts("seven engineers reviewed it", "en"), numeric_facts("راجع المهندسون النظام", "ar"))

    def test_explicit_spec_value_must_match(self):
        self.assertTrue(same_numeric_facts("The engine makes 450 horsepower", "ينتج المحرك ٤٥٠ حصان"))
        self.assertFalse(same_numeric_facts("The engine makes 450 horsepower", "ينتج المحرك ٤٠٠ حصان"))

    def test_model_identifiers_are_not_facts(self):
        self.assertNotIn("35", numeric_facts("Nissan GT-R R35", "en"))
        self.assertNotIn("35", numeric_facts("نيسان GT-R R35", "ar"))

    def test_deterministic_alignment_repairs_explicit_digits(self):
        repaired = align_arabic_numeric_facts("The engine makes 450 horsepower", "ينتج المحرك 400 حصان")
        self.assertTrue(same_numeric_facts("The engine makes 450 horsepower", repaired))
        self.assertIn("٤٥٠", repaired)

    def test_strict_gate_identifier_digits_are_not_facts(self):
        self.assertNotIn("35", strict_story_gate._numbers("Nissan GT-R R35", "en"))
        self.assertNotIn("6", strict_story_gate._numbers("V6 engine", "en"))
        self.assertNotIn("911", strict_story_gate._numbers("911GT3 RS", "en"))

    def test_strict_gate_standalone_numeric_fact_is_preserved(self):
        self.assertEqual(strict_story_gate._numbers("The engine makes 450 horsepower", "en")["450"], 1)


if __name__ == "__main__":
    unittest.main()
