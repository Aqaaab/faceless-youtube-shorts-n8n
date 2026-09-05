import sys
import unittest
from pathlib import Path

# [run-production] keep the regression test aligned with the production import path.
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class StoryPipelineImportTest(unittest.TestCase):
    def test_story_pipeline_imports_cleanly(self):
        import story_pipeline  # noqa: F401


if __name__ == "__main__":
    unittest.main()
