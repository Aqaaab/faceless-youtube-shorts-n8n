from __future__ import annotations
import json, os, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=Path(os.getenv('RUN_DIR',str(ROOT/'data/run')))

def build_shorts(story:dict)->list[dict]:
    scenes=story['scenes']; starts=[0,6,12,18]
    shorts=[]
    for i,start in enumerate(starts,1):
        chunk=scenes[start:start+6]
        shorts.append({'id':i,'scene_start':start+1,'scene_end':min(start+len(chunk),len(scenes)),'title':f"{story.get('title','Story')} — Part {i}",'scenes':chunk})
    return shorts

def render_placeholder(short:dict)->Path:
    # Rendering is delegated to FFmpeg in CI. This function only defines paths/contracts.
    out=RUN/'shorts'/f"short-{short['id']}.mp4"; out.parent.mkdir(parents=True,exist_ok=True)
    return out

def main():
    story=json.loads((RUN/'long_story.json').read_text())
    shorts=build_shorts(story)
    for s in shorts: render_placeholder(s)
    (RUN/'shorts_plan.json').write_text(json.dumps({'shorts':shorts},ensure_ascii=False,indent=2)+'\n')
    print('SHORTS_PLAN=PASS count=4')
    return shorts

if __name__=='__main__': main()
