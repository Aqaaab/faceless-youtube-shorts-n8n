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

    def test_svg_builder_is_a_full_frame_product_layer(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from visual_engineering import build_scene_svg

        svg = build_scene_svg({
            "technical_component": "Engine",
            "text_ar": "هندسة المحرك",
            "specs": {"horsepower": "500 hp", "torque": "650 Nm"},
            "upgrade_note": "تحسين التبريد والمعايرة قبل زيادة القوة.",
        })
        self.assertIn('width="1920" height="1080"', svg)
        self.assertIn("500 hp", svg)
        self.assertIn("650 Nm", svg)
        self.assertIn("UPGRADES", svg)
        self.assertIn("الاحتراق", svg)
        self.assertIn("هندسة المحرك", svg)

    def test_vertical_product_layer_is_native_not_crop_contract(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from visual_engineering import build_scene_svg

        svg = build_scene_svg({"technical_component": "Transmission", "text_ar": "ناقل الحركة"}, vertical=True)
        self.assertIn('width="1080" height="1920"', svg)
        self.assertIn("ناقل الحركة", svg)
        self.assertIn("TORQUE", svg)

    def test_technical_overlay_removes_opaque_full_canvas_background(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import technical_overlay

        source = (ROOT / "scripts" / "technical_overlay.py").read_text(encoding="utf-8")
        self.assertIn("_make_overlay_svg", source)
        self.assertIn("opaque full-canvas background survived", source)

        # Exercise the exact transformation without invoking FFmpeg.
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "scene.svg"
            svg = '<svg width="1920" height="1080"><defs><linearGradient id="bg"/></defs><rect width="100%" height="100%" fill="url(#bg)"/><path d="M0 0 H10"/></svg>'
            with patch.object(technical_overlay, "build_scene_svg", return_value=svg):
                technical_overlay._make_overlay_svg({"technical_component": "Engine"}, False, out)
            rendered = out.read_text(encoding="utf-8")
            self.assertNotIn('<rect width="100%" height="100%" fill="url(#bg)"', rendered)
            self.assertIn('<path d="M0 0 H10"/>', rendered)

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
