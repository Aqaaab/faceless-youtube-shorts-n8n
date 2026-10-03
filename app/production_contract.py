"""Canonical production contracts for the WanGP visual pipeline."""

PIPELINE_CONTRACT_VERSION = "wangp-v1"
SCENE_COUNT = 25
SCENE_IDS = tuple(range(1, SCENE_COUNT + 1))
DEFAULT_SCENE_DURATION = 18.0
SCENE_DURATION_MIN = 5.0
SCENE_DURATION_MAX = 60.0
LANDSCAPE_ASPECT = "16:9"
LANDSCAPE_DELIVERY = (1920, 1080)
PORTRAIT_ASPECT = "9:16"
PORTRAIT_DELIVERY = (1080, 1920)

SHORT_CANDIDATE_MINIMUM = 30
SHORT_SELECTION_MIN_PIXEL_DISTANCE = 0.055
SHORT_MIN_SECONDS = 28.0
SHORT_MAX_SECONDS = 59.0
SHORT_DELIVERY_COUNT = 4
SHORT_WINDOW_SCENES = (2,)

VISUAL_FAMILIES = {
    "front_3q", "rear_3q", "side_profile", "low_angle", "wide_scene",
    "front_close", "rear_close", "three_quarter_high", "design_detail",
    "technology", "performance", "safety", "battery", "charging",
    "interior", "wheel_detail", "aero",
}

AUTOMOTIVE_PROFILE_NAMES = ("premium_coupe", "graphite_executive", "pearl_sport")
WAN_GP_RENDERER = "wangp"
WAN_GP_REFERENCE_REQUIRED = True
