"""Read-only validation of durable SoftwareFactory job records."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
BRANCH_RE = re.compile(r"codex/checkpoint-[1-9][0-9]*-[a-z0-9][a-z0-9-]*\Z")
CHECK_RE = re.compile(r"- ([a-z0-9][a-z0-9-]*): (.+)\Z")
REPO = "https://github.com/Tmejs/SoftwareFactory"
ROLES = {"code", "security", "ui"}
STAGES = {"intake", "spec", "build", "review", "repair", "ready", "needs-human", "failed"}
TRANSITIONS = {
    None: {"intake"},
    "intake": {"spec"},
    "spec": {"build", "needs-human"},
    "build": {"review", "needs-human", "failed"},
    "review": {"repair", "ready", "needs-human", "failed"},
    "repair": {"build", "needs-human", "failed"},
}
REQUIRED_HEADINGS = (
    "Objective", "Scope", "Context", "Target repository", "Baseline commit",
    "Acceptance criteria", "Checks",
)
REQUIRED_FIELDS = (
    "schema_version", "id", "mode", "stage", "baseline", "workflow_commit",
    "branch", "model_profile", "agent_runs", "assigned_reviews", "review_round",
    "repair_count", "checks", "human_interventions", "artifacts", "history",
)


def safe_artifact(job_dir: Path, relative: str) -> Optional[Path]:
    """Resolve a repository-relative artifact, rejecting lexical and symlink escapes."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        return None
    try:
        root = job_dir.resolve().parents[2]
        candidate = (root / path).resolve()
        return candidate if candidate.is_relative_to(job_dir.resolve()) else None
    except (OSError, ValueError):
        return None


def _task_sections(job_dir: Path, errors: list[str]) -> dict:
    try:
        content = (job_dir / "task.md").read_text()
    except OSError:
        errors.append("missing task.md")
        return {}
    sections = {}
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    parsed = {key: "\n".join(value).strip() for key, value in sections.items()}
    for heading in REQUIRED_HEADINGS:
        if not parsed.get(heading):
            errors.append("missing task section: " + heading)
    return parsed


def _declared_checks(sections: dict, errors: list[str]) -> dict:
    declared = {}
    for line in sections.get("Checks", "").splitlines():
        if not line.strip():
            continue
        match = CHECK_RE.fullmatch(line.strip())
        if not match:
            errors.append("invalid task check: " + line.strip())
            continue
        name, command = match.groups()
        if name in declared:
            errors.append("duplicate task check: " + name)
        declared[name] = command
    if declared.get("git-diff-check") != "git diff --check":
        errors.append("missing required task check: git-diff-check")
    return declared


def _review_errors(job_dir: Path, roles: list, round_number: int, require_pass: bool) -> list[str]:
    errors = []
    for role in roles:
        if role not in ROLES:
            continue
        path = job_dir / "reviews" / ("round-" + str(round_number)) / (role + ".md")
        try:
            first = path.read_text().splitlines()[0]
        except (OSError, IndexError):
            errors.append("missing review: " + role)
            continue
        if first not in ("VERDICT: PASS", "VERDICT: CHANGES"):
            errors.append("invalid review verdict: " + role)
        elif require_pass and first != "VERDICT: PASS":
            errors.append("review not passed: " + role)
    return errors


