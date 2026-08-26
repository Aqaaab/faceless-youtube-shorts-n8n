from pathlib import Path
import json
import os
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('RUN_DIR',str(ROOT/'data/test-story-slots'))


class TestLongStorySlots(unittest.TestCase):
    def test_slot_contract_is_fixed_and_contiguous(self):
        cfg=json.loads((ROOT/'config/long-story-slots.json').read_text(encoding='utf-8'))
        slots=cfg['slots']
        self.assertTrue(cfg['rules']['fixed_scene_ranges'])
        self.assertTrue(cfg['rules']['fallback_stays_in_same_slot'])
        self.assertTrue(cfg['rules']['never_skip_failed_slot'])
        self.assertEqual(len(slots),5)
        self.assertEqual([s['start_scene'] for s in slots],[1,6,11,16,21])
        self.assertEqual([s['end_scene'] for s in slots],[5,10,15,20,25])
        self.assertTrue(all(s['scene_count']==5 for s in slots))
        self.assertEqual(sum(s['scene_count'] for s in slots),25)

    def test_story_engine_and_orchestrator_reference_slot_contract(self):
        patent=(ROOT/'scripts/patent_story_engine.py').read_text(encoding='utf-8')
        orch=(ROOT/'scripts/daily_content_orchestrator.py').read_text(encoding='utf-8')
        self.assertIn('LONG_STORY_SLOTS_CONFIG', patent)
        self.assertIn('LONG_STORY_SLOT_ABORT', patent)
        self.assertIn('if provider:', patent)
        self.assertIn('config/long-story-slots.json', orch)
        self.assertIn('_validate_story_slots', orch)
        self.assertIn('LONG_STORY_FIXED_SLOTS=PASS', orch)

    def test_router_uses_slot_output_budget(self):
        router=(ROOT/'scripts/ai_router.py').read_text(encoding='utf-8')
        pool=(ROOT/'scripts/compatible_provider_pool.py').read_text(encoding='utf-8')
        cfg=json.loads((ROOT/'config/ai-router.json').read_text(encoding='utf-8'))
        self.assertIn('LONG_SLOT_MAX_OUTPUT_TOKENS', router)
        self.assertIn('LONG_SLOT_MAX_OUTPUT_TOKENS', pool)
        self.assertEqual(cfg['tasks']['long_story']['mode'],'fixed_slots')
        self.assertEqual(cfg['tasks']['long_story']['slot_count'],5)
        self.assertEqual(cfg['tasks']['long_story']['slot_scene_count'],5)
        self.assertEqual(cfg['tasks']['long_story']['max_output_tokens'],1200)

    def test_validation_failure_is_not_persistently_cooled_down(self):
        from ai_router import AIRouter, Provider
        p=Provider('Repairable',['long_story'],1,True,lambda prompt:{'ok':True})
        r=AIRouter([p])
        r.report_validation_failure('Repairable',ValueError('S1 scene count invalid'))
        self.assertEqual(r._entry('Repairable')['status'],'SCHEMA_INVALID')
        self.assertEqual(r._entry('Repairable')['cooldown_until'],0)
