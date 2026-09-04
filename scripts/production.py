from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _prepare_run(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    for name in ("long_story.json", "metadata.json", "shorts_manifest.json", "shorts_plan.json", "render_manifest.json", "qa_report.json", "sources.json"):
        target = run / name
        if target.exists():
            target.unlink()
    for directory in (run / "audio", run / "media", run / "shorts", run / "renders", run / "render", run / "technical_overlay"):
        if directory.exists():
            shutil.rmtree(directory)


def main() -> None:
    os.environ.setdefault("RUN_DIR", str(ROOT / "data/run"))
    os.environ.setdefault("CAR_MODE", "1")
    run = Path(os.environ["RUN_DIR"])
    _prepare_run(run)

    from story_pipeline import generate
    from strict_story_gate import main as strict_story
    from car_content_gate import main as car_gate
    from episode_blueprint import main as blueprint
    from car_shorts_pipeline import main as shorts
    from caption_hardening import harden_manifest, install
    from renderer_safe import main as render
    from technical_overlay import main as technical_overlay
    from qa import main as qa

    story = generate()
    if not story or len(story.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: generation did not produce exactly 25 scenes")

    audited = strict_story()
    if not audited or len(audited.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: strict story audit did not produce exactly 25 scenes")

    car_story = car_gate()
    if not car_story or len(car_story.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: automotive content gate failed")

    enriched = blueprint()
    if not enriched or len(enriched.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: episode blueprint enrichment failed")

    shorts()
    install()
    render()
    technical_overlay()
    harden_manifest(run)
    qa(run)
    print("PRODUCTION_PIPELINE=PASS niche=cars format=encyclopedia master_plus_4_derived_shorts technical_hud=ready sources=registered")


if __name__ == "__main__":
    main()
