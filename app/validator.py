import json, re, sys
from pathlib import Path
from .core import Story, Scene

def validate_story(path=Path("work/story.json")):
    data=json.loads(path.read_text(encoding='utf-8'))
    errors=[]
    scenes=data.get('scenes',[])
    if len(scenes)!=25: errors.append(f"scene count must be 25, got {len(scenes)}")
    total=sum(float(s.get('duration',0)) for s in scenes)
    if not 420<=total<=900: errors.append(f"planned duration {total:.1f}s outside 420-900")
    for s in scenes:
        for k in ('id','narration','visual_intent','layout','duration'):
            if not s.get(k): errors.append(f"scene {s.get('id')} missing {k}")
        if len(s.get('narration','').split())<8: errors.append(f"scene {s.get('id')} narration too short")
    if not data.get('title') or data.get('title')=='Untitled Story': errors.append('weak/missing title')
    if re.search(r'pexels',path.read_text(encoding='utf-8'),re.I): errors.append('forbidden Pexels reference')
    if errors: raise AssertionError('; '.join(errors))
    return True

if __name__=='__main__': validate_story()
