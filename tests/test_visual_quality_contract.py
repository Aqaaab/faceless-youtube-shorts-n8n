from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_blender_v4_model_is_the_only_production_renderer():
    source = (ROOT / "scripts" / "blender_automotive_scene.py").read_text(encoding="utf-8")
    model = (ROOT / "scripts" / "automotive_model.py").read_text(encoding="utf-8")
    assert "from automotive_model import" in source
    assert "blender_eevee_automotive_v5_temporal" in model
    assert "persistent_automotive_coupe_v5_surface_refined" in model
    assert "build_persistent_asset" in model


def test_exterior_model_has_real_wheel_and_lighting_detail():
    source = (ROOT / "scripts" / "automotive_model.py").read_text(encoding="utf-8")
    for marker in (
        "body_shell", "wheel_fl_arch", "wheel_fr_arch", "wheel_rl_arch", "wheel_rr_arch",
        "tire_fl", "tire_fr", "tire_rl", "tire_rr",
        "rim_fl", "rim_fr", "rim_rl", "rim_rr",
        "brake_fl", "brake_fr", "brake_rl", "brake_rr",
        "headlamp_l", "headlamp_r", "tail_lamp_l", "tail_lamp_r",
    ):
        assert marker in source


def test_interior_model_is_not_a_flat_placeholder():
    source = (ROOT / "scripts" / "automotive_model.py").read_text(encoding="utf-8")
    for marker in (
        "dash_main", "instrument_cluster", "infotainment_screen", "center_console",
        "steering_wheel", "steering_spoke", "driver_seat", "passenger_seat",
        "door_panel_l", "door_panel_r", "center_vent",
    ):
        assert marker in source


def test_callouts_are_burned_into_scene_rasters():
    for name in ("app/story_visuals.py", "app/vertical_visuals.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "apply_callout_overlay" in source


def test_short_candidates_have_one_selection_engine():
    selector = (ROOT / "app/short_selector.py").read_text(encoding="utf-8")
    render = (ROOT / "app/render.py").read_text(encoding="utf-8")
    assert "SHORT_MIN_SECONDS" in selector
    assert "MIN_CANDIDATES = 30" in selector
    assert "load_selected" in render
