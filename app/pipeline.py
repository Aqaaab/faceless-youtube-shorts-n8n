from __future__ import annotations
import argparse, json, os, shutil
from pathlib import Path
from .arabic_font import ensure_ready
from .checkpoint import begin as checkpoint_begin, load as checkpoint_load, mark as checkpoint_mark, stage_done
from .core import RUN, _deterministic_structure_repair, _normalize_for_validation, _story_from_data, ask_odysseus, save_story, load_story
from .profile import load_profile
from .validator import validate_story, validate_story_data, validate_short_selection
from .tts import generate_tts, synchronize_scene_durations, validate_tts_timing
from .story_visuals import generate_visuals
from .vertical_visuals import generate_vertical_visuals
from .short_selector import select_shorts, load_selected
from .render import render_long, render_shorts, write_srt, burn_subtitles
from .thumbnail import generate_thumbnail
from .artifact_gate import qa

STORY_SYSTEM='''Output JSON only. Create an Arabic premium automotive story with EXACTLY 25 scenes, ids 1..25. Each scene has 30-45 Arabic narration words, visual_intent, layout, grounded callouts and provisional duration 18 seconds. Use at least 4 layouts, 12 callout scenes and 20 distinct visual intents. Return four unique Arabic short titles as provisional metadata only; never assume fixed scene pairs. Do not invent specifications. Visual direction is premium photorealistic automotive editorial with the vehicle as primary subject.'''
REPAIR_SYSTEM=STORY_SYSTEM

def generate_story_resilient(topic):
    attempts=max(1,int(os.getenv("STORY_GENERATION_ATTEMPTS","2"))); repairs=max(1,int(os.getenv("STORY_REPAIR_ATTEMPTS","2"))); last="unknown"
    for _ in range(attempts):
        data=ask_odysseus(STORY_SYSTEM,f"Create the production story for this topic: {topic}",timeout=float(os.getenv("STORY_GENERATION_TIMEOUT","180")))
        for attempt in range(repairs+1):
            candidate=_deterministic_structure_repair(_normalize_for_validation(data))
            try:
                validate_story_data(candidate); return _story_from_data(candidate,topic)
            except Exception as exc:
                last=str(exc)
            if attempt<repairs:
                data=ask_odysseus(REPAIR_SYSTEM,f"Topic: {topic}\nFailure: {last}\nCurrent JSON:\n{json.dumps(candidate,ensure_ascii=False,separators=(',',':'))}",timeout=float(os.getenv("STORY_REPAIR_TIMEOUT","180")))
    raise RuntimeError(f"Story generation failed: {last}")

def _scene_artifacts():
    return [p for sid in range(1,26) for p in (RUN/"scenes"/f"scene_{sid:02d}.mp4",RUN/"scenes"/f"scene_{sid:02d}.png",RUN/"scenes"/f"scene_{sid:02d}.json")]

def _short_artifacts():
    return [RUN/"short_candidates.json",RUN/"short_subtitles_burn.json",*(RUN/"shorts"/f"short_{i}.mp4" for i in range(1,5))]

