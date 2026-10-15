# Software Factory v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repo-local Codex workflow that can resume a software job from files, coordinate isolated build and independent review, and validate the resulting evidence.

**Architecture:** A skill drives decisions and agent handoffs; per-job Markdown and JSON files hold durable state. A small Python standard-library validator checks job records, while shell filesystem operations provide atomic per-job ownership and state-file replacement. No service or dashboard is part of v1.

**Tech Stack:** Codex repo-local skill, Markdown, JSON, Python 3 standard library, Git worktrees, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-14-software-factory-design.md`

## Global Constraints

- First version targets this repository and runs only when a user invokes the skill.
- `main` is stable; use a fresh `codex/checkpoint-<number>-<short-name>` branch from clean, fetched, synchronized `main` for each development checkpoint.
- A running job keeps its artifacts in its checkpoint worktree; the main checkout stays clean.
- One orchestrator claims `owner.lock` atomically and alone updates `state.json` atomically. An abandoned claim needs explicit human resolution.
- The task packet is frozen when a run starts. A changed criterion starts a new versioned run from the common baseline.
- Code review is mandatory. Security and UI reviews are conditional. Wait for all assigned reviewers, and allow at most two repair cycles.
- Required checks must pass before `READY`; failed or unavailable checks cannot be waived within an active run.
- The first comparison uses GPT-6.1 Sol in solo and team modes, with the same task packet, baseline, checks, and review gate. Record actual model and reasoning settings.
- No automatic merge. Follow the user's local verification, independent review, SHA confirmation, push, and `--no-ff` merge workflow.
- The tracked job state ends at `READY`; branch push state comes from Git refs, and a unique annotated `factory/<job-id>` tag created after merge is the durable final delivery record. Never replace an existing tag.
- No third-party Python packages, hosted control plane, issue integration, or visual board in v1.
- Python 3.9 or newer, using only the standard library; the workspace currently has Python 3.9.6.

## Review Focus

These likely failure conditions must have a test or dry-run check in the owning task:

1. A `READY` state or closed review round with one missing or `CHANGES` reviewer report must fail validation (Task 1).
2. A repository-relative artifact path that escapes its job directory, including through `..`, must fail validation (Task 1).
3. Two orchestrators racing for one job must not both acquire `owner.lock` (Task 2).
4. A state update interrupted before replacement must leave the previous valid `state.json` readable (Task 2).
5. A required check marked failed or unavailable must prevent `READY`, including after repair round two (Tasks 1 and 3).

## File map

| File | Responsibility |
| --- | --- |
| `AGENTS.md` | Short repository rules, verification command, and pointer to the skill |
| `.agents/skills/software-factory/SKILL.md` | Invocation, orchestration, stage flow, stop rules, and exact file handoffs |
| `.agents/skills/software-factory/references/roles.md` | Spec writer, builder, and reviewer input/output/write contracts |
| `.agents/skills/software-factory/references/model-policy.md` | Initial OpenAI model settings and comparison controls |
| `.agents/skills/software-factory/assets/{task,spec,build,review,decision}.md` | Job artifact templates |
| `factory/job-format.md` | Version 1 state shape, stages, valid transitions, verdicts, and check evidence format |
| `tools/validate_job.py` | Read-only job record validator and CLI |
| `tests/test_validate_job.py` | Behavior tests for schema, stage gates, artifacts, and path safety |
| `.gitignore` | Exclude live `owner.lock` directories and temporary state files |
| `README.md` | Verified invocation and local validation instructions |
| `codex/checkpoints/2-factory-v1.md` | Verification and independent review evidence for the implementation checkpoint |

Do not create `factory/jobs/` contents as part of the implementation commit. Disposable dry-run jobs live in a temporary directory until the workflow is verified. Real jobs are added by later factory runs on their own branches.

## Task 1: Job format and read-only validator

**Files:**
- Create: `factory/job-format.md`
- Create: `tools/validate_job.py`
- Create: `tests/test_validate_job.py`

**Interfaces:**
- Consumes: A path to a job directory containing `task.md`, `state.json`, and stage artifacts.
- Produces: `validate_state(job_dir: Path, state: dict) -> list[str]` for a proposed state; `validate_job(job_dir: Path) -> list[str]` loads `state.json` and delegates to it. An empty list means valid. CLI `python3 tools/validate_job.py <job-dir>` exits 0 for valid, 1 for invalid, 2 for invalid invocation or unreadable JSON.

State v1 fields: `schema_version` (integer 1), `id` (`[a-z0-9][a-z0-9-]{0,63}`), `mode` (`solo` or `team`), `stage` (`intake`, `spec`, `build`, `review`, `repair`, `ready`, `needs-human`, `failed`), `baseline` and `workflow_commit` (40-character Git SHAs), `branch` (checkpoint branch name), `model_profile` (requested model and reasoning per role), `agent_runs` (actual role, model, reasoning, start/end times, and usage or `null`), `assigned_reviews` (array containing `code` and optionally `security`, `ui`), `review_round` (0 through 3), `repair_count` (0 through 2), `checks` (array of `{name, command, status, output}`), `human_interventions` (timestamped question/decision records), `artifacts` (repository-relative paths constrained to this job), and `history` (ordered stage transitions with UTC timestamps, reasons, and the review round on review exits). `task.md` requires nonempty `Objective`, `Scope`, `Context`, `Target repository`, `Baseline commit`, `Acceptance criteria`, and `Checks` sections. `Baseline commit` must equal `state.baseline`; `Target repository` must be `https://github.com/Tmejs/SoftwareFactory` in v1. The `Checks` section uses `- name: command` entries, including `- git-diff-check: git diff --check`. Review files start with `VERDICT: PASS` or `VERDICT: CHANGES`; `decision.md` starts with `DECISION: READY`, `DECISION: NEEDS-HUMAN`, or `DECISION: FAILED`.

