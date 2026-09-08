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

    def test_svg_contains_component_specific_flow_and_labels(self):
        scene = {
            "technical_component": "Turbocharger",
            "technical_flow": "exhaust gas → turbine → compressor → intake air",
            "technical_motion": "Reveal the mechanism",
        }
        svg = build_scene_svg(scene)
        self.assertIn("TURBOCHARGER", svg)
        self.assertIn("COMPONENT  Turbocharger", svg)
        self.assertIn('id="component-turbocharger"', svg)
        self.assertIn('class="flow"', svg)

    def test_unknown_component_falls_back_safely(self):
        profile = visual_profile({"technical_component": "unknown subsystem"})
        self.assertFalse(profile["allowed"])
        self.assertEqual(profile["layer_id"], "generic")


if __name__ == "__main__":
    unittest.main()
