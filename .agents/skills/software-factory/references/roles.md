# Role contracts

Every role receives repository paths and a job ID. Read the files named here; do not rely on the orchestrator's conversation. Report the artifact path, commit SHA if relevant, and anything blocking completion. The orchestrator remains the sole writer of `state.json` and `decision.md`.

| Role | Reads | Writes | Completion report |
| --- | --- | --- | --- |
| Spec writer | Frozen `task.md`, relevant code and project docs, `assets/spec.md` | That job's `spec.md` only | Acceptance criteria, ambiguities, affected files, spec path |
| Builder | Frozen `task.md`, accepted `spec.md`, relevant code, prior complete review round during repair, `assets/build.md` | Product code and that job's `build.md`; focused commits | Commit SHA, each exact check command/status/output, build path |
| Code reviewer | `task.md`, `spec.md`, `build.md`, branch diff, check evidence, `assets/review.md` | Assigned `reviews/round-N/code.md` only | `PASS` or `CHANGES`; findings with severity and file references |
| Security reviewer, when assigned | Same shared review inputs, emphasizing credentials, permissions, untrusted input, and dependencies | Assigned `reviews/round-N/security.md` only | Verdict and concrete security findings |
| UI reviewer, when assigned | Same shared review inputs, emphasizing user-visible behavior and accessibility | Assigned `reviews/round-N/ui.md` only | Verdict and concrete UI findings |
| Orchestrator | Task, state, all artifacts, Git refs | `state.json`, `decision.md`, `human_interventions`, and ownership claim; creates packet at intake | Transition reason, complete evidence, final decision |

The builder never approves its own code as the only review. Reviewers never edit implementation. A review round closes only after each assigned report exists; the orchestrator consolidates findings after that barrier. The same builder receives repairs. In solo mode, the spec writer and builder may be one agent, but review remains independent.
