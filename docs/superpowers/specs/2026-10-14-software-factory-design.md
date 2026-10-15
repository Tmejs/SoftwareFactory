# Software Factory: Agent-Picked-Up Workflow

**Date:** 2026-10-14
**Status:** Design approved in conversation; implementation pending

## Purpose

Build a small, repo-local software factory to learn which multiagent software-development workflows work well. A fresh Codex session must be able to pick up a job from repository files, carry it through bounded stages, and leave evidence another session can inspect or resume. The factory is an experiment platform, not an autonomous production deployment system.

The first comparison is one agent doing specification and implementation versus separate spec and builder agents, with an independent review gate in both modes. Both modes use the same tasks, model settings, acceptance criteria, checks, and output format. Model routing is a later variable, tested separately from workflow shape.

## Sequence and scope

1. Build and verify the factory workflow, templates, job records, and a small record validator.
2. Define repeatable sample-application tasks after the factory exists.
3. Run those tasks through the factory and use the results to improve it.
4. Build a visual job board as a later factory task, reading the recorded job state.

The first factory version targets this repository, including the sample application that will later live in it. It has no dashboard, hosted control plane, scheduled trigger, external ticket integration, deployment automation, or automatic merge. It runs when a user invokes the repo-local skill in Codex. The design must remain understandable from its repository files within a few minutes.

## Components and ownership

| Component | Responsibility | Write ownership |
| --- | --- | --- |
| `AGENTS.md` | Short repository rules and pointers to the factory skill | Maintainers |
| `.agents/skills/software-factory/SKILL.md` | Entry point, stage transitions, orchestration, and stop rules | Maintainers |
| Skill `references/` | Role contracts and review policy | Maintainers |
| Skill `assets/` | Task, spec, build, review, and decision templates | Maintainers |
| `factory/jobs/<job-id>/task.md` | Objective, scope, context, acceptance criteria, and required checks | Requester or intake agent; frozen when a run starts |
| `factory/jobs/<job-id>/state.json` | Current stage, mode, assignments, attempts, and artifact paths | One orchestrator for that job |
| `factory/jobs/<job-id>/owner.lock` | Exclusive orchestration claim while a job is active | Claiming orchestrator |
| Other job artifacts | Work and evidence for a stage | The assigned role writes only its own artifact |
| Record validator | Check required files, schema, allowed states, transitions, and cross-file references | Read-only against jobs |

Each job owns its state. There is no shared mutable `board.json`. A later board derives its display from per-job records. Parallel jobs therefore do not contend over one status file. A running job keeps its artifacts in its own checkpoint worktree and branch, leaving the `main` checkout clean. The orchestrator claims `owner.lock` with an atomic create-if-absent operation before writing `state.json`; the lock records an owner identifier and claim time. It updates `state.json` atomically and remains its only writer for that job. A second orchestrator encountering the lock reports the conflict and does not proceed. A stopped job may be resumed only after the owner releases the claim or a human explicitly resolves an abandoned claim; elapsed time alone does not authorize takeover. The lock is local runtime state and is not committed.

Initial job layout:

```text
factory/jobs/<job-id>/
  task.md
  state.json
  owner.lock              # present only while actively claimed; untracked
  spec.md
  build.md
  reviews/
    round-1/
      code.md
      security.md       # only when assigned
      ui.md             # only when assigned
    round-2/             # only when needed
  decision.md
```

The exact JSON keys and Markdown templates are set in the implementation plan, but they must support the contracts and outcomes below. Job IDs are unique, filesystem-safe identifiers; artifact paths are relative to the repository and must remain inside the job directory.

## Job contract and lifecycle

The task packet contains an objective, boundaries, relevant context, observable acceptance criteria, and exact applicable checks. It records the intended target repository and baseline commit. The spec writer may clarify and sharpen the acceptance criteria but may not silently change the requested outcome. Ambiguous or missing information that changes the outcome leads to `NEEDS-HUMAN` with a focused question.

The orchestrator runs these stages:

1. **Intake:** Validate the task packet, confirm synchronized `main`, create the fresh checkpoint branch and isolated worktree, and create the job record there. Pin the baseline commit, workflow version, model profile, and run mode.
2. **Spec:** Produce `spec.md` with behavior, edge cases, files or boundaries affected, and acceptance criteria. A human reviews consequential scope changes.
3. **Build:** Give the builder the task and spec in the job's worktree. The builder commits reviewable changes, runs the exact applicable checks, and writes `build.md` with results and evidence.
4. **Review:** Assign code review for every build. Assign security review for changes involving credentials, permissions, untrusted input, dependencies, or other security-sensitive behavior. Assign UI review for user-facing interface changes. Reviewers work independently from the same spec, diff, and check results; they do not edit the implementation. They write `PASS` or `CHANGES` with concrete findings and file references.
5. **Repair:** Wait for every assigned review in the round. Consolidate `CHANGES` findings and return them to the same builder. After a repair, rerun applicable checks and every review affected by the changes. Allow at most two repair rounds. Missing reviewer output, failed checks, or an unresolved important finding cannot count as a pass.
6. **Decision:** Record `READY`, `NEEDS-HUMAN`, or `FAILED` in `decision.md`, with reasons and evidence links. `READY` means the job can enter the user's checkpoint push and merge workflow; it does not merge automatically. `NEEDS-HUMAN` contains the exact question or approval needed. `FAILED` records the stopping condition and available recovery path.

