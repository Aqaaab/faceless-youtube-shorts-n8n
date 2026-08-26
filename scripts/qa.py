from __future__ import annotations
import json, sys
from pathlib import Path


def check(root: Path) -> None:
    story = json.loads((root / "story.json").read_text(encoding="utf-8"))
    assert len(story["slots"]) == 5
    long_video = root / "long_video.mp4"
    assert long_video.is_file() and long_video.stat().st_size > 0
    for i in range(1, 5):
        p = root / "shorts" / f"short-{i}.mp4"
        assert p.is_file() and p.stat().st_size > 0
    print("QA=PASS")

if __name__ == "__main__":
    check(Path(sys.argv[1] if len(sys.argv) > 1 else "data/run"))
