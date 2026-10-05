from pathlib import Path
import argparse, os, shutil, json, hashlib
from .core import ask_odysseus, _normalize_for_validation, _deterministic_structure_repair, _story_from_data, load_story, save_story, RUN
from .validator import validate_short_selection, validate_story_data, validate_story
from .story_visuals import generate_visuals
from .tts import generate_tts, validate_tts_timing, synchronize_scene_durations
from .render import render_long, write_srt, burn_subtitles, render_shorts
from .qa import qa
from .mp4_visual_gate import run_mp4_visual_product_gate
from .visual_product_gate import run_visual_product_gate



STORY_SYSTEM = '''You are the production Story Engine for a premium Arabic automotive YouTube channel. Output JSON only. EXACTLY 25 scenes, ids 1..25. Each scene must contain id, Arabic narration, visual_intent, layout, callouts, duration. Generate 30-45 Arabic words per scene. Set every provisional duration to 18 seconds. Return exactly four unique provisional Arabic short_titles, 20-80 characters each; they are metadata only and must not encode or assume any fixed scene pairs because a later selector chooses Shorts from a candidate pool. Use layouts only hero, technical, spec, comparison, diagram, timeline; at least 4 layouts; at least 12 callout scenes; at least 20 distinct visual intents. Callouts must be directly grounded in the same narration and numeric callouts must copy the exact digit form used there. Do not invent unsupported specifications. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Visual language is full-frame premium automotive editorial with the vehicle as the primary subject; never output dashboard/debug copy or stock-footage references.'''

REPAIR_SYSTEM = '''Return JSON only. Repair or regenerate the supplied Arabic automotive story. The JSON root MUST be an object with a top-level scenes array. EXACTLY 25 scenes, ids 1..25. Every scene must have 30-45 Arabic narration words, visual_intent of at least 4 words, a valid layout, grounded callouts, and duration 18.0. Return exactly four unique Arabic short_titles of 20-80 characters. Shorts are selected later from a candidate pool, so do not impose a later candidate selector. Ensure >=4 layouts, >=12 callout scenes, >=20 distinct visual intents, total planned duration 450 seconds. Preserve factual claims; do not invent specifications or numbers. Remove unsupported callouts. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Return the complete object only, with no markdown or explanation.'''


def clean_run():
    if RUN.exists(): shutil.rmtree(RUN)
    RUN.mkdir(parents=True, exist_ok=True)


def _require(path):
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"required production artifact missing: {path}")


def _compact_payload(data):
    normalized = _normalize_for_validation(data) if isinstance(data, dict) else {}
    scenes = normalized.get("scenes") if isinstance(normalized, dict) else None
    compact = []
    if isinstance(scenes, list):
        for scene in scenes:
            if isinstance(scene, dict):
                compact.append({
                    "id": scene.get("id"),
                    "narration": str(scene.get("narration", "")),
                    "visual_intent": str(scene.get("visual_intent", "")),
                    "layout": scene.get("layout"),
                    "callouts": scene.get("callouts", []),
                    "duration": scene.get("duration", 18.0),
                })
    return json.dumps({
        "topic": normalized.get("topic"),
        "title": normalized.get("title"),
        "description": normalized.get("description"),
        "tags": normalized.get("tags", []),
        "short_titles": normalized.get("short_titles", []),
        "narration": normalized.get("narration", ""),
        "scenes": compact,
    }, ensure_ascii=False, separators=(",", ":"))


def _validate_candidate(data):
    candidate = _deterministic_structure_repair(_normalize_for_validation(data))
    validate_story_data(candidate)
    return candidate


def generate_story_resilient(topic: str):
    generation_attempts = max(1, int(os.getenv("STORY_GENERATION_ATTEMPTS", "2")))
    timeout = max(60.0, float(os.getenv("STORY_GENERATION_TIMEOUT", "180")))
    repair_attempts = max(1, int(os.getenv("STORY_REPAIR_ATTEMPTS", "2")))
    repair_timeout = max(60.0, float(os.getenv("STORY_REPAIR_TIMEOUT", str(timeout))))
    last_error = "unknown story failure"

    for generation_index in range(generation_attempts):
        data = ask_odysseus(STORY_SYSTEM, f"Create the production story for this topic: {topic}", timeout=timeout)
        try:
            return _story_from_data(_validate_candidate(data), topic)
        except (AssertionError, RuntimeError, TypeError, ValueError) as exc:
            last_error = str(exc)

        payload = _compact_payload(data)
        for repair_index in range(repair_attempts):
            repair_user = f"Topic: {topic}\nValidation failure: {last_error}\n\nCurrent story payload:\n{payload}"
            repaired = None
            try:
                repaired = ask_odysseus(REPAIR_SYSTEM, repair_user, timeout=repair_timeout)
                normalized = _normalize_for_validation(repaired)
                candidate = _deterministic_structure_repair(normalized)
                validate_story_data(candidate)
                return _story_from_data(candidate, topic)
            except (AssertionError, RuntimeError, TypeError, ValueError) as exc:
                last_error = str(exc)
                if isinstance(repaired, dict):
                    payload = _compact_payload(repaired)
                continue
        if generation_index + 1 < generation_attempts:
            continue

    raise RuntimeError(f"Story generation failed after {generation_attempts} generations and {repair_attempts} repairs per generation: {last_error}")



