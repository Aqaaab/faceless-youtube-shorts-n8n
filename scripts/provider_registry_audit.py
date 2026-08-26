#!/usr/bin/env python3
"""Static consistency audit for the canonical Aqaaab production provider registry."""
from __future__ import annotations
import ast, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config'/'ai-router.json'; PLAN=ROOT/'config'/'provider-activation-plan.json'; MESH=ROOT/'config'/'provider-mesh.json'
POOL=ROOT/'scripts'/'compatible_provider_pool.py'; DAILY_WORKFLOW=ROOT/'.github'/'workflows'/'daily-production.yml'; VALIDATION_WORKFLOW=ROOT/'.github'/'workflows'/'ai-router-validation.yml'; ROUTER=ROOT/'scripts'/'ai_router.py'; WORKFLOW_DIR=ROOT/'.github'/'workflows'

def operational_legacy_refs(text:str)->list[str]:
    refs=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or line.startswith('assert ') or line.startswith('assert('): continue
        if 'daily-production-v2.yml' in line and any(k in line for k in ('uses:','workflow:','workflows:','workflow_run:')): refs.append(line)
        if 'daily-production-v2-final-' in line and any(k in line for k in ('pattern:','name:','download-artifact','cp ','mv ','test -s','find ')): refs.append(line)
    return refs

def pool_names(text:str)->set[str]:
    tree=ast.parse(text); names=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Dict):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id=='PROVIDERS':
                    for k in node.value.keys:
                        if isinstance(k,ast.Constant) and isinstance(k.value,str): names.add(k.value)
    return names

def main()->int:
    cfg=json.loads(CFG.read_text()); plan=json.loads(PLAN.read_text()); mesh=json.loads(MESH.read_text())
    registry=cfg.get('additional_providers',{}); entries=plan.get('providers',[]); names=[p['name'] for p in entries]; by={p['name']:p for p in entries}
    builtins={'OpenRouter','CloudflareWorkersAI'}; dedicated={'FreeLLMAPI','Ollama'}
    pool_text=POOL.read_text(); pool_set=pool_names(pool_text); daily=DAILY_WORKFLOW.read_text(); validation=VALIDATION_WORKFLOW.read_text(); router=ROUTER.read_text()
    assert DAILY_WORKFLOW.is_file() and VALIDATION_WORKFLOW.is_file() and POOL.is_file()
    assert not (WORKFLOW_DIR/'daily-production-v2.yml').exists()
    for path in WORKFLOW_DIR.glob('*.yml'): assert not operational_legacy_refs(path.read_text()), f'legacy operational dependency remains: {path}'
    assert cfg.get('integration',{}).get('daily_pipeline')=='.github/workflows/daily-production.yml'
    assert cfg['free_only'] is True and cfg['fail_closed'] is True
    assert 'GitHubModels' not in registry and 'ZAI' not in registry and 'ZAI' not in pool_text
    assert 'GitHubModels' not in names and 'ZAI' not in names
    assert len(registry)<=int(plan.get('policy',{}).get('max_provider_entries',100))
    assert set(names)==(set(registry)-builtins)|dedicated
    assert set(plan.get('built_in_free_only_providers',[]))==builtins
    assert registry['OpenRouter']['default_model'].endswith(':free') and registry['CloudflareWorkersAI']['free_only'] is True
    enabled=set()
    for name,meta in registry.items():
        disabled=bool(meta.get('disabled_by_default',False) or by.get(name,{}).get('disabled_by_default',False))
        if name in pool_set: enabled.add(name)
        elif not disabled: assert name in router, f'enabled provider has no adapter/router: {name}'
        if meta.get('api_key_env'): assert meta['api_key_env'] in pool_text or disabled, f'adapter secret missing: {name}'
        if not disabled and name not in builtins:
            assert (meta.get('api_key_env') in validation+daily) if meta.get('api_key_env') else True
    assert pool_set <= set(registry) | {'OpenRouter','CloudflareWorkersAI'}
    assert builtins|dedicated <= set(router) | set(registry)
    task_providers={x.split(':',1)[0] for x in cfg['tasks']['long_story']['providers']}
    for name,meta in registry.items():
        disabled=bool(meta.get('disabled_by_default',False) or by.get(name,{}).get('disabled_by_default',False))
        if not disabled: assert name in task_providers or name in builtins or name in dedicated, f'enabled provider missing from long_story task: {name}'
    for p in entries:
        name=p['name']; disabled=bool(p.get('disabled_by_default',False) or registry.get(name,{}).get('disabled_by_default',False))
        assert name in pool_set or name in router or disabled or name in dedicated, f'provider adapter/router missing: {name}'
    for task,meta in mesh['tasks'].items():
        for key in ('primary','backup_1','backup_2'): assert meta.get(key), f'mesh task missing {task}.{key}'
    assert 'scripts/patent_story_engine.py' in daily and 'ALLOW_DETERMINISTIC_FALLBACK: "false"' in daily
    print(f'PROVIDER_REGISTRY_COUNT={len(registry)}'); print(f'PROVIDER_PLAN_COUNT={len(names)}'); print(f'PROVIDER_POOL_COUNT={len(pool_set)}')
    print('PROVIDER_REGISTRY_MATCH=PASS'); print('PROVIDER_ADAPTER_MATCH=PASS'); print('PROVIDER_MESH_CHAIN_MATCH=PASS'); print('BUILT_IN_FREE_PROVIDER_MATCH=PASS'); print('ZAI_REMOVED=PASS'); print('FREE_ONLY_FAIL_CLOSED=PASS'); print('CANONICAL_WORKFLOW_MATCH=PASS'); print('NO_LEGACY_WORKFLOW_DEPENDENCY=PASS'); return 0
if __name__=='__main__': raise SystemExit(main())
