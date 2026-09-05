import unittest


class StoryPipelineImportTest(unittest.TestCase):
    def test_story_pipeline_imports_cleanly(self):
        import story_pipeline  # noqa: F401


if __name__ == "__main__":
    unittest.main()
