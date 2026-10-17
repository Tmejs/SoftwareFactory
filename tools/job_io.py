"""Single-writer ownership and atomic state replacement for a local job."""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .validate_job import validate_state
else:
    from validate_job import validate_state


def claim(job_dir: Path, owner: str) -> None:
    if not owner or not owner.strip():
        raise ValueError("owner ID is required")
    lock = Path(job_dir) / "owner.lock"
    lock.mkdir()
    try:
        record = {"owner": owner, "claimed_at": datetime.now(timezone.utc).isoformat()}
        (lock / "owner.json").write_text(json.dumps(record))
    except BaseException:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()
        raise


def _require_owner(job_dir: Path, owner: str) -> Path:
    lock = Path(job_dir) / "owner.lock"
    try:
        record = json.loads((lock / "owner.json").read_text())
    except (OSError, ValueError) as exc:
        raise PermissionError("job has no readable owner claim") from exc
    if record.get("owner") != owner:
        raise PermissionError("job is claimed by another orchestrator")
    return lock


def release(job_dir: Path, owner: str) -> None:
    lock = _require_owner(job_dir, owner)
    (lock / "owner.json").unlink()
    lock.rmdir()


def write_state(job_dir: Path, owner: str, state: dict) -> None:
    job_dir = Path(job_dir)
    _require_owner(job_dir, owner)
    errors = validate_state(job_dir, state)
    if errors:
        raise ValueError("invalid state: " + "; ".join(errors))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=job_dir, prefix=".state-", delete=False) as tmp:
            temp_path = Path(tmp.name)
            json.dump(state, tmp, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_path, job_dir / "state.json")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Claim or update a SoftwareFactory job")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("claim", "release", "write-state"):
        command = sub.add_parser(name)
        command.add_argument("job_dir", type=Path)
        command.add_argument("owner")
        if name == "write-state":
            command.add_argument("candidate_json", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "claim":
            claim(args.job_dir, args.owner)
        elif args.command == "release":
            release(args.job_dir, args.owner)
        else:
            try:
                state = json.loads(args.candidate_json.read_text())
            except (OSError, ValueError) as exc:
                print("unreadable candidate JSON: " + str(exc), file=sys.stderr)
                return 2
            write_state(args.job_dir, args.owner, state)
    except (FileExistsError, PermissionError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
