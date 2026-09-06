from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("CAR_MODE", "1")

from scripts.story_pipeline import normalize_metadata


class MetadataHashtagContractTests(unittest.TestCase):
    def test_automotive_description_has_at_most_three_hashtags(self) -> None:
        story = normalize_metadata(
            {
                "title": "Ferrari 488 GTB Engineering",
                "description": "A concise automotive engineering explanation.",
                "tags": ["cars", "automotive"],
            },
            "Ferrari 488 GTB",
        )
        hashtags = re.findall(r"#[A-Za-z0-9_-]+", story["description"])
        self.assertLessEqual(len(hashtags), 3)
        self.assertEqual(len(hashtags), len({h.casefold() for h in hashtags}))


if __name__ == "__main__":
    unittest.main()
