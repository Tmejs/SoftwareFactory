import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.job_io import claim, release, write_state
from tools.validate_job import validate_job


class JobIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name) / "factory/jobs/example"
        self.job.mkdir(parents=True)
        sha = "a" * 40
        (self.job / "task.md").write_text(
            "# Task\n\n## Objective\nExample.\n\n## Scope\nOne file.\n\n"
            "## Context\nExperiment.\n\n## Target repository\nhttps://github.com/Tmejs/SoftwareFactory\n\n"
            "## Baseline commit\n" + sha + "\n\n## Acceptance criteria\nWorks.\n\n"
            "## Checks\n- git-diff-check: git diff --check\n"
        )
        self.state = {
            "schema_version": 1, "id": "example", "mode": "solo", "stage": "intake",
            "baseline": sha, "workflow_commit": sha, "branch": "codex/checkpoint-2-example",
            "model_profile": {"builder": {"model": "gpt-6.1-sol", "reasoning": "high"}},
            "agent_runs": [], "assigned_reviews": ["code"], "review_round": 0,
            "repair_count": 0, "checks": [], "human_interventions": [],
            "artifacts": ["factory/jobs/example/task.md"],
            "history": [{"from": None, "to": "intake", "at": "2026-10-17T10:00:00Z", "reason": "created"}],
        }
        (self.job / "state.json").write_text(json.dumps(self.state))

    def test_second_owner_cannot_claim_until_release(self):
        claim(self.job, "first")
        with self.assertRaises(FileExistsError):
            claim(self.job, "second")
        self.assertEqual("first", json.loads((self.job / "owner.lock/owner.json").read_text())["owner"])
        release(self.job, "first")
        claim(self.job, "second")
        self.assertEqual("second", json.loads((self.job / "owner.lock/owner.json").read_text())["owner"])

    def test_wrong_owner_cannot_release_or_write(self):
        claim(self.job, "first")
        with self.assertRaises(PermissionError):
            release(self.job, "second")
        with self.assertRaises(PermissionError):
            write_state(self.job, "second", self.state)
        self.assertTrue((self.job / "owner.lock").exists())

    def test_simultaneous_claim_has_one_winner(self):
        barrier = threading.Barrier(2)
        results = []

        def attempt(owner):
            barrier.wait()
            try:
                claim(self.job, owner)
                results.append("won")
            except FileExistsError:
                results.append("lost")

        threads = [threading.Thread(target=attempt, args=(name,)) for name in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(["won", "lost"], results)

    def test_valid_write_replaces_state(self):
        claim(self.job, "first")
        updated = dict(self.state)
        updated["mode"] = "team"
        write_state(self.job, "first", updated)
        self.assertEqual("team", json.loads((self.job / "state.json").read_text())["mode"])
        self.assertEqual([], validate_job(self.job))

    def test_interrupted_replace_preserves_old_state(self):
        claim(self.job, "first")
        updated = dict(self.state)
        updated["mode"] = "team"
        with patch("tools.job_io.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                write_state(self.job, "first", updated)
        self.assertEqual("solo", json.loads((self.job / "state.json").read_text())["mode"])
        self.assertEqual([], list(self.job.glob(".state-*")))

    def test_invalid_candidate_never_replaces_valid_state(self):
        claim(self.job, "first")
        invalid = dict(self.state)
        invalid["id"] = "wrong"
        with self.assertRaises(ValueError):
            write_state(self.job, "first", invalid)
        self.assertEqual("example", json.loads((self.job / "state.json").read_text())["id"])
        self.assertEqual([], validate_job(self.job))


if __name__ == "__main__":
    unittest.main()
