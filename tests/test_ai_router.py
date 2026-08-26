from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('RUN_DIR',str(ROOT/'data/test-router'))

from ai_router import AIRouter, Provider, estimate_tokens, _classify

def test_token_estimator_is_conservative():
    assert estimate_tokens('one two three') >= 300

def test_error_classification():
    assert _classify(RuntimeError('HTTP 402 payment_required')) == 'PAID_REQUIRED'
    assert _classify(RuntimeError('HTTP 429 rate limit')) == 'RATE_LIMIT'
    assert _classify(RuntimeError('403 AccessDenied.Unpurchased')) == 'ACCESS_OR_QUOTA'
    assert _classify(RuntimeError('scene 1 invalid beat')) == 'SCHEMA_INVALID'
    assert _classify(RuntimeError('HTTP 524 timeout')) == 'TRANSIENT'

def test_router_skips_hard_disabled_provider():
    bad=Provider('Paid', ['long_story'], 1, True, lambda p: (_ for _ in ()).throw(RuntimeError('402 payment_required')))
    good=Provider('Good', ['long_story'], 2, True, lambda p: {'ok':True})
    r=AIRouter([bad,good])
    result,name,model=r.route('test prompt')
    assert result == {'ok':True}
    assert name == 'Good'

def test_schema_failure_does_not_cooldown_provider():
    p=Provider('Repairable', ['long_story'], 1, True, lambda p: {'scene': 'invalid'})
    r=AIRouter([p])
    result,name,model=r.route('test prompt')
    assert name == 'Repairable'
    r.report_validation_failure('Repairable', ValueError('scene count invalid'))
    assert r._entry('Repairable')['status'] == 'SCHEMA_INVALID'
    assert r._entry('Repairable')['cooldown_until'] == 0

def test_registry_is_aligned_and_zai_removed():
    cfg=json.loads((ROOT/'config/ai-router.json').read_text())
    plan=json.loads((ROOT/'config/provider-activation-plan.json').read_text())
    pool=(ROOT/'scripts/compatible_provider_pool.py').read_text()
    assert cfg['free_only'] is True
    assert cfg['fail_closed'] is True
    assert 'ZAI' not in cfg['additional_providers']
    assert 'ZAI' not in pool

    # Canonical registry categories:
    # - ai-router.additional_providers contains remote backups AND built-in gateways.
    # - provider-activation-plan.providers contains remote backups plus local/self-hosted entries.
    # - OpenRouter/CloudflareWorkersAI are tagged as built-in in the activation plan.
    # - FreeLLMAPI/Ollama are tagged as local/self-hosted in the activation plan.
    additional_names=set(cfg['additional_providers'])
    plan_names={x['name'] for x in plan['providers']}
    built_in=set(plan.get('built_in_free_only_providers', []))
    local_names={'FreeLLMAPI','Ollama'}

    assert additional_names == (plan_names - local_names) | built_in
    assert built_in == {'OpenRouter','CloudflareWorkersAI'}
    assert built_in <= additional_names
    assert built_in.isdisjoint(local_names)
    assert local_names <= plan_names
    assert local_names.isdisjoint(additional_names)

    task_providers=set(cfg['tasks']['long_story']['providers'])
    task_plain={p.split(':',1)[0] for p in task_providers}
    assert additional_names <= task_plain
    assert local_names <= task_plain

    assert 'freellmapi' in cfg and 'ollama' in cfg
    assert cfg['freellmapi']['free_only'] is True
    assert cfg['freellmapi']['openai_compatible'] is True
    assert cfg['freellmapi']['live_inference_required'] is True
    assert cfg['ollama']['free_only'] is True
    assert cfg['ollama']['openai_compatible'] is True
    assert cfg['ollama']['live_inference_required'] is True

def test_config_is_free_only():
    cfg=json.loads((ROOT/'config/ai-router.json').read_text())
    assert cfg['free_only'] is True
    assert cfg['fail_closed'] is True
