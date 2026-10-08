import json
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from subprocess import run

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

    def test_review_event_persists_until_explicit_resolution(self):
        row = {"repository": "fixture/repo", "source_path": "REPORT.md", "baseline_commit": "c1", "current_commit": "c2", "status": "source_changed", "current_sha256": "h2", "baseline_sha256": "h1"}
        with tempfile.TemporaryDirectory() as directory:
            queue_path = Path(directory) / "review-queue.jsonl"
            first = atlas.update_review_queue([row], "2026-01-01T00:00:00Z", queue_path)
            event_id = first[0]["event_id"]
            second = atlas.update_review_queue([row], "2026-01-02T00:00:00Z", queue_path)
            self.assertEqual(second[0]["event_id"], event_id)
            self.assertEqual(second[0]["first_seen"], "2026-01-01T00:00:00Z")
            self.assertEqual(second[0]["last_seen"], "2026-01-02T00:00:00Z")
            restored = {**row, "status": "unchanged"}
            third = atlas.update_review_queue([restored], "2026-01-03T00:00:00Z", queue_path)
            self.assertFalse(third[0]["resolved"])
            self.assertEqual(third[0]["last_observed_status"], "not_currently_flagged")
            original_path = atlas.REVIEW_QUEUE
            atlas.REVIEW_QUEUE = queue_path
            try:
                atlas.resolve_review(event_id, "Reviewed source change; no claim update required.", "no_catalog_change", "fixture-reviewer")
            finally:
                atlas.REVIEW_QUEUE = original_path
            resolved = json.loads(queue_path.read_text().splitlines()[0])
            self.assertTrue(resolved["resolved"])
            self.assertEqual(resolved["resolution"], "Reviewed source change; no claim update required.")
            self.assertEqual(resolved["resolution_outcome"], "no_catalog_change")
            self.assertEqual(resolved["resolved_by"], "fixture-reviewer")

    def test_local_git_fixture_advances_then_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            source = repo / "REPORT.md"
            source.write_text("baseline\n")
            run(["git", "add", "REPORT.md"], cwd=repo, check=True)
            run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "baseline"], cwd=repo, check=True)
            baseline_commit = run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
            baseline_sha = sha256(source.read_bytes()).hexdigest()
            source.write_text("baseline\n")
            run(["git", "add", "REPORT.md"], cwd=repo, check=True)
            run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "metadata-only"], cwd=repo, check=True)
            advanced_commit = run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(atlas.classify_drift({"id": "fixture"}, advanced_commit, baseline_sha, baseline_commit, baseline_sha), "repository_advanced_source_unchanged")
            source.write_text("changed\n")
            changed_sha = sha256(source.read_bytes()).hexdigest()
            self.assertEqual(atlas.classify_drift({"id": "fixture"}, advanced_commit, changed_sha, baseline_commit, baseline_sha), "source_changed")


if __name__ == "__main__":
    unittest.main()