The first history entry is `null→intake`. Allowed later transitions: `intake→spec`, `spec→build|needs-human`, `build→review|needs-human|failed`, `review→repair|ready|needs-human|failed`, `repair→build|needs-human|failed`; terminal stages have no outgoing *stage* transition. A run needing changed criteria terminates and a new job starts. Closing any review round requires a report from every assigned reviewer. `ready` requires all assigned reviewers to report `PASS` in the last review round. Every `Checks` entry in the frozen task packet must have a matching state record with the same name and command and status `pass`; an empty or incomplete `checks` array cannot yield `ready`.

`READY` means the job can enter the Git delivery workflow, not that it has merged. Git refs prove whether the branch was pushed. After human approval and a verified `--no-ff` merge, create an annotated tag `factory/<job-id>` pointing to the merge commit; its message records the job ID, selected branch tip, and verification summary. Push the new tag and verify the remote peeled tag SHA equals the merge commit. The tag is the durable final delivery record and does not change `main` or the completed branch. A job is fully complete only when its `READY` record, synchronized branch and main refs, and matching remote completion tag are all present. A later board derives delivery status from those Git refs and tags alongside job files.

- [ ] **Step 1: Write tests for valid and invalid decision gates.** In `tests/test_validate_job.py`, use `tempfile.TemporaryDirectory` to build a repo-like `factory/jobs/<id>` tree and a valid ready job fixture. Add separate tests that change one fact at a time: absent `code.md`, `VERDICT: CHANGES`, empty `checks`, a missing task-declared check, a check with a changed command, `checks[0].status = "fail"`, `checks[0].status = "unavailable"`, and `repair_count = 3`. Each must produce a nonempty error list. Include a valid in-progress `review` job whose assigned report has not arrived yet, and an invalid `review→repair` history entry when another assigned report is absent.

```python
def test_ready_rejects_missing_review(self):
    job = self.make_ready_job()
    (job / "reviews/round-1/code.md").unlink()
    self.assertIn("missing review: code", validate_job(job))
```

