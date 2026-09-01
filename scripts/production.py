from __future__ import annotations
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    os.environ.setdefault('RUN_DIR',str(ROOT/'data/run'))
    from story_pipeline import generate
    from shorts_pipeline import main as shorts
    from renderer_safe import main as render
    from qa import main as qa
    story=generate()
    shorts()
    render()
    qa(Path(os.environ['RUN_DIR']))
    print('PRODUCTION_PIPELINE=PASS')

if __name__=='__main__': main()
