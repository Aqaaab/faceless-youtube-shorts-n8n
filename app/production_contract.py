"""Single source of truth for production delivery contracts.

Runtime code and tests should import these values instead of duplicating delivery
limits. Fixed Short scene pairs intentionally do not exist in the production
contract; selection is candidate-driven.
"""

LONG_WIDTH = 1920
LONG_HEIGHT = 1080
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
LONG_SIZE = (LONG_WIDTH, LONG_HEIGHT)
SHORT_SIZE = (SHORT_WIDTH, SHORT_HEIGHT)

SCENE_COUNT = 25
SHORT_DELIVERY_COUNT = 4
SHORT_CANDIDATE_MINIMUM = 30

MIN_LONG_SECONDS = 420.0
MAX_LONG_SECONDS = 900.0
SHORT_MIN_SECONDS = 28.0
SHORT_MAX_SECONDS = 59.0
SHORT_SCENE_MIN_SECONDS = 14.5

MIN_WPS = 1.60
MAX_WPS = 2.10
MIN_PUBLISH_SCORE = 9.0

VISUAL_MIN_SCORE = 85.0
CAR_FIRST_THRESHOLD = 0.70
MIN_UNIQUE_FAMILIES = 8
MIN_UNIQUE_CAMERAS = 8
MIN_UNIQUE_INTENTS = 20
MAX_FAMILY_REPETITION = 4
MAX_NEAR_IDENTICAL_PAIRS = 35
MIN_CAMERA_PIXEL_DISTANCE = 0.100
MIN_SHORT_PIXEL_DISTANCE = 0.055

RENDER_FPS = 30
MOTION_FPS = 15
SUBTITLE_FONT_SIZE = 24
SHORT_SUBTITLE_FONT_SIZE = 21
FFMPEG_CRF = 18
FFMPEG_PRESET = "medium"

REQUIRED_EXTERIOR_OBJECTS = (
    "body_shell", "front_bumper", "rear_bumper",
    "wheel_fl_arch", "wheel_fr_arch", "wheel_rl_arch", "wheel_rr_arch",
    "headlamp_l", "headlamp_r", "tail_lamp_l", "tail_lamp_r", "front_grille",
)

REQUIRED_WHEEL_OBJECTS = (
    "tire_fl", "tire_fr", "tire_rl", "tire_rr",
    "rim_fl", "rim_fr", "rim_rl", "rim_rr",
    "brake_fl", "brake_fr", "brake_rl", "brake_rr",
)

REQUIRED_INTERIOR_OBJECTS = (
    "dash_main", "instrument_cluster", "infotainment_screen", "center_console",
    "steering_wheel", "driver_seat", "passenger_seat",
    "door_panel_l", "door_panel_r", "center_vent",
)

REQUIRED_WIDE_OBJECTS = (
    "studio_floor", "studio_backdrop", "wide_light_key", "wide_light_fill",
)

VISUAL_FAMILIES = {
    "front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene",
    "front_close", "rear_close", "three_quarter_high", "design_detail",
    "technology", "performance", "safety", "battery", "charging",
    "interior", "wheel_detail", "aero",
}

AUTOMOTIVE_PROFILE_NAMES = ("premium_coupe", "graphite_executive", "pearl_sport")
