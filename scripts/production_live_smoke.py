#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, subprocess, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'config/ai-router.json').read_text(encoding='utf-8'))
PLAN = json.loads((ROOT / 'config/provider-activation-plan.json').read_text(encoding='utf-8'))
MESH = json.loads((ROOT / 'config/provider-mesh.json').read_text(encoding='utf-8'))
DAILY = (ROOT / '.github/workflows/daily-production-v2.yml').read_text(encoding='utf-8')

def command_exists(name: str) -> bool:
    return shutil.which(name) is not None

def live_router_smoke() -> tuple[dict, str, str | None]:
    from ai_router import build_long_story_router
    router = build_long_story_router()
    if not router.providers:
        raise RuntimeError('No eligible live providers are configured for the long_story task')
    prompt = '{"task":"live_smoke","instruction":"Return exactly this JSON object: {\\"ok\\":true,\\"task\\":\\"live_smoke\\"}"}'
    result, provider, model = router.route(prompt, wait_for_ready=False)
    if not isinstance(result, dict) or result.get('ok') is not True or result.get('task') != 'live_smoke':
        raise RuntimeError(f'Live router returned invalid result: {result!r}')
    return result, provider, model

def pexels_smoke() -> None:
    key = os.getenv('PEXELS_API_KEY')
    if not key:
        raise RuntimeError('PEXELS_API_KEY is required for the live visual provider smoke test')
    req = urllib.request.Request(
        'https://api.pexels.com/v1/search?query=cinematic&per_page=1',
        headers={'Authorization': key, 'User-Agent': 'aqaaab-production-live-smoke/1.0'},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8', 'replace'))
    photos = payload.get('photos') or []
    if not photos or not photos[0].get('src', {}).get('landscape'):
        raise RuntimeError('Pexels live smoke returned no usable asset')

def main() -> int:
    if 'len(p[\'providers\']) == 11' in DAILY or 'len(p["providers"]) == 11' in DAILY:
        raise RuntimeError('DAILY_PRODUCTION_WORKFLOW_IS_STALE: hardcoded provider count 11 remains in daily-production-v2.yml')
    if 'len(active)==11' in DAILY or 'len(active) == 11' in DAILY:
        raise RuntimeError('DAILY_PRODUCTION_WORKFLOW_IS_STALE: hardcoded activation count 11 remains in daily-production-v2.yml')
    long_story = CFG['tasks']['long_story']
    assert long_story['slot_count'] == 5
    assert long_story['slot_scene_count'] == 5
    assert long_story['mode'] == 'fixed_slots'
    assert len(long_story['providers']) >= 20
    assert len(PLAN['providers']) >= 14
    assert MESH['policy']['fallback_stays_within_task'] is True
    assert all(MESH['tasks']['hook'].get(k) for k in ('primary','backup_1','backup_2'))
    if not command_exists('ffmpeg'):
        raise RuntimeError('ffmpeg is missing')
    if not command_exists('ffprobe'):
        raise RuntimeError('ffprobe is missing')
    result, provider, model = live_router_smoke()
    pexels_smoke()
    ffmpeg = subprocess.run(['ffmpeg','-version'],capture_output=True,text=True,timeout=15)
    if ffmpeg.returncode != 0:
        raise RuntimeError('ffmpeg execution failed')
    print('DAILY_WORKFLOW_CONTRACT=PASS')
    print('FIXED_SLOT_CONFIG=PASS')
    print(f'LIVE_ROUTER_INFERENCE=PASS provider={provider} model={model}')
    print(f'LIVE_ROUTER_RESULT={json.dumps(result,ensure_ascii=False,separators=(",",":"))}')
    print('LIVE_PEXELS_INFERENCE=PASS')
    print('FFMPEG_EXECUTION=PASS')
    print('PRODUCTION_LIVE_SMOKE=PASS')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
