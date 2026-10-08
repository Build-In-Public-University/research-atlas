import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import atlas


class DriftClassificationTests(unittest.TestCase):
    def test_first_observation_is_baseline(self):
        self.assertEqual(atlas.classify_drift(None, "new", "hash", None, None), "baseline")

    def test_same_commit_and_hash_is_unchanged(self):
        prior = {"id": "existing"}
        self.assertEqual(atlas.classify_drift(prior, "c1", "h1", "c1", "h1"), "unchanged")

    def test_advanced_repository_with_same_file_is_not_source_change(self):
        prior = {"id": "existing"}
        self.assertEqual(atlas.classify_drift(prior, "c2", "h1", "c1", "h1"), "repository_advanced_source_unchanged")

    def test_advanced_repository_with_changed_file_requires_review(self):
        prior = {"id": "existing"}
        self.assertEqual(atlas.classify_drift(prior, "c2", "h2", "c1", "h1"), "source_changed")

    def test_same_commit_with_changed_file_requires_review(self):
        prior = {"id": "existing"}
        self.assertEqual(atlas.classify_drift(prior, "c1", "h2", "c1", "h1"), "source_changed")


if __name__ == "__main__":
    unittest.main()
