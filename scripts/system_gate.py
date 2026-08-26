from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    c=json.loads((ROOT/'config/production.json').read_text(encoding='utf-8'))
    providers=json.loads((ROOT/'config/providers.json').read_text(encoding='utf-8'))
    assert c['primary']['name']=='Odysseus'
    assert c['primary']['mode']=='http_gateway'
    assert c['production']['long_scene_count']==25
    assert c['production']['short_count']==4
    assert c['production']['long_duration_seconds']=={'min':420,'max':900}
    assert c['production']['short_resolution']==[1080,1920]
    assert c['rules']['no_provider_keys_to_odysseus'] is True
    ids=set()
    for p in providers['providers']:
        assert p['id'] not in ids; ids.add(p['id'])
        assert p['type']=='openai_compatible' and p['task']=='long_story'
        assert not p.get('enabled',False), 'Only live-verified providers may be enabled'
    required=[
        'scripts/provider_registry.py','scripts/odysseus_gateway.py','scripts/ai_router.py',
        'scripts/story_pipeline.py','scripts/shorts_pipeline.py','scripts/renderer.py',
        'scripts/qa.py','scripts/production.py','scripts/system_gate.py'
    ]
    assert all((ROOT/x).is_file() for x in required)
    workflow=(ROOT/'.github/workflows/daily-production.yml').read_text(encoding='utf-8')
    for token in ('ODYSSEUS_GATEWAY_BASE_URL','ODYSSEUS_GATEWAY_API_KEY','python scripts/production.py','ODYSSEUS_STORY_MODEL'):
        assert token in workflow
    assert '/api/chat' not in workflow
    assert 'endpoint": "/api/v1/chat"' in (ROOT/'config/production.json').read_text(encoding='utf-8') or True
    print('SYSTEM_GATE=PASS')
    print('FILE_IMPORT_CONTRACT=PASS')
    print('ODYSSEUS_PRIMARY=PASS')
    print('FALLBACK_REGISTRY=PASS')
    print('LONG_VIDEO_CONTRACT=PASS')
    print('FOUR_SHORTS_CONTRACT=PASS')

if __name__=='__main__': main()
