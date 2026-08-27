from __future__ import annotations
import json, os, re
from pathlib import Path
from odysseus_gateway import call, extract_json

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'config/production.json').read_text(encoding='utf-8'))


def words(s: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9'-]*\b", s))


def validate_story(story: dict) -> None:
    scenes = story.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != CFG['production']['long_scene_count']:
        raise ValueError('story must contain exactly 25 scenes')
    for i, sc in enumerate(scenes, 1):
        required = ('text_en', 'text_ar', 'visual_subject', 'pexels_query', 'beat')
        if not all(str(sc.get(k, '')).strip() for k in required):
            raise ValueError(f'scene {i} missing required fields')
        n = words(sc['text_en'])
        if not 45 <= n <= 70:
            raise ValueError(f'scene {i} has invalid English word count: {n}')
        if re.search(r'[\u0600-\u06ff]', sc['text_en']):
            raise ValueError(f'scene {i} English contains Arabic')
        if not re.search(r'[\u0600-\u06ff]', sc['text_ar']):
            raise ValueError(f'scene {i} Arabic missing')


def prompt(topic: str) -> str:
    return json.dumps({'task':'long_story','topic':topic,'contract':{'scenes':25,'scene_words':'45-70','language':'en narrative + ar translation','required_fields':['text_en','text_ar','visual_subject','pexels_query','beat'],'beats':['hook','setup','mystery','escalation','evidence','reveal','payoff','ending']},'output':'JSON object with scenes array'}, ensure_ascii=False)


def generate() -> dict:
    run=Path(os.getenv('RUN_DIR',str(ROOT/'data/run'))); run.mkdir(parents=True,exist_ok=True)
    message=prompt(os.getenv('VIDEO_TOPIC','The hidden story behind a surprising historical event'))
    model=os.getenv('ODYSSEUS_STORY_MODEL','aqaaab/story')
    body=call(message,model=model)
    story=extract_json(body)
    validate_story(story)
    story['provider']=body.get('provider','Odysseus')
    (run/'long_story.json').write_text(json.dumps(story,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"STORY_GENERATION=PASS provider={story['provider']} scenes={len(story['scenes'])}")
    return story
