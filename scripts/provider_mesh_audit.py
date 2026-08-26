#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / 'config' / 'provider-mesh.json'
REQUIRED_TASKS = {'research','trends','story','hook','rewrite_qa','tts','speech_to_text','visual_search','image_generation','video_render','audio_mix','music','thumbnail','media_qa','youtube_publish','instagram_publish','analytics'}
PLATFORM_SINGLE_SOURCE = {'youtube_publish','instagram_publish'}

def main():
    c=json.loads(CFG.read_text(encoding='utf-8'))
    policy=c['policy']; tasks=c['tasks']; providers=c['providers']
    assert policy['prefer_sustainable_free'] is True
    assert policy['never_treat_trial_credit_as_permanent_free'] is True
    assert policy['fallback_stays_within_task'] is True
    assert policy['required_remote_or_local_candidates_per_task'] == 3
    assert REQUIRED_TASKS <= set(tasks)
    for task,meta in tasks.items():
        chain=[meta.get('primary'),meta.get('backup_1'),meta.get('backup_2')]
        assert all(isinstance(x,str) and x for x in chain), f'{task}: incomplete fallback chain'
        assert len(set(chain)) == 3, f'{task}: duplicate fallback provider'
        for name in chain:
            assert name in providers or name == 'AqaaabAIRouter', f'{task}: missing provider metadata {name}'
            if name == 'AqaaabAIRouter':
                continue
            p=providers[name]
            if p.get('platform_single_source'):
                assert task in PLATFORM_SINGLE_SOURCE, f'{task}: invalid platform adapter placement'
    for name,p in providers.items():
        if p.get('type') == 'remote_trial':
            assert p.get('enabled') is False, f'{name}: remote trial must remain disabled until live verification'
    assert providers['Pexels']['enabled'] is True
    assert providers['FFmpeg']['enabled'] is True
    assert providers['FFprobe']['enabled'] is True
    assert providers['EdgeTTS']['enabled'] is True
    assert providers['Kokoro']['enabled'] is True
    assert providers['WhisperLocal']['enabled'] is True
    assert providers['YouTubeDataAPI']['enabled'] is True
    print('PROVIDER_MESH_TASK_COUNT='+str(len(tasks)))
    print('PROVIDER_MESH_PROVIDER_COUNT='+str(len(providers)))
    print('PROVIDER_MESH_3_PROVIDER_CHAINS=PASS')
    print('PROVIDER_MESH_TRIAL_GUARD=PASS')
    print('PROVIDER_MESH_CORE_LOCAL_PATHS=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
