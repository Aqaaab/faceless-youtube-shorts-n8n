#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config/provider-mesh.json'
REQUIRED_TASKS={'research','trends','story','hook','rewrite_qa','tts','speech_to_text','visual_search','image_generation','video_render','audio_mix','music','thumbnail','media_qa','youtube_publish','instagram_publish','analytics'}

def main():
    c=json.loads(CFG.read_text(encoding='utf-8'))
    assert c['policy']['prefer_sustainable_free'] is True
    assert c['policy']['never_treat_trial_credit_as_permanent_free'] is True
    assert c['policy']['fallback_stays_within_task'] is True
    tasks=c['tasks']; providers=c['providers']
    assert REQUIRED_TASKS <= set(tasks)
    for task,meta in tasks.items():
        names=list(meta.get('primary',[]))+list(meta.get('secondary',[]))
        assert names, f'no provider for task {task}'
        for name in names:
            if name == 'AqaaabAI Router':
                continue
            assert name in providers, f'missing provider metadata: {name}'
            p=providers[name]
            assert p['task'] == task or (task in ('trends','youtube_publish') and name=='YouTubeDataAPI') or (task=='analytics' and name in ('YouTubeAnalyticsAPI','InstagramInsights')), f'task mismatch: {task}->{name}'
    for name,p in providers.items():
        if p.get('type') == 'remote_trial':
            assert p.get('enabled') is False
    assert providers['Pexels']['enabled'] is True
    assert providers['FFmpeg']['enabled'] is True
    assert providers['FFprobe']['enabled'] is True
    assert providers['EdgeTTS']['enabled'] is True
    assert providers['Kokoro']['enabled'] is True
    assert providers['WhisperLocal']['enabled'] is True
    assert providers['YouTubeDataAPI']['enabled'] is True
    print('PROVIDER_MESH_TASK_COUNT='+str(len(tasks)))
    print('PROVIDER_MESH_PROVIDER_COUNT='+str(len(providers)))
    print('PROVIDER_MESH_TASK_COVERAGE=PASS')
    print('PROVIDER_MESH_TRIAL_GUARD=PASS')
    print('PROVIDER_MESH_CORE_LOCAL_PATHS=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
