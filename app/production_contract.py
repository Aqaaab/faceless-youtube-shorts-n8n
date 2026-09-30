"""Shared production contracts. Keep story, TTS, Shorts and publishing on one source of truth."""

SHORT_GROUPS = ((1, 2), (7, 8), (13, 14), (19, 20))
SHORT_MIN_SECONDS = 28.0
SHORT_MAX_SECONDS = 59.0
SHORT_SCENE_MIN_SECONDS = 14.5

REQUIRED_EXTERIOR_OBJECTS = (
    "body_shell",
    "front_bumper",
    "rear_bumper",
    "wheel_fl_arch",
    "wheel_fr_arch",
    "wheel_rl_arch",
    "wheel_rr_arch",
    "headlamp_l",
    "headlamp_r",
    "tail_lamp_l",
    "tail_lamp_r",
    "front_grille",
)

REQUIRED_WHEEL_OBJECTS = (
    "tire_fl", "tire_fr", "tire_rl", "tire_rr",
    "rim_fl", "rim_fr", "rim_rl", "rim_rr",
    "brake_fl", "brake_fr", "brake_rl", "brake_rr",
)

REQUIRED_INTERIOR_OBJECTS = (
    "dash_main",
    "instrument_cluster",
    "infotainment_screen",
    "center_console",
    "steering_wheel",
    "driver_seat",
    "passenger_seat",
    "door_panel_l",
    "door_panel_r",
    "center_vent",
)

REQUIRED_WIDE_OBJECTS = (
    "studio_floor",
    "studio_backdrop",
    "wide_light_key",
    "wide_light_fill",
)

VISUAL_FAMILIES = {
    "front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene",
    "front_close", "rear_close", "three_quarter_high", "design_detail",
    "technology", "performance", "safety", "battery", "charging",
    "interior", "wheel_detail", "aero",
}


# Production v5 contracts. SHORT_GROUPS remains only as a backward-compatible test fixture.
SHORT_CANDIDATE_MINIMUM = 30
SHORT_SELECTION_MIN_PIXEL_DISTANCE = 0.055
SHORT_DELIVERY_COUNT = 4
AUTOMOTIVE_PROFILE_NAMES = ("premium_coupe", "graphite_executive", "pearl_sport")