from .arabic_font import ensure_ready
from .checkpoint import PIPELINE_REVISION, begin as checkpoint_begin, load as checkpoint_load, mark as checkpoint_mark, stage_done
from .profile import load_profile
from .short_selector import select_shorts, load_selected
from .thumbnail import generate_thumbnail

def _motion_enabled() -> bool:
    return os.getenv("AUTOMOTIVE_RENDER_MOTION", "0").strip().lower() in {"1", "true", "yes"}


def _scene_artifacts(prefix: str) -> list[Path]:
    extension = []
    for sid in range(1, 26):
        extension.extend(
            [
                RUN / prefix / f"scene_{sid:02d}.svg",
                RUN / prefix / f"scene_{sid:02d}.png",
            ]
        )
        if _motion_enabled():
            extension.append(RUN / prefix / f"scene_{sid:02d}.motion.mp4")
    return extension


def _run_stage(state: dict, name: str, artifacts: list[Path], fn):
    if stage_done(state, name, artifacts):
        return False
    try:
        checkpoint_mark(state, RUN, name, "running", artifacts)
        fn()
        if not stage_done(state, name, artifacts):
            raise RuntimeError(f"Stage {name} completed without all required artifacts")
        checkpoint_mark(state, RUN, name, "done", artifacts)
        return True
    except Exception as exc:
        checkpoint_mark(state, RUN, name, "failed", artifacts, str(exc))
        raise


