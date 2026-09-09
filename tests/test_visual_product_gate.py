from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VisualProductGateTests(unittest.TestCase):
    def test_generic_visual_profiles_are_rejected(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from visual_engineering import visual_profile, validate_visual_engineering

        profile = visual_profile({"technical_component": "unknown component"})
        self.assertFalse(profile["allowed"])
        with self.assertRaises(ValueError):
            validate_visual_engineering({"visual_engineering": profile})

    def test_svg_builder_never_emits_internal_mode_metadata(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from visual_engineering import build_scene_svg

        svg = build_scene_svg({"technical_component": "Turbocharger", "technical_flow": "air"})
        for token in ("FACT_SOURCE_REQUIRED", "GENERAL_EXPLANATION", "HUD_ONLY", "X-RAY SECTION", "MODE  CUTAWAY_FLOW"):
            self.assertNotIn(token, svg)

    def test_production_invokes_visual_product_gate_before_quality_gate(self):
        production = (ROOT / "scripts" / "production.py").read_text(encoding="utf-8")
        self.assertIn("from visual_product_gate import main as visual_product_gate", production)
        self.assertIn('run_gate("VISUAL_PRODUCT_GATE", visual_product_gate)', production)
        self.assertLess(production.index('run_gate("VISUAL_PRODUCT_GATE", visual_product_gate)'), production.index('run_gate("EPISODE_QUALITY_GATE", quality_gate)'))

    def test_daily_workflow_contains_gate_script(self):
        workflow = (ROOT / ".github" / "workflows" / "daily-production.yml").read_text(encoding="utf-8")
        self.assertIn("test -f scripts/visual_product_gate.py", workflow)


if __name__ == "__main__":
    unittest.main()
