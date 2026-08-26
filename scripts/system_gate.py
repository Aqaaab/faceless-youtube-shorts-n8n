from __future__ import annotations
import ast, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    production=json.loads((ROOT/'config/production.json').read_text(encoding='utf-8'))
    ody=json.loads((ROOT/'config/odysseus.json').read_text(encoding='utf-8'))
    providers=json.loads((ROOT/'config/providers.json').read_text(encoding='utf-8'))
    required=['scripts/provider_registry.py','scripts/ai_router.py','scripts/odysseus_gateway.py','scripts/story_pipeline.py','scripts/shorts_pipeline.py','scripts/renderer.py','scripts/qa.py','scripts/production.py','scripts/system_gate.py']
    for rel in required:
        p=ROOT/rel; assert p.is_file(), f'missing {rel}'
        if p.suffix=='.py': ast.parse(p.read_text(encoding='utf-8'))
    assert production['primary']['name']=='Odysseus'
    assert production['production']['long_video_count']==1
    assert production['production']['short_count']==4
    assert production['production']['long_duration_seconds']=={'min':420,'max':900}
    assert production['production']['short_resolution']==[1080,1920]
    assert ody['enabled'] is True
    assert ody['endpoint']=='/api/v1/chat'
    assert ody['provider_keys_sent_to_odysseus'] is False
    assert ody['fallback']=='scripts/ai_router.py'
    ids=set()
    for p in providers['providers']:
        assert p['id'] not in ids; ids.add(p['id'])
        assert p['type']=='openai_compatible'
        assert p['task']=='long_story'
        assert p['enabled'] is False
    workflow=(ROOT/'.github/workflows/daily-production.yml').read_text(encoding='utf-8')
    assert 'python scripts/production.py' in workflow
    assert 'ODYSSEUS_GATEWAY_BASE_URL' in workflow and 'ODYSSEUS_GATEWAY_API_KEY' in workflow
    assert '/api/chat' not in workflow
    print('SYSTEM_GATE=PASS')
    print('FILE_IMPORT_CONTRACT=PASS')
    print('PROVIDER_REGISTRY=PASS')
    print('ODYSSEUS_GATEWAY=PASS')
    print('ODYSSEUS_PRIMARY=PASS')
    print('ROUTER_FALLBACK=PASS')
    print('LONG_VIDEO_CONTRACT=PASS')
    print('FOUR_SHORTS_CONTRACT=PASS')
