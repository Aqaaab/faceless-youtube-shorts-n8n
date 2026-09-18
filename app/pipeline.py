import argparse, os, shutil, json
from .core import ask_odysseus, _normalize_for_validation, _deterministic_structure_repair, _story_from_data, save_story, RUN
from .validator import validate_story_data, validate_story
from .story_visuals import generate_visuals
from .tts import generate_tts, validate_tts_timing, synchronize_scene_durations
from .render import render_long, write_srt, burn_subtitles, render_shorts
from .qa import qa
from .mp4_visual_gate import run_mp4_visual_product_gate


STORY_SYSTEM = '''You are the production Story Engine for a premium Arabic automotive YouTube channel. Output JSON only. EXACTLY 25 scenes, ids 1..25. Each scene must contain id, Arabic narration, visual_intent, layout, callouts, duration. Generate 30-45 Arabic words per scene. Set every provisional duration to 18 seconds. Return exactly four unique Arabic short_titles for source pairs (1,2), (7,8), (13,14), (19,20), each 20-80 characters. Use layouts only hero, technical, spec, comparison, diagram, timeline; at least 4 layouts; at least 12 callout scenes; at least 20 distinct visual intents. Callouts must be directly grounded in the same narration and numeric callouts must copy the exact digit form used there. Do not invent unsupported specifications. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Visual language is full-frame premium automotive editorial with the vehicle as the primary subject; never output dashboard/debug copy or stock-footage references.'''

REPAIR_SYSTEM = '''Return JSON only. Repair or regenerate the supplied Arabic automotive story. The JSON root MUST be an object with a top-level scenes array. EXACTLY 25 scenes, ids 1..25. Every scene must have 30-45 Arabic narration words, visual_intent of at least 4 words, a valid layout, grounded callouts, and duration 18.0. Return exactly four unique Arabic short_titles of 20-80 characters. Ensure >=4 layouts, >=12 callout scenes, >=20 distinct visual intents, total planned duration 450 seconds, and source pairs (1,2),(7,8),(13,14),(19,20) each total 36 seconds. Preserve factual claims; do not invent specifications or numbers. Remove unsupported callouts. Title 20-100 chars, description >=120 chars, >=5 tags, aggregate narration >=200 words. Return the complete object only, with no markdown or explanation.'''


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


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--topic',default=os.getenv('CAR_TOPIC','')); args=ap.parse_args()
    if not args.topic.strip(): raise SystemExit('CAR_TOPIC is required')
    if not os.getenv('ODYSSEUS_GATEWAY_BASE_URL') or not os.getenv('ODYSSEUS_GATEWAY_API_KEY'):
        raise SystemExit('Odysseus gateway credentials are required')

    clean_run()
    story=generate_story_resilient(args.topic.strip())
    save_story(story)
    validate_story()

    generate_visuals(story)

    tts_durations=generate_tts(story)
    synchronize_scene_durations(story, tts_durations)
    save_story(story)
    validate_story()
    validate_tts_timing(story, tts_durations)
    (RUN/'tts_durations.json').write_text(json.dumps(tts_durations,ensure_ascii=False,indent=2),encoding='utf-8')

    for s in story.scenes:
        _require(RUN/'scenes'/f'scene_{s.id:02d}.svg'); _require(RUN/'audio'/f'scene_{s.id:02d}.mp3')

    render_long(story); _require(RUN/'master.mp4')
    write_srt(story); _require(RUN/'arabic.srt')
    burn_subtitles(RUN/'master.mp4',RUN/'arabic.srt',RUN/'master_final.mp4'); _require(RUN/'master_final.mp4')
    render_shorts(story)
    shorts=[RUN/'shorts'/f'short_{i}.mp4' for i in range(1,5)]
    for p in shorts: _require(p)
    qa(story,RUN/'master_final.mp4',shorts)
    mp4_gate = run_mp4_visual_product_gate(RUN/'master_final.mp4', shorts, RUN/'mp4_visual_product_gate.json')
    qa_report_path = RUN/'qa_report.json'
    qa_report = json.loads(qa_report_path.read_text(encoding='utf-8'))
    qa_report['mp4_visual_product_gate'] = mp4_gate
    qa_report['passed'] = bool(qa_report.get('passed')) and bool(mp4_gate.get('passed'))
    qa_report_path.write_text(json.dumps(qa_report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PRODUCTION ARTIFACT READY:',RUN/'master_final.mp4')
    print('FINAL QA PASSED: master + 4 Shorts + Arabic subtitle evidence')


if __name__=='__main__': main()