def validate_state(job_dir: Path, state: dict) -> list[str]:
    """Return all job record errors; the proposed state need not be on disk."""
    errors = []
    if not isinstance(state, dict):
        return ["state must be an object"]
    for field in REQUIRED_FIELDS:
        if field not in state:
            errors.append("missing state field: " + field)
    if errors:
        return errors
    job_dir = Path(job_dir)
    if job_dir.parent.name != "jobs" or job_dir.parent.parent.name != "factory":
        errors.append("job directory must be factory/jobs/<id>")
    if state["schema_version"] != 1 or type(state["schema_version"]) is not int:
        errors.append("unsupported schema_version")
    identifier = state["id"]
    if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier) or identifier != job_dir.name:
        errors.append("invalid or mismatched job id")
    if state["mode"] not in ("solo", "team"):
        errors.append("invalid mode")
    stage = state["stage"]
    if not isinstance(stage, str) or stage not in STAGES:
        errors.append("invalid stage")
    for field in ("baseline", "workflow_commit"):
        if not isinstance(state[field], str) or not SHA_RE.fullmatch(state[field]):
            errors.append("invalid " + field)
    if not isinstance(state["branch"], str) or not BRANCH_RE.fullmatch(state["branch"]):
        errors.append("invalid branch")
    if not isinstance(state["model_profile"], dict) or not state["model_profile"]:
        errors.append("invalid model_profile")
    if not isinstance(state["agent_runs"], list):
        errors.append("invalid agent_runs")
    roles = state["assigned_reviews"]
    if not isinstance(roles, list) or "code" not in roles or not all(isinstance(r, str) and r in ROLES for r in roles) or len(roles) != len(set(roles)):
        errors.append("invalid assigned_reviews")
        roles = []
    for field, maximum in (("review_round", 3), ("repair_count", 2)):
        value = state[field]
        if type(value) is not int or not 0 <= value <= maximum:
            errors.append("invalid " + field)
    if not isinstance(state["human_interventions"], list):
        errors.append("invalid human_interventions")
    artifacts = state["artifacts"]
    if not isinstance(artifacts, list):
        errors.append("invalid artifacts")
    else:
        for relative in artifacts:
            if not isinstance(relative, str) or not relative or safe_artifact(job_dir, relative) is None:
                errors.append("unsafe artifact: " + str(relative))
    sections = _task_sections(job_dir, errors)
    if sections.get("Target repository") and sections["Target repository"] != REPO:
        errors.append("wrong target repository")
    if sections.get("Baseline commit") and sections["Baseline commit"] != state["baseline"]:
        errors.append("task baseline mismatch")
    declared = _declared_checks(sections, errors)
    checks = state["checks"]
    if not isinstance(checks, list):
        errors.append("invalid checks")
        checks = []
    evidence = {}
    for check in checks:
        if not isinstance(check, dict) or any(k not in check for k in ("name", "command", "status", "output")):
            errors.append("invalid check record")
            continue
        name = check["name"]
        if not isinstance(name, str):
            errors.append("invalid check name")
            continue
        if name in evidence:
            errors.append("duplicate check: " + name)
        evidence[name] = check
        if check["status"] not in ("pass", "fail", "unavailable", "inapplicable"):
            errors.append("invalid check status: " + name)
    history = state["history"]
    if not isinstance(history, list) or not history:
        errors.append("missing history")
    else:
        previous = None
        reached = set()
        repair_transitions = 0
        review_entries = 0
        for entry in history:
            if not isinstance(entry, dict) or any(k not in entry for k in ("from", "to", "at", "reason")):
                errors.append("invalid history entry")
                break
            source, target = entry["from"], entry["to"]
            allowed = TRANSITIONS.get(source, set()) if source is None or isinstance(source, str) else set()
            if source != previous or not isinstance(target, str) or target not in allowed:
                errors.append("invalid history transition")
            if target == "review":
                review_entries += 1
            if source == "review":
                round_number = entry.get("round")
                if type(round_number) is not int or not 1 <= round_number <= 3:
                    errors.append("invalid review exit round")
                else:
                    if round_number != review_entries:
                        errors.append("review exit round mismatch")
                    errors.extend(_review_errors(job_dir, roles, round_number, False))
                if target == "repair":
                    repair_transitions += 1
            if isinstance(target, str):
                reached.add(target)
            previous = target
        if previous != stage:
            errors.append("history stage mismatch")
        if repair_transitions > 2:
            errors.append("repair limit exceeded")
        if type(state["repair_count"]) is int and repair_transitions != state["repair_count"]:
            errors.append("repair_count history mismatch")
        if type(state["review_round"]) is int and review_entries != state["review_round"]:
            errors.append("review_round history mismatch")
        for reached_stage, artifact in (("build", "spec.md"), ("review", "build.md")):
            if reached_stage in reached:
                try:
                    if not (job_dir / artifact).read_text().strip():
                        errors.append("missing " + artifact)
                except OSError:
                    errors.append("missing " + artifact)
    if stage == "ready":
        round_number = state["review_round"]
        if type(round_number) is not int or round_number < 1:
            errors.append("ready requires review round")
        else:
            errors.extend(_review_errors(job_dir, roles, round_number, True))
        for name, command in declared.items():
            check = evidence.get(name)
            if check is None:
                errors.append("missing check: " + name)
            elif check["command"] != command:
                errors.append("check command mismatch: " + name)
            elif check["status"] != "pass":
                errors.append("check not passed: " + name)
        try:
            decision = (job_dir / "decision.md").read_text().splitlines()[0]
        except (OSError, IndexError):
            decision = None
        if decision != "DECISION: READY":
            errors.append("missing READY decision")
    elif stage in ("needs-human", "failed"):
        try:
            decision = (job_dir / "decision.md").read_text().splitlines()[0]
        except (OSError, IndexError):
            decision = None
        if decision != "DECISION: " + stage.upper():
            errors.append("missing terminal decision")
    return errors


def validate_job(job_dir: Path) -> list[str]:
    try:
        state = json.loads((Path(job_dir) / "state.json").read_text())
    except (OSError, ValueError) as exc:
        return ["unreadable state.json: " + str(exc)]
    return validate_state(Path(job_dir), state)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate a SoftwareFactory job directory")
    parser.add_argument("job_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        state = json.loads((args.job_dir / "state.json").read_text())
    except (OSError, ValueError) as exc:
        print("unreadable state.json: " + str(exc), file=sys.stderr)
        return 2
    errors = validate_state(args.job_dir, state)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
