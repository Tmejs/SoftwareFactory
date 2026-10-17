# Repository agent instructions

Read [the approved design](docs/superpowers/specs/2026-10-14-software-factory-design.md), [job format](factory/job-format.md), and [software factory skill](.agents/skills/software-factory/SKILL.md) before starting or resuming a factory job. Use the skill when the user invokes `$software-factory` with a request or job ID.

Treat `main` as stable. Before a checkpoint, require a clean main checkout, fetch and inspect remote state, and confirm local `main` equals `origin/main`. Work on a fresh `codex/checkpoint-<number>-<short-name>` branch from synchronized main. Use an isolated worktree when parallel work or subagents are involved. Preserve completed branches; do not force-push, reset shared history, delete branches, or merge over unexpected changes.

Run `python3 -m unittest discover -s tests -v` and `git diff --check` plus every task-specific applicable check. Record evidence and get an independent review; fix and re-review Critical or Important findings before push. Confirm local, tracking, and remote branch SHAs after push. Merge completed checkpoints with `--no-ff`, rerun the gate, push main, and confirm local, tracking, and remote main SHAs match. Factory jobs additionally follow the skill's human decision and completion-tag gate.

Keep the root README limited to verified behavior. Store checkpoint evidence under `codex/checkpoints/`.
