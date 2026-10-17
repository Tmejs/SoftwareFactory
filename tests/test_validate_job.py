import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_job import validate_job, validate_state


SHA = "a" * 40
REPO = "https://github.com/Tmejs/SoftwareFactory"


class JobValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = self.root / "factory/jobs/example-job"
        self.job.mkdir(parents=True)
        self.task_text = (
            "# Task\n\n## Objective\nMake example.\n\n## Scope\nOne file.\n\n"
            "## Context\nExperimental run.\n\n## Target repository\n" + REPO + "\n\n"
            "## Baseline commit\n" + SHA + "\n\n## Acceptance criteria\nWorks.\n\n"
            "## Checks\n- unit: python3 -m unittest discover -s tests -v\n"
            "- git-diff-check: git diff --check\n"
        )
        (self.job / "task.md").write_text(self.task_text)
        (self.job / "spec.md").write_text("# Specification\n\n## Acceptance criteria\nWorks.\n")
        (self.job / "build.md").write_text("# Build\n\n## Check evidence\n- unit: exit 0\n")
        (self.job / "reviews/round-1").mkdir(parents=True)
        (self.job / "reviews/round-1/code.md").write_text("VERDICT: PASS\n\nNo findings.\n")
        (self.job / "decision.md").write_text("DECISION: READY\n\nChecks and review passed.\n")
        self.state = {
            "schema_version": 1, "id": "example-job", "mode": "team", "stage": "ready",
            "baseline": SHA, "workflow_commit": SHA,
            "branch": "codex/checkpoint-2-example", "model_profile": {"builder": {"model": "gpt-6.1-sol", "reasoning": "high"}},
            "agent_runs": [], "assigned_reviews": ["code"], "review_round": 1,
            "repair_count": 0,
            "checks": [
                {"name": "unit", "command": "python3 -m unittest discover -s tests -v", "status": "pass", "output": "OK"},
                {"name": "git-diff-check", "command": "git diff --check", "status": "pass", "output": "clean"},
            ],
            "human_interventions": [],
            "artifacts": ["factory/jobs/example-job/task.md", "factory/jobs/example-job/reviews/round-1/code.md", "factory/jobs/example-job/decision.md"],
            "history": [
                {"from": None, "to": "intake", "at": "2026-10-17T10:00:00Z", "reason": "created"},
                {"from": "intake", "to": "spec", "at": "2026-10-17T10:01:00Z", "reason": "task accepted"},
                {"from": "spec", "to": "build", "at": "2026-10-17T10:02:00Z", "reason": "spec complete"},
                {"from": "build", "to": "review", "at": "2026-10-17T10:03:00Z", "reason": "build complete"},
                {"from": "review", "to": "ready", "at": "2026-10-17T10:04:00Z", "reason": "approved", "round": 1},
            ],
        }
        self.save()

    def save(self):
        (self.job / "state.json").write_text(json.dumps(self.state))

    def test_complete_ready_job_passes(self):
        self.assertEqual([], validate_job(self.job))

    def test_ready_rejects_missing_review(self):
        (self.job / "reviews/round-1/code.md").unlink()
        self.assertIn("missing review: code", validate_job(self.job))

    def test_review_rejects_missing_spec_handoff(self):
        (self.job / "spec.md").unlink()
        self.state["stage"] = "review"
        self.state["history"].pop()
        self.assertIn("missing spec.md", validate_state(self.job, self.state))

    def test_review_rejects_missing_build_handoff(self):
        (self.job / "build.md").unlink()
        self.state["stage"] = "review"
        self.state["history"].pop()
        self.assertIn("missing build.md", validate_state(self.job, self.state))

    def test_ready_rejects_changes_verdict(self):
        (self.job / "reviews/round-1/code.md").write_text("VERDICT: CHANGES\n")
        self.assertIn("review not passed: code", validate_job(self.job))

    def test_ready_rejects_empty_checks(self):
        self.state["checks"] = []
        self.assertTrue(validate_state(self.job, self.state))

    def test_ready_rejects_missing_declared_check(self):
        self.state["checks"].pop()
        self.assertIn("missing check: git-diff-check", validate_state(self.job, self.state))

    def test_ready_rejects_changed_check_command(self):
        self.state["checks"][0]["command"] = "true"
        self.assertIn("check command mismatch: unit", validate_state(self.job, self.state))

    def test_ready_rejects_failed_check(self):
        self.state["checks"][0]["status"] = "fail"
        self.assertIn("check not passed: unit", validate_state(self.job, self.state))

    def test_ready_rejects_unavailable_check(self):
        self.state["checks"][0]["status"] = "unavailable"
        self.assertIn("check not passed: unit", validate_state(self.job, self.state))

    def test_rejects_third_repair_cycle(self):
        self.state["repair_count"] = 3
        self.assertTrue(validate_state(self.job, self.state))

    def test_pending_review_is_valid_until_round_closes(self):
        (self.job / "reviews/round-1/code.md").unlink()
        self.state["stage"] = "review"
        self.state["history"].pop()
        self.assertEqual([], validate_state(self.job, self.state))

    def test_review_exit_waits_for_all_assigned_reports(self):
        self.state["assigned_reviews"] = ["code", "security"]
        self.state["stage"] = "repair"
        self.state["history"][-1]["to"] = "repair"
        self.assertIn("missing review: security", validate_state(self.job, self.state))

    def test_third_repair_transition_exceeds_limit(self):
        history = self.state["history"][:4]
        for round_number in (1, 2, 3):
            report = self.job / "reviews" / ("round-" + str(round_number)) / "code.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("VERDICT: CHANGES\n")
            history.append({"from": "review", "to": "repair", "at": "2026-10-17T10:04:00Z", "reason": "changes", "round": round_number})
            if round_number < 3:
                history.extend([
                    {"from": "repair", "to": "build", "at": "2026-10-17T10:05:00Z", "reason": "repair started"},
                    {"from": "build", "to": "review", "at": "2026-10-17T10:06:00Z", "reason": "repair checked"},
                ])
        self.state.update(stage="repair", history=history, review_round=3, repair_count=2)
        self.assertIn("repair limit exceeded", validate_state(self.job, self.state))

    def test_two_repair_cycles_can_end_needs_human(self):
        history = self.state["history"][:4]
        for round_number in (1, 2, 3):
            report = self.job / "reviews" / ("round-" + str(round_number)) / "code.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("VERDICT: CHANGES\n")
            history.append({"from": "review", "to": "needs-human" if round_number == 3 else "repair", "at": "2026-10-17T10:04:00Z", "reason": "changes", "round": round_number})
            if round_number < 3:
                history.extend([
                    {"from": "repair", "to": "build", "at": "2026-10-17T10:05:00Z", "reason": "repair started"},
                    {"from": "build", "to": "review", "at": "2026-10-17T10:06:00Z", "reason": "repair checked"},
                ])
        (self.job / "decision.md").write_text("DECISION: NEEDS-HUMAN\n\nUnresolved review.\n")
        self.state.update(stage="needs-human", history=history, review_round=3, repair_count=2)
        self.assertEqual([], validate_state(self.job, self.state))

    def test_rejects_sibling_artifact(self):
        self.state["artifacts"].append("factory/jobs/other/task.md")
        self.assertTrue(validate_state(self.job, self.state))

    def test_rejects_absolute_artifact(self):
        self.state["artifacts"].append("/tmp/escape")
        self.assertTrue(validate_state(self.job, self.state))

    def test_rejects_symlink_escape(self):
        outside = self.root / "outside.md"
        outside.write_text("outside")
        (self.job / "escape.md").symlink_to(outside)
        self.state["artifacts"].append("factory/jobs/example-job/escape.md")
        self.assertTrue(validate_state(self.job, self.state))

    def test_rejects_mismatched_job_id(self):
        self.state["id"] = "other-job"
        self.assertTrue(validate_state(self.job, self.state))

    def test_malformed_stage_returns_errors_instead_of_crashing(self):
        self.state["stage"] = []
        self.assertIn("invalid stage", validate_state(self.job, self.state))

    def test_malformed_review_role_returns_errors_instead_of_crashing(self):
        self.state["assigned_reviews"] = ["code", []]
        self.assertIn("invalid assigned_reviews", validate_state(self.job, self.state))

    def test_rejects_missing_context(self):
        (self.job / "task.md").write_text(self.task_text.replace("## Context\nExperimental run.\n\n", ""))
        self.assertTrue(validate_job(self.job))

    def test_rejects_missing_target_repository(self):
        (self.job / "task.md").write_text(self.task_text.replace("## Target repository\n" + REPO + "\n\n", ""))
        self.assertTrue(validate_job(self.job))

    def test_rejects_mismatched_baseline(self):
        (self.job / "task.md").write_text(self.task_text.replace("## Baseline commit\n" + SHA, "## Baseline commit\n" + "b" * 40))
        self.assertTrue(validate_job(self.job))

    def test_rejects_history_jump(self):
        self.state["history"] = [self.state["history"][0], self.state["history"][1], {"from": "spec", "to": "ready", "at": "2026-10-17T10:02:00Z", "reason": "jump"}]
        self.assertTrue(validate_state(self.job, self.state))

    def test_ready_rejects_review_round_not_reached_in_history(self):
        second = self.job / "reviews/round-2/code.md"
        second.parent.mkdir(parents=True)
        second.write_text("VERDICT: PASS\n")
        self.state["review_round"] = 2
        self.assertIn("review_round history mismatch", validate_state(self.job, self.state))


if __name__ == "__main__":
    unittest.main()
