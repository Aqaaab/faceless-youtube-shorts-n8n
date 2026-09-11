import argparse, os, shutil, json
from .core import generate_story, save_story, RUN
from .validator import validate_story
from .story_visuals import generate_visuals
from .tts import generate_tts, validate_tts_timing
from .render import render_long, write_srt, burn_subtitles, render_shorts
from .qa import qa


def clean_run():
    if RUN.exists(): shutil.rmtree(RUN)
    RUN.mkdir(parents=True, exist_ok=True)


def _require(path):
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"required production artifact missing: {path}")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--topic',default=os.getenv('CAR_TOPIC','')); args=ap.parse_args()
    if not args.topic.strip(): raise SystemExit('CAR_TOPIC is required')
    if not os.getenv('ODYSSEUS_GATEWAY_BASE_URL') or not os.getenv('ODYSSEUS_GATEWAY_API_KEY'):
        raise SystemExit('Odysseus gateway credentials are required')
    clean_run()
    story=generate_story(args.topic.strip()); save_story(story); validate_story()
    generate_visuals(story)
    tts_durations=generate_tts(story)
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
    print('PRODUCTION ARTIFACT READY:',RUN/'master_final.mp4')
    print('FINAL QA PASSED: master + 4 Shorts + Arabic subtitle evidence')


if __name__=='__main__': main()