- [ ] **Step 2: Run the focused tests and see them fail.** Run `python3 -m unittest tests.test_validate_job -v`. Expected: import failure for `tools.validate_job` or the new gate tests fail.
- [ ] **Step 3: Implement the minimal validator.** Define `validate_state(job_dir: Path, state: dict) -> list[str]`, `validate_job(job_dir: Path) -> list[str]`, and `main(argv: list[str]) -> int`. Require the repo-like `factory/jobs/<id>` location, parse JSON and the required task headings, and check `Baseline commit` against state. Parse the task's `Checks` bullets into name/command pairs and compare them with the state evidence; require `git-diff-check`. For each artifact path, resolve from the repository root and reject a target outside `job_dir.resolve()`, including symlinks. For `ready`, require last-round reports for every assigned reviewer, exact `PASS` verdicts, a `READY` decision file, and matching task-declared checks all marked `pass`. Check each history pair against the allowed transitions above, and require all assigned reports before any `review` stage exit. Print one error per line in the CLI.

```python
from pathlib import Path
from typing import Optional

def safe_artifact(job_dir: Path, relative: str) -> Optional[Path]:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None
    repo_root = job_dir.resolve().parents[2]
    candidate = (repo_root / relative).resolve()
    return candidate if candidate.is_relative_to(job_dir.resolve()) else None
```

- [ ] **Step 4: Add path, packet, and history tests.** Test an artifact path into a sibling job, an absolute path, a symlink to an outside file, a mismatched job ID, a missing `Context` or `Target repository`, a task baseline different from state, and a `ready` history that jumps directly from `spec`. Test that a `review` stage with pending assigned reports is valid until the orchestrator attempts to close the round. Test that a `review→repair` transition with a missing assigned report fails.
- [ ] **Step 5: Make tests pass and document the format.** Run `python3 -m unittest tests.test_validate_job -v`, then `python3 tools/validate_job.py --help`; both must exit 0. Write `factory/job-format.md` with the exact fields, transitions, verdicts, and one complete example JSON state matching the implementation.
- [ ] **Step 6: Commit.** Run `git diff --check`; commit the three files as `feat: define factory job records and validator`.

## Task 2: Atomic job ownership and state replacement

**Files:**
- Create: `.gitignore`
- Create: `tests/test_job_io.py`
- Create: `tools/job_io.py`
- Modify: `factory/job-format.md`

**Interfaces:**
- Consumes: A job directory and an orchestrator-generated owner ID.
- Produces: `claim(job_dir: Path, owner: str) -> None`, `release(job_dir: Path, owner: str) -> None`, and `write_state(job_dir: Path, owner: str, state: dict) -> None`. `claim` raises `FileExistsError` on a competing owner. `release` and `write_state` raise `PermissionError` unless `owner.lock/owner.json` matches the owner ID. No automatic stale lock removal. CLI commands are `python3 tools/job_io.py claim <job-dir> <owner>`, `release <job-dir> <owner>`, and `write-state <job-dir> <owner> <candidate-json-file>`; exit 0 on success, 1 on conflict or invalid state, and 2 on invalid invocation.

- [ ] **Step 1: Write ownership tests.** Use a temporary job directory. Assert the first `claim` succeeds and a second `claim` raises `FileExistsError`; an incorrect owner cannot release or write; the correct owner can release, then another can claim. Add a simultaneous two-thread claim test using `threading.Barrier` and assert exactly one succeeds.

```python
with self.assertRaises(FileExistsError):
    claim(job, "second-orchestrator")
```

- [ ] **Step 2: Run focused tests and see them fail.** Run `python3 -m unittest tests.test_job_io -v`. Expected: import failure or failing ownership tests.
- [ ] **Step 3: Implement claim and release.** Use `Path.mkdir()` without `exist_ok` for `owner.lock`, then write `owner.json` with owner ID and an ISO UTC claim time. If writing `owner.json` fails, remove only the newly created lock directory. `release` checks the recorded ID before deleting the lock. Never infer staleness from elapsed time.

