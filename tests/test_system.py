import json, unittest
from pathlib import Path
from scripts.odysseus import chat_url

ROOT=Path(__file__).resolve().parents[1]

class SystemTests(unittest.TestCase):
    def test_required_contracts(self):
        o=json.loads((ROOT/'config/odysseus.json').read_text())
        p=json.loads((ROOT/'config/production.json').read_text())
        self.assertEqual(o['endpoint_path'],'/api/v1/chat')
        self.assertTrue(o['primary'])
        self.assertTrue(o['provider_keys_hidden'])
        self.assertEqual(p['output']['shorts']['count'],4)
        self.assertEqual(p['output']['long_video']['min_seconds'],420)
        self.assertEqual(p['output']['long_video']['max_seconds'],900)
    def test_imports(self):
        import scripts.story, scripts.renderer, scripts.production, scripts.qa, scripts.system_gate
    def test_url(self):
        import os
        os.environ['ODYSSEUS_BASE_URL']='http://localhost:7000'
        self.assertEqual(chat_url(),'http://localhost:7000/api/v1/chat')

if __name__ == '__main__': unittest.main()
