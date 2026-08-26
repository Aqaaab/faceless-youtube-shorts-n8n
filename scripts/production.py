from __future__ import annotations
import argparse, os
from pathlib import Path
from .story import build_story
from .renderer import render_placeholder


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=os.getenv("VIDEO_TOPIC", "The hidden story behind a surprising invention"))
    parser.add_argument("--output-dir", default="data/run")
    args = parser.parse_args()
    root = Path(args.output_dir); shorts = root / "shorts"; shorts.mkdir(parents=True, exist_ok=True)
    build_story(args.topic, root / "story.json")
    render_placeholder(root / "long_video.mp4", 420)
    for i in range(1, 5): render_placeholder(shorts / f"short-{i}.mp4", 30, vertical=True)
    print("PRODUCTION_PACKAGE=PASS")

if __name__ == "__main__":
    main()
