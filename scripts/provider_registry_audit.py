#!/usr/bin/env python3
"""Static consistency audit for the canonical Aqaaab production provider registry."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config'/'ai-router.json'
PLAN=ROOT/'config'/'provider-activation-plan.json'
MESH=ROOT/'config'/'provider-mesh.json'
POOL=ROOT/'scripts'/'compatible_provider_pool.py'
DAILY_WORKFLOW=ROOT/'.github'/'workflows'/'daily-production.yml'
VALIDATION_WORKFLOW=ROOT/'.github'/'workflows'/'ai-router-validation.yml'
ROUTER=ROOT/'scripts'/'ai_router.py'
WORKFLOW_DIR=ROOT/'.github'/'workflows'

def main()->int:
    cfg=json.loads(CFG.read_text(encoding='utf-8'))
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    mesh=json.loads(MESH.read_text(encoding='utf-8'))
    registry=cfg.get('additional_providers',{})
    plan_entries=plan.get('providers',[])
    plan_names=[p['name'] for p in plan_entries]
    plan_by_name={p['name']:p for p in plan_entries}
    builtins={'OpenRouter','CloudflareWorkersAI'}
    dedicated={'FreeLLMAPI','Ollama'}
    pool=POOL.read_text(encoding='utf-8')
    daily=DAILY_WORKFLOW.read_text(encoding='utf-8')
    validation=VALIDATION_WORKFLOW.read_text(encoding='utf-8')
    router=ROUTER.read_text(encoding='utf-8')
    workflow_text=daily+'\n'+validation

    assert DAILY_WORKFLOW.is_file(), 'canonical daily-production.yml is missing'
    assert VALIDATION_WORKFLOW.is_file(), 'ai-router-validation.yml is missing'
    assert not (WORKFLOW_DIR/'daily-production-v2.yml').exists(), 'obsolete daily-production-v2.yml still exists'

    # Only operational workflows are checked for live legacy dependencies.
    # ai-router-validation.yml may mention legacy names in negative assertions.
    for path in WORKFLOW_DIR.glob('*.yml'):
        if path.name == 'ai-router-validation.yml':
            continue
        text=path.read_text(encoding='utf-8')
        assert 'daily-production-v2.yml' not in text, f'legacy workflow dependency remains: {path}'
        assert "len(p['providers']) == 11" not in text, f'stale provider count remains: {path}'
        assert 'len(p["providers"]) == 11' not in text, f'stale provider count remains: {path}'

    assert cfg['free_only'] is True and cfg['fail_closed'] is True
    assert 'GitHubModels' not in registry and 'ZAI' not in registry and 'ZAI' not in pool
    assert 'GitHubModels' not in plan_names and 'ZAI' not in plan_names
    assert len(registry) <= int(plan.get('policy',{}).get('max_provider_entries',100))
    assert set(plan_names) == (set(registry)-builtins) | dedicated
    assert set(plan.get('built_in_free_only_providers',[])) == builtins
    assert registry['OpenRouter']['default_model'].endswith(':free')
    assert registry['CloudflareWorkersAI']['free_only'] is True

    for name,meta in registry.items():
        if name in builtins:
            continue
        disabled=bool(meta.get('disabled_by_default',False) or plan_by_name.get(name,{}).get('disabled_by_default',False))
        if name not in pool:
            assert disabled, f'adapter missing for enabled provider: {name}'
            continue
        if meta.get('api_key_env'):
            assert meta['api_key_env'] in pool, f"secret adapter missing: {meta['api_key_env']}"
        if not disabled:
            if meta.get('api_key_env'):
                assert meta['api_key_env'] in workflow_text, f"workflow secret missing: {meta['api_key_env']}"
            flag=f'ENABLE_{name.upper()}_PROVIDER'
            assert flag in workflow_text, f'workflow enable flag missing: {flag}'
            if name=='Mistral':
                assert "ENABLE_MISTRAL_LONG_STORY_PROVIDER: 'true'" in workflow_text, 'Mistral long-story opt-in missing'

    for name in builtins:
        assert name in router
    for name in dedicated:
        assert name in router

    task_providers={x.split(':',1)[0] for x in cfg['tasks']['long_story']['providers']}
    for name,meta in registry.items():
        disabled=bool(meta.get('disabled_by_default',False) or plan_by_name.get(name,{}).get('disabled_by_default',False))
        if name in dedicated and name not in task_providers:
            continue
        if not disabled:
            assert name in task_providers or name in builtins, f'enabled provider missing from long_story task: {name}'

    for p in plan_entries:
        name=p['name']
        disabled=bool(p.get('disabled_by_default',False) or registry.get(name,{}).get('disabled_by_default',False))
        assert name in pool or name in router or disabled or name in dedicated, f'provider adapter/router missing: {name}'

    for task,meta in mesh['tasks'].items():
        for key in ('primary','backup_1','backup_2'):
            assert meta.get(key), f'mesh task missing {task}.{key}'

    assert 'scripts/compatible_provider_pool.py' in daily
    assert 'scripts/patent_story_engine.py' in daily
    assert 'ALLOW_DETERMINISTIC_FALLBACK: "false"' in daily

    print(f'PROVIDER_REGISTRY_COUNT={len(registry)}')
    print(f'PROVIDER_PLAN_COUNT={len(plan_names)}')
    print(f'BUILT_IN_FREE_PROVIDER_COUNT={len(builtins)}')
    print('PROVIDER_REGISTRY_MATCH=PASS')
    print('PROVIDER_ADAPTER_MATCH=PASS')
    print('PROVIDER_MESH_CHAIN_MATCH=PASS')
    print('BUILT_IN_FREE_PROVIDER_MATCH=PASS')
    print('ZAI_REMOVED=PASS')
    print('FREE_ONLY_FAIL_CLOSED=PASS')
    print('CANONICAL_WORKFLOW_MATCH=PASS')
    print('NO_LEGACY_WORKFLOW_DEPENDENCY=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
