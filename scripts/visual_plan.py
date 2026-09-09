from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))

MODES = ("hero", "detail", "xray", "technical_animation", "exploded", "motion_detail")


def _mode(scene: dict, index: int) -> str:
    role = str(scene.get("short_role", "")).casefold()
    component = str(scene.get("technical_component", "")).casefold()
    subject = str(scene.get("visual_subject", "")).casefold()
    if index == 1 or "hero" in role or "identity" in subject:
        return "hero"
    if any(x in subject for x in ("close-up", "detail", "headlight", "interior", "cabin", "wheel")):
        return "detail"
    if component in {"engine architecture", "ev battery", "electric powertrain", "hybrid system"}:
        return "xray"
    if component in {"turbocharger", "intercooler", "cooling system", "fuel delivery", "fuel injector", "transmission", "gearbox", "differential", "braking system", "suspension", "aerodynamics", "downforce", "electric motor", "tire contact patch"}:
        return "technical_animation"
    if any(x in subject for x in ("inside", "cutaway", "exploded", "architecture")):
        return "exploded"
    return "motion_detail"


def main() -> dict:
    path = RUN / "long_story.json"
    story = json.loads(path.read_text(encoding="utf-8"))
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise RuntimeError("VISUAL_PLAN_ABORT: expected exactly 25 scenes")
    records = []
    for index, scene in enumerate(scenes, 1):
        mode = _mode(scene, index)
        scene["visual_mode"] = mode
        scene["visual_asset_policy"] = "generated_first_then_pexels_fallback"
        scene["camera_motion"] = "ken_burns" if mode != "technical_animation" else "slow_push"
        scene["visual_prompt"] = (
            f"Automotive editorial visual for {os.getenv('CAR_VEHICLE', 'the featured vehicle')}; "
            f"mode={mode}; subject={scene.get('visual_subject', '')}; technical focus={scene.get('technical_component', '')}. "
            "Exact vehicle identity and generation must be preserved. No substitute vehicle, no invented parts, no HUD, no readable text."
        )
        records.append({"scene": index, "mode": mode, "asset_policy": scene["visual_asset_policy"], "camera_motion": scene["camera_motion"]})
    story["visual_system"] = {
        "primary": "generated_or_curated_still",
        "fallback": "Pexels real footage",
        "technical_layer": "local component-aware X-Ray/cutaway/flow SVG",
        "motion": "Ken Burns / slow push / live footage motion",
        "scene_modes": list(MODES),
    }
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN / "visual_plan.json").write_text(json.dumps({"system": story["visual_system"], "scenes": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VISUAL_PLAN=PASS scenes={len(records)} modes=" + ",".join(sorted({x['mode'] for x in records})))
    return story


if __name__ == "__main__":
    main()
