from __future__ import annotations
import json, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/production.json').read_text())

def duration(path:Path)->float:
    out=subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],text=True).strip()
    return float(out)

def main(run_dir:Path):
    story=json.loads((run_dir/'long_story.json').read_text())
    assert story.get('provider') in {'Odysseus','fallback'}
    assert len(story.get('scenes',[]))==25
    video=run_dir/'video.mp4'
    assert video.is_file() and video.stat().st_size>0
    d=duration(video)
    assert 420<=d<=900, d
    for i in range(1,5):
        p=run_dir/'shorts'/f'short-{i}.mp4'
        assert p.is_file() and p.stat().st_size>0
        sd=duration(p); assert 28<=sd<=59, sd
    print('PRODUCTION_QA=PASS')

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1] if len(sys.argv)>1 else ROOT/'data/run'))
