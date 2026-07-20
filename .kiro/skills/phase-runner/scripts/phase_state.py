#!/usr/bin/env python3
"""Manage DRISHTI phase state, preflight evidence, and concise handoffs."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PHASES = tuple(range(18, 27))
VALID_STATUS = {"pending", "in_progress", "complete", "blocked"}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_git(repo: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, timeout=30
    )
    output = (result.stdout or result.stderr).strip()
    return result.returncode, output


def default_state() -> dict:
    return {
        "schema_version": 1,
        "updated_at": now(),
        "phases": {str(phase): {"status": "pending"} for phase in PHASES},
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("phases", {})
    for phase in PHASES:
        state["phases"].setdefault(str(phase), {"status": "pending"})
    return state


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def preflight(repo: Path, phase: int) -> int:
    state_path = repo / "EXECUTION_STATE.json"
    state = load_state(state_path)
    branch_rc, branch = run_git(repo, "branch", "--show-current")
    status_rc, dirty = run_git(repo, "status", "--short")
    previous = phase - 1
    previous_status = state["phases"].get(str(previous), {}).get("status")
    dependency_ok = phase == 18 or previous_status == "complete"
    record = {
        "phase": phase,
        "timestamp": now(),
        "branch": branch if branch_rc == 0 else None,
        "dirty_paths": dirty.splitlines() if status_rc == 0 and dirty else [],
        "previous_phase": previous if phase > 18 else None,
        "previous_status": previous_status,
        "dependency_ok": dependency_ok,
        "prompt_file": "prompt3new.md",
    }
    write_json(repo / f"artifacts/phase-{phase:02d}/preflight.json", record)
    state["updated_at"] = now()
    state["current_phase"] = phase
    if dependency_ok and state["phases"][str(phase)]["status"] == "pending":
        state["phases"][str(phase)]["status"] = "in_progress"
    write_json(state_path, state)
    print(json.dumps(record, indent=2))
    return 0 if dependency_ok else 2


def handoff(repo: Path, phase: int, status: str, next_action: str) -> int:
    if status not in VALID_STATUS:
        raise ValueError(f"invalid status: {status}")
    state_path = repo / "EXECUTION_STATE.json"
    state = load_state(state_path)
    state["updated_at"] = now()
    state["current_phase"] = phase
    state["phases"][str(phase)] = {
        **state["phases"].get(str(phase), {}),
        "status": status,
        "updated_at": now(),
        "next_action": next_action,
    }
    write_json(state_path, state)
    handoff_path = repo / "docs/execution/NEXT_SESSION.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        "# Next DRISHTI session\n\n"
        f"- Phase: {phase}\n- Status: {status}\n- Updated: {now()}\n"
        f"- Next action: {next_action}\n\n"
        "Read EXECUTION_STATE.json, FILE_MAP.json, DECISIONS.md, "
        "RELEASE_REQUIREMENTS.json, this file, the selected phase, and git status "
        "before acting.\n",
        encoding="utf-8",
    )
    print(json.dumps(state["phases"][str(phase)], indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("preflight", "status", "handoff"):
        command = sub.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        if name != "status":
            command.add_argument("--phase", type=int, choices=PHASES, required=True)
        if name == "handoff":
            command.add_argument("--status", choices=sorted(VALID_STATUS), required=True)
            command.add_argument("--next-action", required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.action == "status":
        print(json.dumps(load_state(repo / "EXECUTION_STATE.json"), indent=2))
        return 0
    if args.action == "preflight":
        return preflight(repo, args.phase)
    return handoff(repo, args.phase, args.status, args.next_action)


if __name__ == "__main__":
    raise SystemExit(main())