def _selected_short_artifacts() -> list[Path]:
    return [
        RUN / "short_candidates.json",
        *(RUN / "shorts" / f"short_{i}.mp4" for i in range(1, 5)),
        RUN / "short_subtitles_burn.json",
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_revision() -> str:
    return os.getenv("ACE_SOURCE_REVISION") or os.getenv("GITHUB_SHA") or "local"


def _write_production_manifest(story, qa_report: dict, final: Path, shorts: list[Path], visual_gate: dict, mp4_gate: dict) -> Path:
    story_hash = _sha256(RUN / "story.json")
    manifest = {
        "production_id": f"{story.topic.strip()}::{_source_revision()}",
        "commit": _source_revision(),
        "story_hash": story_hash,
        "scene_plan_hash": story_hash,
        "renderer_version": PIPELINE_REVISION,
        "long_video": {
            "file": str(final),
            "sha256": _sha256(final),
            "duration": float(qa_report.get("master_duration") or 0.0),
        },
        "shorts": [
            {"file": str(path), "sha256": _sha256(path), "duration": float(item.get("duration") or 0.0)}
            for path, item in zip(shorts, qa_report.get("shorts", []))
        ],
        "qa": {
            "technical": "PASS" if mp4_gate.get("passed") else "FAIL",
            "visual": "PASS" if visual_gate.get("passed") else "FAIL",
            "audio": "PASS" if qa_report.get("score_categories", {}).get("Audio / Voice", 0) >= 10 else "FAIL",
            "semantic": "PASS" if qa_report.get("score_categories", {}).get("Script / Story", 0) >= 10 else "FAIL",
            "diversity": "PASS" if visual_gate.get("passed") else "FAIL",
        },
        "publish": "APPROVED" if qa_report.get("passed") and visual_gate.get("passed") and mp4_gate.get("passed") else "BLOCKED",
    }
    path = RUN / "production_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default=os.getenv("CAR_TOPIC", ""))
    ap.add_argument("--profile", default=os.getenv("AUTOMOTIVE_PROFILE", "premium_coupe"))
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    topic = args.topic.strip()
    if not topic:
        raise SystemExit("CAR_TOPIC is required")

    os.environ["AUTOMOTIVE_PROFILE"] = args.profile
    os.environ.setdefault("ACE_SOURCE_REVISION", os.getenv("GITHUB_SHA", "local"))
    profile = load_profile(args.profile)
    if args.reset and RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True, exist_ok=True)
    state = checkpoint_begin(RUN, topic, profile["name"], reset=args.reset)
    state = checkpoint_load(RUN)

    font_report = RUN / "arabic_font_gate.json"
    if not font_report.is_file():
        ensure_ready(font_report, strict=True)

    story_path = RUN / "story.json"
    if stage_done(state, "story", [story_path]):
        story = load_story(story_path)
        validate_story()
    else:
        if not os.getenv("ODYSSEUS_GATEWAY_BASE_URL") or not os.getenv("ODYSSEUS_GATEWAY_API_KEY"):
            raise SystemExit("Odysseus gateway credentials are required for a new story")
        story = generate_story_resilient(topic)
        save_story(story)
        validate_story()
        checkpoint_mark(state, RUN, "story", "done", [story_path])

    tts_artifacts = [RUN / "tts_durations.json"] + [
        RUN / "audio" / f"scene_{sid:02d}.{suffix}"
        for sid in range(1, 26)
        for suffix in ("mp3", "words.json")
    ]
    if stage_done(state, "tts", tts_artifacts):
        durations = json.loads((RUN / "tts_durations.json").read_text(encoding="utf-8"))
        durations = {int(k): float(v) for k, v in durations.items()}
    else:
        durations = generate_tts(story)
        synchronize_scene_durations(story, durations)
        save_story(story)
        validate_story()
        validate_tts_timing(story, durations)
        (RUN / "tts_durations.json").write_text(json.dumps(durations, ensure_ascii=False, indent=2), encoding="utf-8")
        checkpoint_mark(state, RUN, "tts", "done", tts_artifacts)
    synchronize_scene_durations(story, durations)
    validate_tts_timing(story, durations)

    visual_artifacts = _scene_artifacts("scenes")
    _run_stage(state, "visuals", visual_artifacts, lambda: generate_visuals(story))

    selector_artifacts = [RUN / "short_candidates.json"]
    if not stage_done(state, "short_selection", selector_artifacts):
        select_shorts(story, RUN / "scenes", RUN / "short_candidates.json")
        selected_manifest = json.loads((RUN / "short_candidates.json").read_text(encoding="utf-8"))
        validate_short_selection(selected_manifest)
        selected = load_selected(RUN / "short_candidates.json")
        story.short_titles = [str(item["title"]).strip() for item in selected]
        save_story(story)
        validate_story()
        checkpoint_mark(state, RUN, "short_selection", "done", selector_artifacts)

    master = RUN / "master.mp4"
    _run_stage(state, "long_render", [master], lambda: render_long(story, master))

    srt = RUN / "arabic.srt"
    final = RUN / "master_final.mp4"
    if not stage_done(state, "subtitles", [srt, final, RUN / "subtitle_burn.json"]):
        write_srt(story, srt)
        burn_subtitles(master, srt, final)
        checkpoint_mark(state, RUN, "subtitles", "done", [srt, final, RUN / "subtitle_burn.json"])

    _run_stage(
        state,
        "short_render",
        _selected_short_artifacts(),
        lambda: render_shorts(story),
    )

    thumbnail = RUN / "thumbnail.jpg"
    _run_stage(state, "thumbnail", [thumbnail], lambda: generate_thumbnail(story))

    # Final gates are deliberately re-run even on resume because they are cheap compared
    # with rendering and must be evaluated against the current filesystem state.
    visual_gate = run_visual_product_gate(
        story, final,
        [RUN / "shorts" / f"short_{i}.mp4" for i in range(1, 5)],
        RUN / "visual_product_gate_v3.json",
        check_subtitles=True,
    )
    qa(story, final, [RUN / "shorts" / f"short_{i}.mp4" for i in range(1, 5)])
    mp4_gate = run_mp4_visual_product_gate(
        final,
        [RUN / "shorts" / f"short_{i}.mp4" for i in range(1, 5)],
        RUN / "mp4_visual_product_gate.json",
    )
    qa_report_path = RUN / "qa_report.json"
    qa_report = json.loads(qa_report_path.read_text(encoding="utf-8"))
    qa_report["visual_product_gate_v3"] = visual_gate
    qa_report["mp4_visual_product_gate"] = mp4_gate
    qa_report["short_selection"] = json.loads((RUN / "short_candidates.json").read_text(encoding="utf-8"))
    qa_report["thumbnail"] = {"path": str(thumbnail), "size_bytes": thumbnail.stat().st_size}
    qa_report["arabic_font_gate"] = json.loads(font_report.read_text(encoding="utf-8"))
    qa_report["pipeline_revision"] = PIPELINE_REVISION
    qa_report["source_revision"] = _source_revision()
    qa_report["master_sha256"] = _sha256(final)
    qa_report["short_shas"] = [_sha256(RUN / "shorts" / f"short_{i}.mp4") for i in range(1, 5)]
    qa_report["motion_scene_count"] = sum(
        1 for sid in range(1, 26)
        if (RUN / "scenes" / f"scene_{sid:02d}.motion.mp4").is_file()
    ) if _motion_enabled() else 0
    qa_report["cost_usd"] = 0.0
    qa_report["paid_services_used"] = []
    qa_report["passed"] = bool(qa_report.get("passed")) and bool(visual_gate.get("passed")) and bool(mp4_gate.get("passed"))
    qa_report_path.write_text(json.dumps(qa_report, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = _write_production_manifest(
        story, qa_report, final,
        [RUN / "shorts" / f"short_{i}.mp4" for i in range(1, 5)],
        visual_gate, mp4_gate,
    )
    if not qa_report["passed"]:
        raise RuntimeError("FINAL QA FAILED: " + "; ".join(qa_report.get("errors", [])))
    checkpoint_mark(
        state,
        RUN,
        "final_qa",
        "done",
        [qa_report_path, RUN / "production_manifest.json", final, thumbnail, RUN / "visual_product_gate_v3.json", RUN / "mp4_visual_product_gate.json"],
    )
    print("PRODUCTION ARTIFACT READY:", final)
    print("FINAL QA PASSED: master + 4 Shorts + word-timed Arabic subtitles + thumbnail + manifest")
