from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _prepare_run(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    for name in (
        "long_story.json", "episode_blueprint.json", "metadata.json", "shorts_manifest.json",
        "shorts_plan.json", "render_manifest.json", "qa_report.json", "sources.json", "youtube_upload_state.json",
        "visual_plan.json", "visual_manifest.json"
    ):
        target = run / name
        if target.exists():
            target.unlink()
    for directory in (run / "audio", run / "media", run / "shorts", run / "renders", run / "render", run / "technical_overlay"):
        if directory.exists():
            shutil.rmtree(directory)


def _validate_source_provenance(sourced: dict) -> None:
    scenes = sourced.get("scenes", []) if isinstance(sourced, dict) else []
    sources = sourced.get("sources", []) if isinstance(sourced, dict) else []
    if len(scenes) != 25:
        raise RuntimeError("PRODUCTION_ABORT: source enrichment did not preserve the 25-scene master")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("PRODUCTION_ABORT: source enrichment produced no trusted sources")
    source_ids = {str(source.get("id", "")).strip() for source in sources if isinstance(source, dict) and str(source.get("id", "")).strip()}
    if not source_ids or len(source_ids) != len(sources):
        raise RuntimeError("PRODUCTION_ABORT: source enrichment produced duplicate or empty source IDs")
    missing_provenance = [index for index, scene in enumerate(scenes, 1) if not isinstance(scene, dict) or str(scene.get("source_id", "")).strip() not in source_ids]
    if missing_provenance:
        raise RuntimeError("PRODUCTION_ABORT: source enrichment did not assign valid provenance to scenes: " + ",".join(map(str, missing_provenance)))


def _harden_story_visual_queries(run: Path) -> None:
    path = run / "long_story.json"
    story = json.loads(path.read_text(encoding="utf-8"))
    scenes = story.get("scenes") if isinstance(story, dict) else None
    if not isinstance(scenes, list) or len(scenes) != 25:
        raise RuntimeError("PRODUCTION_ABORT: visual-query hardening received invalid 25-scene story")
    from story_pipeline import _query_key, _repair_duplicate_queries
    before = [_query_key(scene.get("pexels_query")) for scene in scenes]
    _repair_duplicate_queries(scenes)
    after = [_query_key(scene.get("pexels_query")) for scene in scenes]
    if any(not value for value in after) or len(after) != len(set(after)):
        raise RuntimeError("PRODUCTION_ABORT: visual-query hardening could not produce unique Pexels queries")
    changed = sum(left != right for left, right in zip(before, after))
    story["scenes"] = scenes
    path.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PEXELS_QUERY_HARDENING=PASS scenes={len(scenes)} changed={changed} unique=true", flush=True)


def _validate_canonical_render_manifest(run: Path) -> None:
    path = run / "render_manifest.json"
    if not path.is_file():
        raise RuntimeError("PRODUCTION_ABORT: canonical render manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 4:
        raise RuntimeError(f"PRODUCTION_ABORT: stale render manifest version {manifest.get('version')!r}; expected 4")
    if manifest.get("media_pipeline") != "generated_still_first_with_pexels_fallback":
        raise RuntimeError("PRODUCTION_ABORT: stale or non-canonical media pipeline manifest")
    if manifest.get("motion_pipeline") != "ken_burns_for_stills_live_motion_for_video":
        raise RuntimeError("PRODUCTION_ABORT: stale or non-canonical motion pipeline manifest")
    master = manifest.get("master")
    shorts = manifest.get("shorts")
    if not isinstance(master, dict) or master.get("scene_count") != 25:
        raise RuntimeError("PRODUCTION_ABORT: render manifest does not describe 25 master scenes")
    if not isinstance(shorts, list) or len(shorts) != 4:
        raise RuntimeError("PRODUCTION_ABORT: render manifest does not describe four shorts")


def _materialize_visual_manifest(run: Path) -> None:
    """Promote renderer's measured scene-visual records to the product-gate contract."""
    render_path = run / "render_manifest.json"
    visual_path = run / "visual_manifest.json"
    manifest = json.loads(render_path.read_text(encoding="utf-8"))
    records = manifest.get("scene_visuals")
    if not isinstance(records, list) or len(records) != 25:
        raise RuntimeError("PRODUCTION_ABORT: renderer did not produce 25 scene visual records")

    normalized: list[dict] = []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            raise RuntimeError(f"PRODUCTION_ABORT: invalid visual record for scene {index}")
        scene = record.get("scene")
        provider = record.get("provider")
        motion = record.get("motion")
        path = str(record.get("path") or "").strip()
        if scene != index or provider not in {"generated", "pexels"} or motion not in {"ken_burns", "live_clip"}:
            raise RuntimeError(f"PRODUCTION_ABORT: invalid visual provider/motion record for scene {index}")
        if not path:
            raise RuntimeError(f"PRODUCTION_ABORT: visual record for scene {index} has no source path")
        source = Path(path)
        if not source.is_file() or source.stat().st_size <= 0:
            raise RuntimeError(f"PRODUCTION_ABORT: visual source missing or empty for scene {index}: {source}")
        if provider == "generated" and motion != "ken_burns":
            raise RuntimeError(f"PRODUCTION_ABORT: generated still scene {index} lacks Ken Burns motion")
        normalized.append({"scene": index, "provider": provider, "motion": motion, "path": path})

    visual_path.write_text(json.dumps({
        "contract": "Odysseus → Gemini automotive stills first; Pexels real footage fallback",
        "gateway": "odysseus",
        "image_provider": "gemini",
        "provider_order": ["generated", "pexels"],
        "motion": "Ken Burns/parallax for stills; native motion for video fallback",
        "scenes": normalized,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VISUAL_MANIFEST=PASS scenes={len(normalized)} measured=true", flush=True)


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
    from visual_plan import main as visual_plan
    from car_shorts_pipeline import main as shorts
    from caption_hardening import harden_manifest, install
    from renderer import main as render
    from technical_overlay import main as technical_overlay
    from episode_quality_gate import main as quality_gate
    from qa import main as qa
    from visual_product_gate import main as visual_product_gate
    from final_gate_runner import run_gate

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
    _validate_source_provenance(sourced)
    _harden_story_visual_queries(run)
    visual_plan()
    shorts()
    install()
    render()
    _validate_canonical_render_manifest(run)
    _materialize_visual_manifest(run)
    technical_overlay()
    _validate_canonical_render_manifest(run)
    run_gate("VISUAL_PRODUCT_GATE", visual_product_gate)
    run_gate("MANIFEST_HARDENING", harden_manifest, run)
    run_gate("PRODUCTION_QA", qa, run)
    run_gate("EPISODE_QUALITY_GATE", quality_gate)
    print("PRODUCTION_PIPELINE=PASS niche=cars format=encyclopedia master_plus_4_derived_shorts visual_system=generated_first_pexels_fallback technical_visual_engineering=ready visual_product_gate=pass sources=claim_mapped quality_gate=pass")


if __name__ == "__main__":
    main()
