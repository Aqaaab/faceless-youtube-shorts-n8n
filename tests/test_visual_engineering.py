import unittest

from scripts.visual_engineering import build_scene_svg, normalize_component, validate_visual_engineering, visual_profile


class VisualEngineeringTests(unittest.TestCase):
    def test_component_registry_is_deterministic(self):
        scene = {"technical_component": "EV battery", "technical_flow": "battery → inverter → motor → wheels"}
        profile = visual_profile(scene)
        self.assertEqual(profile["component_id"], "ev_battery")
        self.assertEqual(profile["layer_id"], "battery")
        self.assertEqual(profile["mode"], "xray")
        self.assertTrue(profile["allowed"])
        validate_visual_engineering({**scene, "visual_engineering": profile})

    def test_aliases_never_change_the_selected_layer(self):
        self.assertEqual(normalize_component("Turbo"), "turbocharger")
        self.assertEqual(normalize_component("motor"), "electric motor")
        self.assertEqual(normalize_component("brake"), "braking system")

    def test_svg_is_full_frame_and_contains_product_ui(self):
        scene = {
            "technical_component": "Turbocharger",
            "technical_flow": "exhaust gas → turbine → compressor → intake air",
            "technical_motion": "Reveal the mechanism",
            "text_ar": "التيربو يضغط الهواء قبل دخوله إلى المحرك",
            "specs": {"horsepower": "450 hp", "torque": "600 Nm", "transmission": "8-speed"},
            "upgrade_note": "ترقية التيربو تتطلب تبريدًا ومعايرة مناسبة.",
        }
        svg = build_scene_svg(scene)
        self.assertIn('width="1920"', svg)
        self.assertIn('height="1080"', svg)
        self.assertIn("TURBOCHARGER", svg)
        self.assertIn("التيربو", svg)
        self.assertIn("450 hp", svg)
        self.assertIn("600 Nm", svg)
        self.assertIn("UPGRADES", svg)
        self.assertIn('class="flow-label"', svg)
        self.assertIn('stroke-dasharray', svg)
        self.assertIn('stroke-dashoffset', svg)
        self.assertIn("COMPONENT  Turbocharger", svg)
        # Test the stable semantic contract, not an implementation-specific SVG id.
        self.assertIn('data-component="turbocharger"', svg)

    def test_vertical_svg_is_1080x1920(self):
        scene = {"technical_component": "EV battery", "text_ar": "البطارية"}
        svg = build_scene_svg(scene, vertical=True)
        self.assertIn('width="1080"', svg)
        self.assertIn('height="1920"', svg)
        self.assertIn("EV BATTERY", svg)
        self.assertIn('data-component="ev_battery"', svg)

    def test_unknown_component_falls_back_safely(self):
        profile = visual_profile({"technical_component": "unknown subsystem"})
        self.assertFalse(profile["allowed"])
        self.assertEqual(profile["layer_id"], "generic")


if __name__ == "__main__":
    unittest.main()
