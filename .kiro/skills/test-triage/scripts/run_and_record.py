#!/usr/bin/env python3
"""Run one bounded command and record redacted log plus JSON metadata."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


REDACTIONS = (
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"), r"\1[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b\d{12}\b"), "[REDACTED_ACCOUNT_ID]"),
    (re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[=:]\s*[^\s,]+"), r"\1=[REDACTED]"),
)


def redact(value: str) -> str:
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.name):
        parser.error("--name must be a filesystem-safe identifier")
    repo = args.repo.resolve()
    cwd = (args.cwd if args.cwd.is_absolute() else repo / args.cwd).resolve()
    try:
        cwd.relative_to(repo)
    except ValueError:
        parser.error("--cwd must remain beneath --repo")
    executable = shutil.which(command[0])
    if executable:
        command[0] = executable
    out = repo / f"artifacts/phase-{args.phase:02d}/test-runs"
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    began = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            shell=False,
        )
        exit_code = result.returncode
        combined = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        combined = stdout + ("\n" + stderr if stderr else "") + f"\nTIMEOUT after {args.timeout}s\n"
    duration = round(time.monotonic() - began, 3)
    log_path = out / f"{args.name}.log"
    summary_path = out / f"{args.name}.json"
    log_path.write_text(redact(combined), encoding="utf-8")
    summary = {
        "name": args.name,
        "phase": args.phase,
        "started_at": started,
        "duration_seconds": duration,
        "command": [redact(part) for part in command],
        "cwd": str(cwd),
        "exit_code": exit_code,
        "status": "TIMEOUT" if timed_out else ("PASS" if exit_code == 0 else "FAIL"),
        "log": str(log_path.relative_to(repo)),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
