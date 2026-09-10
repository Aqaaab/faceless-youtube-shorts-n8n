import json
import re
from pathlib import Path

def _words(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))

def validate_story(path=Path('work/story.json')):
    data=json.loads(path.read_text(encoding='utf-8')); errors=[]; scenes=data.get('scenes',[])
    if len(scenes)!=25: errors.append(f'scene count must be exactly 25, got {len(scenes)}')
    ids=[s.get('id') for s in scenes]
    if ids != list(range(1,26)): errors.append(f'scene ids must be exactly 1..25, got {ids}')
    total=sum(float(s.get('duration',0)) for s in scenes)
    if not 420<=total<=900: errors.append(f'planned duration {total:.1f}s outside 420-900')
    for s in scenes:
        sid=s.get('id')
        for k in ('id','narration','visual_intent','layout','duration'):
            if s.get(k) in (None,'',[]): errors.append(f'scene {sid} missing {k}')
        try:
            d=float(s.get('duration',0))
            if not 5<=d<=60: errors.append(f'scene {sid} duration {d:.1f}s outside 5-60')
        except (TypeError,ValueError): errors.append(f'scene {sid} duration is not numeric')
        wc=_words(s.get('narration',''))
        if wc<25: errors.append(f'scene {sid} narration too short ({wc} words; minimum 25)')
        if len(s.get('callouts',[]))>5: errors.append(f'scene {sid} has more than 5 callouts')
    title=str(data.get('title','')).strip(); description=str(data.get('description','')).strip(); tags=data.get('tags',[])
    if not title or title.lower() in {'untitled story','untitled'}: errors.append('weak/missing title')
    if len(title)<12: errors.append('title must be at least 12 characters')
    if len(description)<80: errors.append('description must be at least 80 characters')
    if not isinstance(tags,list) or len(tags)<3: errors.append('at least 3 tags are required')
    if errors: raise AssertionError('; '.join(errors))
    return True

if __name__=='__main__': validate_story()
