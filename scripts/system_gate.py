from __future__ import annotations
import json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    c=json.loads((ROOT/'config/production.json').read_text())
    providers=json.loads((ROOT/'config/providers.json').read_text())
    assert c['primary']['name']=='Odysseus'
    assert c['primary']['mode']=='http_gateway'
    assert c['production']['long_scene_count']==25
    assert c['production']['short_count']==4
    assert c['production']['long_duration_seconds']=={'min':420,'max':900}
    assert c['rules']['no_provider_keys_to_odysseus'] is True
    ids=set()
    for p in providers['providers']:
        assert p['id'] not in ids; ids.add(p['id'])
        assert p['type']=='openai_compatible'
        assert p['task']=='long_story'
    required=[ROOT/'scripts/provider_registry.py',ROOT/'scripts/odysseus_gateway.py',ROOT/'scripts/story_pipeline.py',ROOT/'scripts/shorts_pipeline.py',ROOT/'scripts/renderer.py',ROOT/'scripts/qa.py',ROOT/'scripts/production.py']
    assert all(x.is_file() for x in required)
    workflow=ROOT/'.github/workflows/daily-production.yml'
    text=workflow.read_text()
    for token in ('ODYSSEUS_GATEWAY_BASE_URL','ODYSSEUS_GATEWAY_API_KEY','python scripts/production.py'):
        assert token in text
    assert '/api/chat' not in text
    print('SYSTEM_GATE=PASS')
    print('FILE_IMPORT_CONTRACT=PASS')
    print('ODYSSEUS_PRIMARY=PASS')
    print('FALLBACK_REGISTRY=PASS')
    print('LONG_VIDEO_CONTRACT=PASS')
    print('FOUR_SHORTS_CONTRACT=PASS')

if __name__=='__main__': main()
