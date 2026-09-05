from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _prepare_run(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    for name in (
        "long_story.json", "episode_blueprint.json", "metadata.json", "shorts_manifest.json",
        "shorts_plan.json", "render_manifest.json", "qa_report.json", "sources.json", "youtube_upload_state.json"
    ):
        target = run / name
        if target.exists():
            target.unlink()
    for directory in (run / "audio", run / "media", run / "shorts", run / "renders", run / "render", run / "technical_overlay"):
        if directory.exists():
            shutil.rmtree(directory)


def main() -> None:
    os.environ.setdefault("RUN_DIR", str(ROOT / "data/run"))
    os.environ["CAR_MODE"] = "1"
    run = Path(os.environ["RUN_DIR"])
    _prepare_run(run)

    from contract_hardening import apply_runtime_hardening
    apply_runtime_hardening()

    from story_pipeline import generate
    from story_preflight import main as story_preflight
    from strict_story_gate import main as strict_story
    from story_integrity_lock import main as story_integrity_lock
    from car_content_gate import main as car_gate
    from episode_blueprint import main as blueprint
    from source_enrichment import main as source_enrichment
    from car_shorts_pipeline import main as shorts
    from caption_hardening import harden_manifest, install
    from renderer import main as render
    from technical_overlay import main as technical_overlay
    from episode_quality_gate import main as quality_gate
    from qa import main as qa

    story = generate()
    if not story or len(story.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: generation did not produce exactly 25 scenes")

    story_preflight()
    audited = strict_story()
    if not audited or len(audited.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: strict story audit did not produce exactly 25 scenes")

    locked = story_integrity_lock()
    if not locked or len(locked.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: final story integrity lock failed")

    car_story = car_gate()
    if not car_story or len(car_story.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: automotive content gate failed")

    enriched = blueprint()
    if not enriched or len(enriched.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: episode blueprint enrichment failed")

    sourced = source_enrichment()
    if not sourced or len(sourced.get("scenes", [])) != 25:
        raise RuntimeError("PRODUCTION_ABORT: source enrichment did not preserve the 25-scene master")
    if not sourced.get("sources"):
        raise RuntimeError("PRODUCTION_ABORT: source enrichment produced no trusted sources")

    shorts()
    install()
    render()
    technical_overlay()
    harden_manifest(run)
    qa(run)
    quality_gate()
    print("PRODUCTION_PIPELINE=PASS niche=cars format=encyclopedia master_plus_4_derived_shorts technical_hud=ready sources=registered quality_gate=pass")


if __name__ == "__main__":
    main()