```python
lock = job_dir / "owner.lock"
lock.mkdir()  # atomic create-if-absent on the local filesystem
(lock / "owner.json").write_text(json.dumps({"owner": owner, "claimed_at": now}))
```

- [ ] **Step 4: Write atomic-write tests.** Seed a valid `state.json`, call `write_state` with a new valid state, and assert it replaces the old state. Simulate a failure before `os.replace` (mock only that filesystem call) and assert the old state remains readable and the temporary file is cleaned up. Test invalid JSON-shaped state is rejected through `validate_job` after writing a candidate in a temporary job.
- [ ] **Step 5: Implement atomic replacement and CLI.** Verify lock ownership, call `validate_state(job_dir, state)` before any replacement, serialize to a uniquely named temporary file inside the job directory, flush and `os.fsync`, then `os.replace(temp, state.json)`; remove the temp file in `finally`. Use `argparse` subcommands for `claim`, `release`, and `write-state`; the last loads the candidate JSON file and passes it to `write_state`. Keep the helper mechanical: the skill, not this module, decides the next stage.

```python
with tempfile.NamedTemporaryFile("w", dir=job_dir, prefix=".state-", delete=False) as tmp:
    json.dump(state, tmp, indent=2)
    tmp.flush()
    os.fsync(tmp.fileno())
    temp_path = Path(tmp.name)
os.replace(temp_path, job_dir / "state.json")
```

- [ ] **Step 6: Ignore runtime files, run tests, and commit.** Add `factory/jobs/*/owner.lock/` and `factory/jobs/*/.state-*` to `.gitignore`; check that `git status --short` excludes those files but still sees `task.md` and `state.json`. Run `python3 -m unittest discover -s tests -v`, `python3 tools/job_io.py --help`, and `git diff --check`; commit as `feat: make factory job state single-writer`.

## Task 3: Repo-local skill and role contracts

