from pathlib import Path
import inspect
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('RUN_DIR',str(ROOT/'data/test-router'))

from ai_router import AIRouter, Provider, estimate_tokens, _classify
from generate_job import compat
import compatible_provider_pool as compatible_pool


class TestAIRouter(unittest.TestCase):
    def test_token_estimator_is_conservative(self):
        self.assertGreaterEqual(estimate_tokens('one two three'),300)

    def test_error_classification(self):
        self.assertEqual(_classify(RuntimeError('HTTP 402 payment_required')),'PAID_REQUIRED')
        self.assertEqual(_classify(RuntimeError('HTTP 429 rate limit')),'RATE_LIMIT')
        self.assertEqual(_classify(RuntimeError('403 AccessDenied.Unpurchased')),'ACCESS_OR_QUOTA')
        self.assertEqual(_classify(RuntimeError('scene 1 invalid beat')),'SCHEMA_INVALID')
        self.assertEqual(_classify(RuntimeError('HTTP 524 timeout')),'TRANSIENT')

    def test_router_skips_hard_disabled_provider(self):
        bad=Provider('Paid',['long_story'],1,True,lambda p: (_ for _ in ()).throw(RuntimeError('402 payment_required')))
        good=Provider('Good',['long_story'],2,True,lambda p:{'ok':True})
        r=AIRouter([bad,good])
        result,name,model=r.route('test prompt')
        self.assertEqual(result,{'ok':True})
        self.assertEqual(name,'Good')

    def test_schema_failure_does_not_cooldown_provider(self):
        p=Provider('Repairable',['long_story'],1,True,lambda p:{'scene':'invalid'})
        r=AIRouter([p])
        result,name,model=r.route('test prompt')
        self.assertEqual(name,'Repairable')
        r.report_validation_failure('Repairable',ValueError('scene count invalid'))
        self.assertEqual(r._entry('Repairable')['status'],'SCHEMA_INVALID')
        self.assertEqual(r._entry('Repairable')['cooldown_until'],0)

    def test_registry_is_aligned_and_zai_removed(self):
        cfg=json.loads((ROOT/'config/ai-router.json').read_text())
        plan=json.loads((ROOT/'config/provider-activation-plan.json').read_text())
        pool=(ROOT/'scripts/compatible_provider_pool.py').read_text()
        self.assertTrue(cfg['free_only'])
        self.assertTrue(cfg['fail_closed'])
        self.assertNotIn('ZAI',cfg['additional_providers'])
        self.assertNotIn('ZAI',pool)
        additional_names=set(cfg['additional_providers'])
        plan_names={x['name'] for x in plan['providers']}
        built_in=set(plan.get('built_in_free_only_providers',[]))
        local_names={'FreeLLMAPI','Ollama'}
        self.assertEqual(additional_names,(plan_names-local_names)|built_in)
        self.assertEqual(built_in,{'OpenRouter','CloudflareWorkersAI'})
        self.assertTrue(built_in <= additional_names)
        self.assertTrue(built_in.isdisjoint(local_names))
        self.assertTrue(local_names <= plan_names)
        self.assertTrue(local_names.isdisjoint(additional_names))
        task_providers=set(cfg['tasks']['long_story']['providers'])
        task_plain={p.split(':',1)[0] for p in task_providers}
        self.assertTrue(additional_names <= task_plain)
        self.assertTrue(local_names <= task_plain)
        self.assertIn('freellmapi',cfg)
        self.assertIn('ollama',cfg)
        self.assertTrue(cfg['freellmapi']['free_only'])
        self.assertTrue(cfg['freellmapi']['openai_compatible'])
        self.assertTrue(cfg['freellmapi']['live_inference_required'])
        self.assertTrue(cfg['ollama']['free_only'])
        self.assertTrue(cfg['ollama']['openai_compatible'])
        self.assertTrue(cfg['ollama']['live_inference_required'])

    def test_enabled_registry_providers_have_adapters_or_are_explicitly_disabled(self):
        cfg=json.loads((ROOT/'config/ai-router.json').read_text())
        pool_names=set(compatible_pool.PROVIDERS)
        for name,meta in cfg['additional_providers'].items():
            if name not in pool_names:
                self.assertTrue(meta.get('disabled_by_default') is True,f'{name} is configured without an adapter and is not disabled by default')

    def test_backup_adapter_priorities_do_not_preempt_primary_router(self):
        expected={'Mistral':56,'SambaNova':57,'HuggingFace':58,'OpenRouter':59,'CloudflareWorkersAI':60,'LLM7':61,'AnyAPI':62,'ArliAI':63,'OllamaCloud':64,'ModelScope':65,'Together':66}
        for name,priority in expected.items():
            self.assertEqual(compatible_pool.PROVIDERS[name]['priority'],priority)
        self.assertGreaterEqual(min(x['priority'] for x in compatible_pool.PROVIDERS.values()),56)

    def test_compat_adapter_accepts_router_output_budget(self):
        self.assertIn('max_tokens',inspect.signature(compat).parameters)

    def test_config_is_free_only(self):
        cfg=json.loads((ROOT/'config/ai-router.json').read_text())
        self.assertTrue(cfg['free_only'])
        self.assertTrue(cfg['fail_closed'])
