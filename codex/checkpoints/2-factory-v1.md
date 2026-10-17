# Checkpoint 2: Software factory v1

## Scope

Implement a repo-local Codex skill, per-job file contract, read-only validator, and atomic single-writer state helper. Sample application and visual board are separate later checkpoints. This checkpoint is a factory bootstrap, not a factory-run job, so it has no `factory/<job-id>` completion tag.

## Verification evidence

| Spec criterion | Command or exercise | Result |
| --- | --- | --- |
| Complete and invalid job records | `python3 -m unittest discover -s tests -v` | Exit 0; 32 tests passed, including missing review, failed/unavailable required check, path escape, malformed state, missing spec/build, and invalid review/repair counts. |
| Validator CLI | `python3 tools/validate_job.py --help` | Exit 0; required job-directory argument shown. |
| Ownership and atomic replacement | `python3 -m unittest tests.test_job_io -v` | Exit 0; 6 tests passed, including simultaneous competing claims, wrong owner, rejected candidate, and interrupted replacement preserving old state. |
| Skill packaging | `python3 /Users/matrzad/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/software-factory` | Exit 0; `Skill is valid!`. |
| Review barrier and file-based resumption | Fresh agent read only the repo skill and disposable job records in `/private/tmp/softwarefactory-task3-dryrun` and ran the validator | Validator exited 0. Agent identified review round 1, requested `review → repair` after the assigned `CHANGES` report, and correctly deferred builder assignment until the transition. |
| Independent per-job ownership | Disposable `dryrun-readme` and `dryrun-other` jobs were claimed by different owner IDs; only the second state was updated | Both validated with exit 0; first stayed `team`, second became `solo`; separate owner claims remained. |
| READY is not merged | Disposable job was moved to `READY` using `job_io.py write-state`, validated, and released; fresh agent inspected job and Git refs | Validator exited 0. Agent reported delivery pending: no committed job artifact, pushed checkpoint branch, verified merge, or completion tag. |
| Checkpoint whitespace and branch gate | `git diff --check origin/main...HEAD` | Exit 0 at implementation commit `e2b1c7d`. |

The tests use temporary job directories and the behavioral dry run used a disposable Git worktree. No disposable job is committed. Actual model and reasoning effort of the fresh-agent dry runs were not exposed by the runtime, so both are recorded as **unavailable** rather than inferred. Usage and cost were also unavailable.

## Findings and limits

The first synthetic packet lacked a specific README sentence, committed builder change, and Git branch metadata. The fresh agent recognized those gaps. A focused fix added machine checks for stage handoff files and review/repair counts. Semantic quality of a requested outcome, actual commit existence, and remote delivery state still require the skill's agent review and Git-ref gates; the read-only job validator does not claim to prove those facts.

The Codex-managed worktree path was outside the sandbox's writable roots. Implementation proceeded on the checkpoint branch in the writable checkout; the behavioral dry run used a separate disposable worktree under `/private/tmp`. This did not change `main`.
