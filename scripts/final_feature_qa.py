#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, subprocess, sys
from pathlib import Path

RUN_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('RUN_DIR', 'data/run'))
VIDEO = RUN_DIR / 'video.mp4'; CONTRACT = RUN_DIR / 'render_contract.json'
def run(*args: str) -> str: return subprocess.check_output(args, text=True).strip()
def probe_stream(selector: str) -> dict:
    data=json.loads(run('ffprobe','-v','error','-select_streams',selector,'-show_entries','stream=index,codec_name,codec_type,width,height,r_frame_rate,pix_fmt,sample_rate,channels','-of','json',str(VIDEO))); streams=data.get('streams') or []
    if not streams: raise SystemExit(f'FINAL_FEATURE_QA_FAIL: stream missing for selector {selector}')
    return streams[0]
def duration(path: Path) -> float: return float(run('ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)))
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> int:
    if not VIDEO.is_file() or VIDEO.stat().st_size < 10000: raise SystemExit('FINAL_FEATURE_QA_FAIL: final video missing or empty')
    if not CONTRACT.is_file(): raise SystemExit('FINAL_FEATURE_QA_FAIL: render_contract.json missing')
    c=json.loads(CONTRACT.read_text(encoding='utf-8')); fmt=str(c.get('format','short')).lower(); long_form=fmt in {'patent','long_form'}
    required=['ai_provider','music','animation','arabic_subtitles','english_voice','final_video']; missing=[k for k in required if k not in c]
    if missing: raise SystemExit('FINAL_FEATURE_QA_FAIL: contract missing '+','.join(missing))
    if c.get('english_spoken') is not True or c.get('english_overlay') is not False or c.get('arabic_overlay') is not True: raise SystemExit('FINAL_FEATURE_QA_FAIL: subtitle/audio overlay contract mismatch')
    if not c['english_voice']['required'] or not c['english_voice']['present']: raise SystemExit('FINAL_FEATURE_QA_FAIL: English voice missing')
    voice_file=RUN_DIR/c['english_voice']['file'];
    if not voice_file.is_file() or voice_file.stat().st_size<1000: raise SystemExit('FINAL_FEATURE_QA_FAIL: declared English voice file missing')
    if not c['arabic_subtitles']['required'] or not c['arabic_subtitles']['present']: raise SystemExit('FINAL_FEATURE_QA_FAIL: Arabic subtitles missing')
    ass_file=RUN_DIR/c['arabic_subtitles']['file'];
    if not ass_file.is_file() or ass_file.stat().st_size<100: raise SystemExit('FINAL_FEATURE_QA_FAIL: declared Arabic subtitle file missing')
    if c['music']['required']:
        mix_rel=c['music'].get('mixed_file')
        if not c['music']['present'] or not mix_rel: raise SystemExit('FINAL_FEATURE_QA_FAIL: required music is not mixed into final audio')
        mix_file=RUN_DIR/mix_rel
        if not mix_file.is_file() or mix_file.stat().st_size<1000: raise SystemExit('FINAL_FEATURE_QA_FAIL: declared music mix file missing')
        if sha(voice_file)==sha(mix_file): raise SystemExit('FINAL_FEATURE_QA_FAIL: final mix is byte-identical to voice-only audio')
        if abs(duration(voice_file)-duration(mix_file))>0.25: raise SystemExit('FINAL_FEATURE_QA_FAIL: voice/mix duration mismatch')
    if c['animation']['required']:
        score=float(c['animation'].get('measured_zoom_ratio',0));
        if not c['animation']['present'] or score<0.06: raise SystemExit(f'FINAL_FEATURE_QA_FAIL: animation motion ratio too low ({score:.4f})')
    provider=str(c['ai_provider'].get('provider',''))
    if not provider or provider in {'deterministic-fallback','baseline-fallback'}: raise SystemExit(f'FINAL_FEATURE_QA_FAIL: non-AI fallback provider is not allowed: {provider}')
    if not c['final_video'].get('finalized'): raise SystemExit('FINAL_FEATURE_QA_FAIL: final_video contract not finalized')
    d=duration(VIDEO)
    if long_form:
        if not 420 <= d <= 900: raise SystemExit(f'FINAL_FEATURE_QA_FAIL: long-form duration {d:.2f}s outside 420-900s')
        expected=(1920,1080)
    else:
        if not 28 <= d <= 45: raise SystemExit(f'FINAL_FEATURE_QA_FAIL: Shorts duration {d:.2f}s outside 28-45s')
        expected=(1080,1920)
    video_stream=probe_stream('v:0')
    if video_stream.get('codec_type')!='video': raise SystemExit('FINAL_FEATURE_QA_FAIL: first video stream is not video')
    if (video_stream.get('width'),video_stream.get('height'))!=expected: raise SystemExit(f"FINAL_FEATURE_QA_FAIL: dimensions {video_stream.get('width')}x{video_stream.get('height')} expected {expected[0]}x{expected[1]}")
    if video_stream.get('r_frame_rate') not in {'30/1','30'}: raise SystemExit(f"FINAL_FEATURE_QA_FAIL: FPS {video_stream.get('r_frame_rate')}")
    if video_stream.get('pix_fmt')!='yuv420p' or video_stream.get('codec_name')!='h264': raise SystemExit('FINAL_FEATURE_QA_FAIL: final video encoding contract failed')
    audio_stream=probe_stream('a:0')
    if audio_stream.get('codec_type')!='audio' or audio_stream.get('codec_name')!='aac': raise SystemExit('FINAL_FEATURE_QA_FAIL: final audio is not AAC')
    if int(audio_stream.get('channels') or 0)<1: raise SystemExit('FINAL_FEATURE_QA_FAIL: final audio has no channels')
    if int(audio_stream.get('sample_rate') or 0)!=48000: raise SystemExit(f"FINAL_FEATURE_QA_FAIL: final audio sample rate {audio_stream.get('sample_rate')}")
    report={'status':'PASS','format':fmt,'duration_seconds':d,'provider':provider,'music':c['music'],'animation':c['animation'],'arabic_subtitles':c['arabic_subtitles'],'video':{'codec':video_stream.get('codec_name'),'width':video_stream.get('width'),'height':video_stream.get('height'),'fps':video_stream.get('r_frame_rate'),'pix_fmt':video_stream.get('pix_fmt')},'final_audio':{'codec':audio_stream.get('codec_name'),'channels':audio_stream.get('channels'),'sample_rate':audio_stream.get('sample_rate')}}
    (RUN_DIR/'final_feature_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(report,ensure_ascii=False,indent=2)); print('FINAL_FEATURE_QA=PASS'); return 0
if __name__=='__main__': raise SystemExit(main())
