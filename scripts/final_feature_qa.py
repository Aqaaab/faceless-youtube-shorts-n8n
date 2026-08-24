#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

RUN_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('RUN_DIR', 'data/run'))
VIDEO = RUN_DIR / 'video.mp4'
CONTRACT = RUN_DIR / 'render_contract.json'


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def duration(path: Path) -> float:
    return float(run('ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)))


def stream_count(kind: str) -> int:
    return int(run('ffprobe','-v','error','-select_streams',kind,'-show_entries','stream=index','-of','csv=p=0',str(VIDEO)).count('\n') + (1 if run('ffprobe','-v','error','-select_streams',kind,'-show_entries','stream=index','-of','csv=p=0',str(VIDEO)) else 0))


def main() -> int:
    if not VIDEO.is_file() or VIDEO.stat().st_size < 10000:
        raise SystemExit('FINAL_FEATURE_QA_FAIL: final video missing or empty')
    if not CONTRACT.is_file():
        raise SystemExit('FINAL_FEATURE_QA_FAIL: render_contract.json missing')
    c = json.loads(CONTRACT.read_text(encoding='utf-8'))
    required = ['ai_provider','music','animation','arabic_subtitles','english_voice','final_video']
    missing = [k for k in required if k not in c]
    if missing:
        raise SystemExit('FINAL_FEATURE_QA_FAIL: contract missing ' + ','.join(missing))
    if not c['english_voice']['required'] or not c['english_voice']['present']:
        raise SystemExit('FINAL_FEATURE_QA_FAIL: English voice missing')
    if not c['arabic_subtitles']['required'] or not c['arabic_subtitles']['present']:
        raise SystemExit('FINAL_FEATURE_QA_FAIL: Arabic subtitles missing')
    if c['music']['required']:
        if not c['music']['present'] or not c['music'].get('mixed_file'):
            raise SystemExit('FINAL_FEATURE_QA_FAIL: required music is not mixed into final audio')
        if not (RUN_DIR / c['music']['mixed_file']).is_file():
            raise SystemExit('FINAL_FEATURE_QA_FAIL: declared music mix file missing')
    if c['animation']['required']:
        score = float(c['animation'].get('measured_zoom_ratio', 0))
        if not c['animation']['present'] or score < 0.06:
            raise SystemExit(f'FINAL_FEATURE_QA_FAIL: animation motion ratio too low ({score:.4f})')
    provider = str(c['ai_provider'].get('provider',''))
    if not provider or provider in {'deterministic-fallback','baseline-fallback'}:
        raise SystemExit(f'FINAL_FEATURE_QA_FAIL: non-AI fallback provider is not allowed: {provider}')
    if not c['final_video'].get('finalized'):
        raise SystemExit('FINAL_FEATURE_QA_FAIL: final_video contract not finalized')
    d = duration(VIDEO)
    if not 28 <= d <= 45:
        raise SystemExit(f'FINAL_FEATURE_QA_FAIL: duration {d:.2f}s outside 28-45s')
    v = run('ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate,pix_fmt,codec_name','-of','csv=p=0',str(VIDEO)).split(',')
    if v[:2] != ['1080','1920']:
        raise SystemExit(f'FINAL_FEATURE_QA_FAIL: dimensions {v[:2]}')
    if v[2] not in {'30/1','30'} or v[3] != 'yuv420p' or v[4] != 'h264':
        raise SystemExit('FINAL_FEATURE_QA_FAIL: final video encoding contract failed')
    if stream_count('a:0') < 1:
        raise SystemExit('FINAL_FEATURE_QA_FAIL: no final audio stream')
    report = {'status':'PASS','duration_seconds':d,'provider':provider,'music':c['music'],'animation':c['animation'],'arabic_subtitles':c['arabic_subtitles']}
    (RUN_DIR/'final_feature_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print('FINAL_FEATURE_QA=PASS')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
