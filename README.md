# Software Factory

This repository contains a repo-local, agent-operated software factory workflow for running and resuming software jobs from files. It currently includes the job record validator, single-writer state helper, role templates, and a Codex skill. A sample application and visual board have not been built yet.

The [approved design](docs/superpowers/specs/2026-10-14-software-factory-design.md) and [implementation plan](docs/superpowers/plans/2026-10-14-software-factory-v1.md) explain the experiment. The [software factory skill](.agents/skills/software-factory/SKILL.md) describes how to invoke a new job with `$software-factory new <request>` or resume one with `$software-factory resume <job-id>` in Codex. The [job format](factory/job-format.md) defines the files a fresh session reads.

To run local checks:

```sh
python3 -m unittest discover -s tests -v
python3 tools/validate_job.py <path-to-job-directory>
git diff --check
```

`validate_job.py` exits 0 for a valid job, 1 for invalid records, and 2 for unreadable JSON or invalid invocation. `python3 tools/job_io.py --help` lists claim, release, and write-state commands. The workflow requires a user invocation and does not merge automatically.
