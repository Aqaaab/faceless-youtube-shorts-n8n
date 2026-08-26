import json, tempfile, unittest
from pathlib import Path

class ContractTests(unittest.TestCase):
    def test_production_contract(self):
        root=Path(__file__).resolve().parents[1]
        c=json.loads((root/'config/production.json').read_text())
        self.assertEqual(c['primary']['name'],'Odysseus')
        self.assertEqual(c['production']['short_count'],4)
        self.assertEqual(c['production']['long_duration_seconds']['min'],420)
        self.assertEqual(c['production']['long_duration_seconds']['max'],900)

    def test_story_validation(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from story_pipeline import words
        self.assertEqual(words('one two three'),3)

    def test_short_count(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from shorts_pipeline import build_shorts
        story={'title':'T','scenes':[{'id':i} for i in range(25)]}
        self.assertEqual(len(build_shorts(story)),4)

if __name__=='__main__': unittest.main()
