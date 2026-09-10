import argparse, os, shutil
from pathlib import Path
from .core import generate_story, save_story, RUN
from .validator import validate_story
from .visuals import generate_visuals
from .tts import generate_tts
from .render import render_long, write_srt, burn_subtitles, render_shorts
from .qa import qa

def clean_run():
    if RUN.exists(): shutil.rmtree(RUN)
    RUN.mkdir(parents=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--topic',default=os.getenv('CAR_TOPIC',''))
    args=ap.parse_args()
    if not args.topic.strip(): raise SystemExit('CAR_TOPIC is required')
    clean_run()
    story=generate_story(args.topic.strip()); save_story(story)
    validate_story()
    generate_visuals(story)
    generate_tts(story)
    render_long(story)
    write_srt(story)
    burn_subtitles(RUN/'master.mp4',RUN/'arabic.srt',RUN/'master_final.mp4')
    render_shorts(story)
    shorts=[RUN/'shorts'/f'short_{i}.mp4' for i in range(1,5)]
    qa(story,RUN/'master_final.mp4',shorts)
    print('PRODUCTION ARTIFACT READY:',RUN/'master_final.mp4')
    print('All publishing gates passed. Upload is the next isolated stage.')

if __name__=='__main__': main()