def _run_stage(state,name,artifacts,fn):
    if stage_done(state,name,artifacts): return
    checkpoint_mark(state,RUN,name,"running",artifacts)
    try:
        fn()
        if not stage_done(state,name,artifacts): raise RuntimeError(f"stage {name} completed without required artifacts")
        checkpoint_mark(state,RUN,name,"done",artifacts)
    except Exception as exc:
        checkpoint_mark(state,RUN,name,"failed",artifacts,str(exc)); raise

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--topic",default=os.getenv("CAR_TOPIC",""))
    ap.add_argument("--profile",default=os.getenv("AUTOMOTIVE_PROFILE","premium_coupe"))
    ap.add_argument("--reset",action="store_true")
    args=ap.parse_args()
    topic=args.topic.strip()
    if not topic: raise SystemExit("CAR_TOPIC is required")
    os.environ["AUTOMOTIVE_PROFILE"]=args.profile; load_profile(args.profile)
    if args.reset and RUN.exists(): shutil.rmtree(RUN)
    RUN.mkdir(parents=True,exist_ok=True)
    state=checkpoint_begin(RUN,topic,args.profile,reset=args.reset); state=checkpoint_load(RUN)
    ensure_ready(RUN/"arabic_font_gate.json",strict=True)
    story_path=RUN/"story.json"
    if stage_done(state,"story",[story_path]):
        story=load_story(story_path); validate_story(story_path)
    else:
        if not os.getenv("ODYSSEUS_GATEWAY_BASE_URL") or not os.getenv("ODYSSEUS_GATEWAY_API_KEY"):
            raise RuntimeError("Odysseus gateway credentials are required")
        story=generate_story_resilient(topic); save_story(story,story_path); validate_story(story_path)
        checkpoint_mark(state,RUN,"story","done",[story_path])
    tts_artifacts=[RUN/"tts_durations.json",*(RUN/"audio"/f"scene_{sid:02d}.{ext}" for sid in range(1,26) for ext in ("mp3","words.json"))]
    if stage_done(state,"tts",tts_artifacts):
        durations={int(k):float(v) for k,v in json.loads((RUN/"tts_durations.json").read_text(encoding="utf-8")).items()}
    else:
        durations=generate_tts(story); synchronize_scene_durations(story,durations); validate_tts_timing(story,durations); save_story(story,story_path)
        (RUN/"tts_durations.json").write_text(json.dumps(durations,ensure_ascii=False,indent=2),encoding="utf-8")
        checkpoint_mark(state,RUN,"tts","done",tts_artifacts)
    synchronize_scene_durations(story,durations); validate_tts_timing(story,durations); save_story(story,story_path)
    _run_stage(state,"visuals",_scene_artifacts(),lambda:generate_visuals(story,RUN/"scenes"))
    candidates_path=RUN/"short_candidates.json"
    if not stage_done(state,"short_selection",[candidates_path]):
        select_shorts(story,RUN/"scenes",candidates_path)
        manifest=json.loads(candidates_path.read_text(encoding="utf-8")); validate_short_selection(manifest)
        story.short_titles=[str(x["title"]).strip() for x in manifest["selected"]]; save_story(story,story_path); validate_story(story_path)
        checkpoint_mark(state,RUN,"short_selection","done",[candidates_path])
    selected=load_selected(candidates_path)
    selected_ids=sorted({int(sid) for item in selected for sid in item["scene_ids"]})
    vertical_artifacts=[RUN/"vertical_scenes"/f"scene_{sid:02d}.{ext}" for sid in selected_ids for ext in ("mp4","png","json")]
    _run_stage(state,"vertical_visuals",vertical_artifacts,lambda:generate_vertical_visuals(story,RUN/"vertical_scenes",selected_ids))
    _run_stage(state,"long_render",[RUN/"master.mp4"],lambda:render_long(story,RUN/"master.mp4"))
    srt=RUN/"arabic.srt"; final=RUN/"master_final.mp4"
    _run_stage(state,"subtitles",[srt,final,RUN/"subtitle_burn.json"],lambda:(write_srt(story,srt),burn_subtitles(RUN/"master.mp4",srt,final)))
    _run_stage(state,"short_render",_short_artifacts(),lambda:render_shorts(story,RUN/"shorts"))
    _run_stage(state,"thumbnail",[RUN/"thumbnail.jpg"],lambda:generate_thumbnail(story,RUN/"thumbnail.jpg"))
    report=qa(story,final,[RUN/"shorts"/f"short_{i}.mp4" for i in range(1,5)])
    checkpoint_mark(state,RUN,"final_qa","done",[RUN/"qa_report.json",final,RUN/"thumbnail.jpg",RUN/"visual_product_gate.json",RUN/"mp4_visual_product_gate.json"])
    print("PRODUCTION ARTIFACT READY:",final)
    print(json.dumps({"renderer":"wangp","weighted_score_10":report["weighted_score_10"],"shorts":4},ensure_ascii=False))

if __name__=="__main__":
    main()
