from __future__ import annotations
import json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = Path(os.getenv("RUN_DIR", str(ROOT / "data/run")))


def build_shorts(story: dict) -> list[dict]:
    scenes = story.get("scenes", [])
    if len(scenes) != 25:
        raise ValueError("shorts require exactly 25 story scenes")

    # Four coherent excerpts, each made from six consecutive scenes.
    starts = (0, 6, 12, 18)
    shorts = []
    for i, start in enumerate(starts, 1):
        chunk = scenes[start:start + 6]
        shorts.append({
            "id": i,
            "scene_start": start + 1,
            "scene_end": start + len(chunk),
            "title": f"{story.get('title', 'Story')} — Part {i}",
            "scenes": chunk,
        })
    return shorts


def main() -> list[dict]:
    source = RUN / "long_story.json"
    if not source.is_file():
        raise FileNotFoundError(f"missing story: {source}")
    story = json.loads(source.read_text(encoding="utf-8"))
    shorts = build_shorts(story)
    out = RUN / "shorts_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"version": 1, "shorts": shorts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("SHORTS_PLAN=PASS count=4")
    return shorts


if __name__ == "__main__":
    main()
