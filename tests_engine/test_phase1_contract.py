import unittest

from engine.components import resolve_component
from engine.models import AudioPlan, Episode, EpisodeBlueprint, Fact, QAReport, Research, Scene, Short, VisualPlan


class Phase1ContractTests(unittest.TestCase):
    def make_scene(self, scene_id: int) -> Scene:
        return Scene(
            scene_id=scene_id,
            title=f"Scene {scene_id}",
            narration="Technical narration.",
            duration=20,
            facts=[],
            component="engine",
            visual_profile="engine_combustion",
            visual_mode="CUTAWAY",
            media_query="sports car engine",
            media_type="video",
            transition="cut",
            subtitle="Technical narration.",
            audio=AudioPlan(),
        )

    def make_blueprint(self) -> EpisodeBlueprint:
        return EpisodeBlueprint(
            episode=Episode(topic="Toyota Supra MK4", vehicle="Toyota Supra MK4", title="Supra", target_duration_seconds=600),
            research=Research(sources=["test"], methodology="fixture"),
            facts=[Fact(claim="A test claim", source="test", confidence=1.0)],
            story={"hook": "test"},
            scenes=[self.make_scene(i) for i in range(1, 26)],
            visual_plan=VisualPlan(),
            audio_plan=AudioPlan(),
            shorts=[Short(short_id=i, title=f"Short {i}", scene_ids=[i, i + 1], duration=30, hook="h", technical_reveal="r", payoff="p", ending="e") for i in range(1, 5)],
            qa=QAReport(),
        )

    def test_blueprint_has_exactly_25_ordered_scenes(self):
        blueprint = self.make_blueprint()
        blueprint.validate_contract()
        self.assertEqual([s.scene_id for s in blueprint.scenes], list(range(1, 26)))

    def test_known_component_resolves(self):
        component, profile = resolve_component("turbo")
        self.assertEqual(component, "turbocharger")
        self.assertIn("X_RAY", profile["allowed_visual_modes"])

    def test_unknown_component_is_not_silently_mapped(self):
        component, profile = resolve_component("mystery-widget")
        self.assertIsNone(component)
        self.assertIsNone(profile)

    def test_short_duration_gate(self):
        blueprint = self.make_blueprint()
        blueprint.shorts[0].duration = 60
        with self.assertRaises(ValueError):
            blueprint.validate_contract()


if __name__ == "__main__":
    unittest.main()
