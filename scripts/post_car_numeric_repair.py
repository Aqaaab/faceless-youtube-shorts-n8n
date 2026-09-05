from __future__ import annotations

import json
from pathlib import Path

from strict_story_gate import _canonicalize_numeric_facts, _numbers

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(__import__("os").getenv("RUN_DIR", str(ROOT / "data/run")))


def main() -> None:
    path = RUN / "long_story.json"
    story = json.loads(path.read_text(encoding="utf-8"))
    repaired = 0
    for scene in story.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        en = str(scene.get("text_en", "")).strip()
        ar = str(scene.get("text_ar", "")).strip()
        if en and ar and _numbers(en, "en") != _numbers(ar, "ar"):
            scene["text_ar"] = _canonicalize_numeric_facts(en, ar)
            repaired += 1
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"POST_CAR_NUMERIC_REPAIR=PASS repaired={repaired}")


if __name__ == "__main__":
    main()
