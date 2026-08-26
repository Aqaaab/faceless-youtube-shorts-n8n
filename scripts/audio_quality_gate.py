#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN_DIR=Path(os.environ.get('RUN_DIR','data/run'))

def duration(path: Path) -> float:
    if not path.is_file() or not shutil.which('ffprobe'): return 0.0
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(path)],capture_output=True,text=True)
    try:return float(p.stdout.strip() or 0)
    except:return 0.0

def main():
    video=RUN_DIR/'video.mp4'
    if not video.is_file(): raise SystemExit('AUDIO_GATE_VIDEO_MISSING')
    streams=[]
    if shutil.which('ffprobe'):
        p=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name,sample_rate,channels','-of','json',str(video)],capture_output=True,text=True,check=True)
        streams=json.loads(p.stdout).get('streams',[])
    audio=[s for s in streams if s.get('codec_type')=='audio']
    ok=bool(audio) and audio[0].get('channels',0)>=1 and audio[0].get('sample_rate') in ('48000',48000)
    payload={'stage':'audio_quality_gate','audio_present':bool(audio),'sample_rate':audio[0].get('sample_rate') if audio else None,'channels':audio[0].get('channels') if audio else None,'duration_seconds':duration(video),'pass':ok}
    (RUN_DIR/'audio_quality.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not ok: raise SystemExit('AUDIO_QA_FAILED')
    print('AUDIO_QA=PASS sample_rate=48000')
if __name__=='__main__': main()
