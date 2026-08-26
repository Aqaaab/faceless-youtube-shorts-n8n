#!/usr/bin/env python3
from __future__ import annotations

import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    'scripts/daily_content_orchestrator.py',
    'scripts/council_learning_bridge.py',
    'scripts/idea_generation_council.py',
    'scripts/idea_council_judge.py',
    'scripts/content_intelligence_upgrade.py',
    'scripts/production_reliability_gate.py',
    'scripts/patent_story_engine.py',
    'scripts/viral_engine.py',
    'scripts/short_factory.py',
    'scripts/visual_qa.py',
    'scripts/final_feature_qa.py',
    'scripts/ai_router.py',
    'scripts/compatible_provider_pool.py',
    'scripts/provider_registry_audit.py',
    'config/idea-council.json',
    'config/ai-router.json',
    'config/provider-activation-plan.json',
    '.github/workflows/daily-production.yml',
]

LEGACY_PATHS = [
    '.github/workflows/daily-production-v2.yml',
    '.github/workflows/daily-content-contract.yml',
    '.github/workflows/youtube-shorts.yml',
]


def fail(code: str, **values: object) -> None:
    details = ' '.join(f'{k}={v!r}' for k, v in values.items())
    raise SystemExit(f'RELIABILITY_{code}' + (f' {details}' if details else ''))


def main() -> None:
    for rel in REQUIRED:
        p = ROOT / rel
        if not p.is_file():
            fail('MISSING', path=rel)
        if p.suffix == '.py':
            py_compile.compile(str(p), doraise=True)

    for rel in LEGACY_PATHS:
        if (ROOT / rel).exists():
            fail('LEGACY_FILE_PRESENT', path=rel)

    council = json.loads((ROOT / 'config/idea-council.json').read_text(encoding='utf-8'))
    router = json.loads((ROOT / 'config/ai-router.json').read_text(encoding='utf-8'))
    plan = json.loads((ROOT / 'config/provider-activation-plan.json').read_text(encoding='utf-8'))

    if not (council.get('allow_source_copy') is False and council.get('top_k') == 5 and len(council.get('roles', [])) == 5):
        fail('COUNCIL_CONTRACT')

    if not (router.get('free_only') is True and router.get('fail_closed') is True):
        fail('ROUTER_POLICY')

    additional = router.get('additional_providers', {})
    if 'ZAI' in additional or 'GitHubModels' in additional:
        fail('FORBIDDEN_PROVIDER_PRESENT')

    registry = set(additional)
    plan_names = [x['name'] for x in plan.get('providers', [])]
    builtins = set(plan.get('built_in_free_only_providers', []))
    dedicated = {'FreeLLMAPI', 'Ollama'}
    expected_plan = (registry - builtins) | dedicated

    if set(plan_names) != expected_plan:
        fail('PROVIDER_SET_MISMATCH', registry_count=len(registry), plan_count=len(plan_names), missing=sorted(expected_plan - set(plan_names)), unexpected=sorted(set(plan_names) - expected_plan))

    if len(plan_names) != len(set(plan_names)):
        fail('DUPLICATE_PROVIDER', duplicates=sorted({x for x in plan_names if plan_names.count(x) > 1}))

    if len(registry) > router.get('provider_capacity', {}).get('max_entries', 100):
        fail('PROVIDER_CAPACITY', count=len(registry))

    if set(builtins) != {'OpenRouter', 'CloudflareWorkersAI'}:
        fail('BUILTIN_PROVIDER_CONTRACT', builtins=sorted(builtins))

    if router.get('openrouter', {}).get('free_only') is not True or not router.get('openrouter', {}).get('default_model', '').endswith(':free'):
        fail('OPENROUTER_CONTRACT')
    if router.get('cloudflare_workers_ai', {}).get('free_only') is not True:
        fail('CLOUDFLARE_CONTRACT')
    if router.get('freellmapi', {}).get('free_only') is not True or router.get('freellmapi', {}).get('live_inference_required') is not True:
        fail('FREELLMAPI_CONTRACT')
    if router.get('ollama', {}).get('free_only') is not True or router.get('ollama', {}).get('live_inference_required') is not True:
        fail('OLLAMA_CONTRACT')

    workflow = (ROOT / '.github/workflows/daily-production.yml').read_text(encoding='utf-8')
    for forbidden in ('daily-production-v2.yml', 'daily-production-v2-final-', '== 11', 'len(registry) == 11'):
        if forbidden in workflow:
            fail('STALE_WORKFLOW_REFERENCE', marker=forbidden)
    for marker in ('idea_judged.json', 'long_story.json', 'preflight:', 'OPENROUTER_API_KEY', 'CLOUDFLARE_API_TOKEN'):
        if marker not in workflow:
            fail('WORKFLOW_MARKER_MISSING', marker=marker)

    print(
        'PRODUCTION_RELIABILITY_GATE=PASS '
        f'files={len(REQUIRED)} python=compiled '
        f'registry={len(registry)} activation_plan={len(plan_names)} '
        'council=PASS router=PASS workflow=canonical legacy=absent'
    )


if __name__ == '__main__':
    main()
