#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, subprocess, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/ai-router.json').read_text(encoding='utf-8'))
PLAN=json.loads((ROOT/'config/provider-activation-plan.json').read_text(encoding='utf-8'))
MESH=json.loads((ROOT/'config/provider-mesh.json').read_text(encoding='utf-8'))
DAILY=(ROOT/'.github/workflows/daily-production.yml').read_text(encoding='utf-8')

def command_exists(name:str)->bool:
    return shutil.which(name) is not None

def live_router_smoke()->tuple[dict,str,str|None]:
    from ai_router import build_long_story_router
    router=build_long_story_router()
    if not router.providers:
        raise RuntimeError('No eligible live providers are configured for long_story')
    prompt='{\"task\":\"live_smoke\",\"instruction\":\"Return exactly {\\\"ok\\\":true,\\\"task\\\":\\\"live_smoke\\\"}\"}'
    result,provider,model=router.route(prompt,wait_for_ready=False)
    if not isinstance(result,dict) or result.get('ok') is not True or result.get('task')!='live_smoke':
        raise RuntimeError(f'Live router returned invalid result: {result!r}')
    return result,provider,model

def pexels_smoke()->None:
    key=os.getenv('PEXELS_API_KEY')
    if not key: raise RuntimeError('PEXELS_API_KEY is required for live visual smoke')
    req=urllib.request.Request('https://api.pexels.com/v1/search?query=cinematic&per_page=1',headers={'Authorization':key,'User-Agent':'aqaaab-production-live-smoke/1.0'})
    with urllib.request.urlopen(req,timeout=30) as response:
        payload=json.loads(response.read().decode('utf-8','replace'))
    photos=payload.get('photos') or []
    if not photos or not photos[0].get('src',{}).get('landscape'):
        raise RuntimeError('Pexels live smoke returned no usable asset')

def ffmpeg_smoke()->None:
    if not command_exists('ffmpeg') or not command_exists('ffprobe'):
        raise RuntimeError('ffmpeg/ffprobe is missing')
    out=ROOT/'data'/'production-live-smoke'; out.mkdir(parents=True,exist_ok=True)
    test=out/'smoke.mp4'
    r=subprocess.run(['ffmpeg','-y','-f','lavfi','-i','color=c=black:s=320x180:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(test)],capture_output=True,text=True,timeout=30)
    if r.returncode!=0 or not test.exists() or test.stat().st_size<=0: raise RuntimeError('ffmpeg render smoke failed')
    q=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(test)],capture_output=True,text=True,timeout=15)
    if q.returncode!=0 or float((q.stdout or '0').strip() or 0)<=0: raise RuntimeError('ffprobe validation failed')

def main()->int:
    assert 'len(p[\'providers\']) == 11' not in DAILY
    assert 'daily-production-v2.yml' not in DAILY
    assert CFG['tasks']['long_story']['slot_count']==5
    assert CFG['tasks']['long_story']['slot_scene_count']==5
    assert CFG['tasks']['long_story']['mode']=='fixed_slots'
    assert len(CFG['tasks']['long_story']['providers'])>=20
    assert len(PLAN['providers'])>=14
    assert MESH['policy']['fallback_stays_within_task'] is True
    for task in MESH['tasks'].values():
        assert all(task.get(k) for k in ('primary','backup_1','backup_2'))
    result,provider,model=live_router_smoke()
    pexels_smoke()
    ffmpeg_smoke()
    print('DAILY_WORKFLOW_CONTRACT=PASS')
    print('FIXED_SLOT_CONFIG=PASS')
    print(f'LIVE_ROUTER_INFERENCE=PASS provider={provider} model={model}')
    print(f'LIVE_ROUTER_RESULT={json.dumps(result,ensure_ascii=False,separators=(",",":"))}')
    print('LIVE_PEXELS_INFERENCE=PASS')
    print('FFMPEG_RENDER_AND_FFPROBE=PASS')
    print('PRODUCTION_LIVE_SMOKE=PASS')
    return 0

if __name__=='__main__': raise SystemExit(main())
