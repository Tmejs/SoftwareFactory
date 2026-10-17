# SoftwareFactory job format, version 1

One job lives at `factory/jobs/<id>/` in its checkpoint worktree. `task.md` is frozen at intake; a changed requirement starts a new versioned job from the original baseline. The orchestrator owns `state.json` and `decision.md`; each reviewer owns only `reviews/round-N/<role>.md`. Runtime `owner.lock/` and `.state-*` files are not committed.

An orchestrator calls `python3 tools/job_io.py claim <job-dir> <owner-id>` before writing state. Creation of `owner.lock/` is atomic on the local filesystem; `owner.json` records that ID and a UTC claim time. A second claim fails. Only the matching owner can run `write-state <job-dir> <owner-id> <candidate-json-file>` or `release <job-dir> <owner-id>`. `write-state` validates the candidate, writes and syncs a temporary file in the job directory, then atomically replaces `state.json`. A failed replacement leaves the previous state intact. The helper never removes an abandoned claim based on age; a human must resolve it.

## Task packet

`task.md` has nonempty level-two sections named `Objective`, `Scope`, `Context`, `Target repository`, `Baseline commit`, `Acceptance criteria`, and `Checks`. The target repository in v1 is `https://github.com/Tmejs/SoftwareFactory`. The baseline is the exact 40-character lowercase Git SHA in `state.json`. Each check is a `- name: exact shell command` line. A `- git-diff-check: git diff --check` line is mandatory. Every declared check must eventually have matching state evidence before `READY`; failed, unavailable, or inapplicable checks require a stopped run and a revised packet.

## State

`state.json` is UTF-8 JSON with these required keys:

| Key | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `id` | Job directory name, 1–64 lowercase letters, digits, or hyphens, starting with a letter or digit |
| `mode` | `solo` or `team` |
| `stage` | `intake`, `spec`, `build`, `review`, `repair`, `ready`, `needs-human`, or `failed` |
| `baseline` | 40-character starting commit SHA |
| `workflow_commit` | 40-character commit SHA pinning the workflow instructions used by this run |
| `branch` | `codex/checkpoint-<number>-<short-name>` |
| `model_profile` | Per-role objects with nonempty requested `model` and `reasoning` strings |
| `agent_runs` | Objects with `role`, actual `model` and `reasoning` (or `null` if unavailable), UTC `started_at`, UTC `ended_at` (or `null` while running), and `usage` object or `null` |
| `assigned_reviews` | Unique roles; always `code`, optionally `security` and `ui` |
| `review_round` | Integer 0–3; 0 before first review |
| `repair_count` | Integer 0–2 |
| `checks` | Objects with `name`, exact `command`, `status` (`pass`, `fail`, `unavailable`, `inapplicable`), integer `exit_code` (0 for pass, nonzero for fail, `null` otherwise), and string `output` (empty for a silent success) |
| `human_interventions` | Objects with UTC `at`, nonempty `question`, and nonempty `decision` or `null` while unanswered |
| `artifacts` | Existing file paths relative to the repository; resolved paths, including symlinks, must remain inside this job directory |
| `history` | Ordered `{from, to, at, reason}` transitions; `at` is UTC and `reason` nonempty; review exits also have `round` |

The first history entry is `null → intake`. Later transitions are `intake → spec`, `spec → build|needs-human`, `build → review|needs-human|failed`, `review → repair|ready|needs-human|failed`, and `repair → build|needs-human|failed`. A terminal stage has no outgoing transition. Reaching `build` requires a nonempty `spec.md`; reaching `review` requires a nonempty `build.md`. Each `build → review` transition increments `review_round`; each `review → repair` transition increments `repair_count`; a third repair transition is invalid. A review exit's `round` must match that history count. Before leaving `review`, every assigned report for that round must exist and start with `VERDICT: PASS` or `VERDICT: CHANGES`. A pending review may lack reports. `ready` requires every final-round verdict to be `PASS`, every task-declared check to have matching command and `pass` status with exit code 0, and `decision.md` to start with `DECISION: READY`. Terminal decisions start with `DECISION: NEEDS-HUMAN` or `DECISION: FAILED` as applicable. Every required file is checked for job containment before it is read, even if omitted from `artifacts`.

## Complete READY example

This example belongs at `factory/jobs/example-job/`. Its `task.md` declares exactly the two checks shown below; nonempty `spec.md` and `build.md` exist, and `reviews/round-1/code.md` starts with `VERDICT: PASS`.

```json
{
  "schema_version": 1,
  "id": "example-job",
  "mode": "team",
  "stage": "ready",
  "baseline": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "workflow_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "branch": "codex/checkpoint-2-example",
  "model_profile": {"builder": {"model": "gpt-6.1-sol", "reasoning": "high"}},
  "agent_runs": [{"role": "builder", "model": "gpt-6.1-sol", "reasoning": "high", "started_at": "2026-10-17T10:00:00Z", "ended_at": "2026-10-17T10:03:00Z", "usage": null}],
  "assigned_reviews": ["code"],
  "review_round": 1,
  "repair_count": 0,
  "checks": [
    {"name": "unit", "command": "python3 -m unittest discover -s tests -v", "status": "pass", "exit_code": 0, "output": "19 tests passed"},
    {"name": "git-diff-check", "command": "git diff --check", "status": "pass", "exit_code": 0, "output": ""}
  ],
  "human_interventions": [],
  "artifacts": ["factory/jobs/example-job/task.md", "factory/jobs/example-job/reviews/round-1/code.md", "factory/jobs/example-job/decision.md"],
  "history": [
    {"from": null, "to": "intake", "at": "2026-10-17T10:00:00Z", "reason": "created"},
    {"from": "intake", "to": "spec", "at": "2026-10-17T10:01:00Z", "reason": "task accepted"},
    {"from": "spec", "to": "build", "at": "2026-10-17T10:02:00Z", "reason": "spec complete"},
    {"from": "build", "to": "review", "at": "2026-10-17T10:03:00Z", "reason": "build complete"},
    {"from": "review", "to": "ready", "at": "2026-10-17T10:04:00Z", "reason": "approved", "round": 1}
  ]
}
```

`READY` is pending delivery, not merged. The branch push is verified through local, tracking, and remote refs. After human approval and a verified `--no-ff` merge to synchronized `main`, an annotated `factory/<job-id>` tag points to the merge commit. Push and verify that tag's peeled remote SHA. The immutable tag, together with the tracked `READY` record and synchronized Git refs, proves completed delivery without changing the merge commit afterward.