The orchestrator never treats an agent's assertion of success as check evidence. It records command, exit status, relevant output or artifact path, and any unavailable or inapplicable check. It does not let a builder review its own changes as the sole quality signal. A review round closes only when all assigned reviewers have reported.

## Experimental modes and model policy

**Solo mode:** One agent performs spec, build, and self-check stages in sequence, followed by the same independent review and final decision requirements. This is the baseline for comparing implementation organization; the review gate stays constant.

**Team mode:** Separate spec writer and builder roles, followed by independent reviewers that run in parallel when their work does not modify the same files. Reviewers receive file-based handoffs rather than relying on the orchestrator's conversation history.

The initial model profile pins GPT-6.1 Sol for every agent. Start with medium reasoning for orchestration and focused review, and high reasoning for spec, build, and code review. Record the actual model and reasoning effort used for each role in the job state, including deviations. Keep these settings equal between comparable solo and team trials. Later experiments may compare GPT-6 Astra for hard specification or review work and GPT-6 Luna for narrow intake work, changing one model variable at a time.

The role files define inputs, expected output, permitted writes, and completion criteria. They do not contain provider-specific syntax beyond the Codex skill entry point. The factory may use Codex subagents when available. A missing subagent capability produces `NEEDS-HUMAN` or a documented solo-mode run; it is not silently recorded as team mode.

## Git and checkpoint integration

The repository's user-provided Git workflow governs factory development and jobs. `main` is stable. Except for the one-time documentation bootstrap of this empty remote, factory changes use fresh `codex/checkpoint-<number>-<short-name>` branches from synchronized `main`. Before each checkpoint, confirm a clean `main`, fetch and inspect the remote, and confirm local `main` equals `origin/main`. Build jobs use isolated worktrees when parallel work is involved. The factory records local verification, independent review, branch and commit SHAs, and the final merge state. It never force-pushes, rewrites shared history, or merges over unexpected remote changes. The orchestrator stops and surfaces divergence or a dirty worktree.

The first implementation must not claim a job is complete until the repository's applicable local verification and `git diff --check` pass, an independent review has no Critical or Important findings, the evidence is recorded, the checkpoint branch is pushed, and the `--no-ff` merge into `main` is verified and synchronized. Confirm local, tracking, and remote checkpoint branch SHAs after push, and local, `origin/main`, and remote `main` SHAs after merge and push. Since the factory's initial decision is human-gated, a `READY` job remains pending until that Git workflow completes.

The tracked job record ends at `READY`; it cannot contain the SHA of a later merge without changing that SHA. After the verified merge, the factory creates and pushes a unique annotated `factory/<job-id>` tag pointing to the merge commit. The tag is the durable final delivery record. A later board derives pushed and merged status from Git refs and tags together with the per-job files. An existing tag is never replaced automatically.

## Evidence and comparison

Each run records its task and baseline commit, mode, workflow version, model profile, stage timestamps, branch and commit IDs, check results, review verdicts and rounds, final decision, and human interventions. Record token usage or cost only when the runtime exposes it; otherwise mark it unavailable rather than estimating. Store enough artifact paths and command output to reconstruct why the decision was made without depending on chat history.

Compare solo and team runs on the same task packet and starting commit in separate branches. Preserve both result branches and records for analysis; select at most one implementation to enter the checkpoint merge workflow. Primary result: acceptance criteria met with applicable checks and independent review passing. Secondary measures: elapsed time, number and severity of review findings, repair rounds, human interventions, and available usage. Do not treat raw PR count or code volume as quality. Record limitations such as nondeterministic model output, differing runs, or missing usage data.

## Verification of the factory itself

Before using the factory for sample-app work, verify with disposable job records that:

- A fresh session can identify the current stage and next action from files alone.
- The validator accepts a complete valid job and rejects missing artifacts, invalid transitions, and paths outside the job directory.
- Parallel reviewers write separate reports; the orchestrator waits for all assigned reports.
- A `CHANGES` verdict returns to the builder, and the configured repair limit stops an unresolved job.
- Failed or unavailable required checks produce `NEEDS-HUMAN` or `FAILED`, never `READY`. If a check proves inapplicable after the run starts, close that run and create a new versioned task packet with the reason. Restart comparable solo and team trials from their common baseline using the revised packet.
- Two jobs can progress without shared state edits.
- Two orchestrators racing to claim one job cannot both proceed, and a lock left by an interrupted run requires explicit resolution before takeover.

Keep the first verification harness small. The initial sample app and visual board are separate later checkpoints, implemented through the factory once this bootstrap is verified.

## Implementation decisions

The implementation plan will choose the exact state schema, role-file names, validator language, and commands that invoke or resume a job in Codex. These choices must preserve the contracts above. Sample-app features and benchmark task packets will be designed after the factory itself is working.