**Files:**
- Create: `AGENTS.md`
- Create: `.agents/skills/software-factory/SKILL.md`
- Create: `.agents/skills/software-factory/references/roles.md`
- Create: `.agents/skills/software-factory/references/model-policy.md`
- Create: `.agents/skills/software-factory/assets/task.md`
- Create: `.agents/skills/software-factory/assets/spec.md`
- Create: `.agents/skills/software-factory/assets/build.md`
- Create: `.agents/skills/software-factory/assets/review.md`
- Create: `.agents/skills/software-factory/assets/decision.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: The format and `tools` functions defined in Tasks 1 and 2; a user request invoking `$software-factory` with a new task or existing job ID.
- Produces: A discoverable Codex skill with `name: software-factory` and a stepwise procedure for `new` and `resume`; artifact templates that match the validator; role instructions that constrain inputs and writes.

- [ ] **Step 1: Write the skill entry and repository policy.** `SKILL.md` front matter must identify when to invoke it. `AGENTS.md` must tell an agent to read the spec and skill, keep `main` stable, use checkpoint branches, run `python3 -m unittest discover -s tests -v` and `git diff --check`, request independent review, and follow the verified push/merge SHA checks. Do not copy long role prompts into `AGENTS.md`.

```yaml
---
name: software-factory
description: Run or resume a SoftwareFactory job from its task packet and durable job files, coordinating build, checks, independent review, and decision.
---
```

- [ ] **Step 2: Write the stage procedure.** In `SKILL.md`, give exact commands for checking clean/synchronized main, creating `codex/checkpoint-<number>-<short-name>` and a worktree at intake, creating a unique job ID, claiming with `python3 tools/job_io.py claim <job-dir> <owner>`, writing state with `python3 tools/job_io.py write-state <job-dir> <owner> <candidate-json-file>`, validating after transitions with `python3 tools/validate_job.py <job-dir>`, and releasing ownership with `python3 tools/job_io.py release <job-dir> <owner>` at terminal states. Describe `new` and `resume` entry paths; a new run cannot change its frozen task packet. On missing subagent support in team mode, record `NEEDS-HUMAN` or explicitly restart as a separately labeled solo run. After `READY`, wait for the human merge decision. Verify branch and `main` SHAs through Git refs; create, push, and verify the unique annotated `factory/<job-id>` tag only after the merge. If a tag already exists, stop and inspect it instead of replacing it.

- [ ] **Step 3: Write role contracts and templates.** `roles.md` must say what each role reads, writes, and reports. Builder alone changes product code and writes `build.md`; reviewers write only their assigned `reviews/round-N/<role>.md`. The orchestrator alone updates `state.json` and `decision.md`. Templates must include required headings and machine-readable first lines for verdict and decision.
- [ ] **Step 4: Write model and experiment policy.** `model-policy.md` pins GPT-6.1 Sol for all roles in v1. Set orchestration and focused review to medium reasoning; spec, build, and code review to high. State that actual model/effort is recorded, and that comparing workflows holds model settings constant. Model routing to Astra or Luna is a later experiment, not part of v1 behavior.
- [ ] **Step 5: Dry-run the instructions without product code.** In a temporary worktree, create a task packet from the template for a harmless documentation change. Have a fresh subagent read only the repository skill and job files, report the current stage and next action, and validate the job. Check that the task packet, state, role outputs, and `README.md` instructions agree. Record any missing instruction and repair it before the checkpoint review.
- [ ] **Step 6: Run checks and commit.** Run `python3 -m unittest discover -s tests -v`, `python3 tools/validate_job.py --help`, and `git diff --check`; commit as `feat: add agent-operated factory skill`.

## Task 4: Factory dry run and checkpoint evidence

**Files:**
- Create: `codex/checkpoints/2-factory-v1.md`
- Modify: the specific Task 1–3 file responsible for any diagnosed dry-run defect, with a focused regression test or repeatable dry-run case

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: A verification record with command outputs, dry-run observations, independent review findings and fixes, and local/remote SHAs.

- [ ] **Step 1: Exercise the required cases.** Use disposable temporary jobs to show a fresh session can resume from files; a `CHANGES` review routes to repair only after all assigned reports arrive; two repair cycles end with `NEEDS-HUMAN` or `FAILED`; two jobs have separate state; competing owners cannot both claim one job; an omitted or unavailable required check cannot yield `READY`; and a `READY` job without a completion tag is not reported as merged. Do not commit the disposable jobs.
- [ ] **Step 2: Capture evidence.** Record each check command, exit code, concise output, and the corresponding spec criterion in `codex/checkpoints/2-factory-v1.md`. Mark any unavailable check explicitly. Include the actual model and reasoning effort of any agent dry run if exposed by Codex; otherwise record `unavailable`.
- [ ] **Step 3: Run the full local gate.** Run `python3 -m unittest discover -s tests -v`, `python3 tools/validate_job.py --help`, `git diff --check`, and `git status --short`. Fix any failure and rerun affected checks plus the complete gate.
- [ ] **Step 4: Request independent review.** Ask a fresh reviewer to compare the branch with `origin/main`, the approved spec, and this plan. Record Critical, Important, and Minor findings. Fix all Critical or Important issues in a separate focused commit and request re-review of the fixes.
- [ ] **Step 5: Finish the checkpoint.** Update the evidence record and commit it separately as `docs: record factory v1 verification`. Fetch and inspect the remote again; stop on divergence or a dirty worktree. Push the checkpoint branch, confirm local/tracking/remote branch SHAs, await the human merge decision, merge it into `main` with `--no-ff`, rerun the applicable local gate on the merged result, push `main`, and confirm local `main`, `origin/main`, and remote `main` SHAs match. Preserve the completed checkpoint branch. Create an annotated `factory/<job-id>` tag on the merge commit only for jobs run through the factory, push it, and confirm its remote peeled SHA equals the merge commit; this plan checkpoint itself has no factory job ID and needs no tag.

## Plan handoff

After the factory checkpoint is merged, define the sample application and comparable task packets in a new design cycle. The first sample-app task can then be run through the factory. The visual board is a later factory task that reads job records without becoming their writer.
