#!/usr/bin/env python3
"""Capture bounded Catalyst login/version checks and repository placeholders."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _resolve(exe: str) -> str:
    """Resolve a CLI name to an executable path, including Windows shims
    (`catalyst.cmd` / `catalyst.ps1`) that a bare subprocess argv cannot find."""
    found = shutil.which(exe)
    if found:
        return found
    if sys.platform.startswith("win"):
        for ext in (".cmd", ".exe", ".bat", ".ps1"):
            found = shutil.which(exe + ext)
            if found:
                return found
    return exe


TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".js", ".mjs", ".ts", ".md", ".toml"}
PLACEHOLDER = re.compile(r"<(?:ACCOUNT_ID|PROJECT_ID|ORG(?:ANIZATION)?_ID|REGION|SUBNET|SECURITY_GROUP|ROLE|BUCKET|KMS|MODEL|DIGEST|[^>]*PLACEHOLDER[^>]*)>", re.I)
REDACTIONS = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b\d{12}\b"), "[REDACTED_ACCOUNT_ID]"),
    (re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
)


def redact(value: str) -> str:
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def command_result(command: list[str], cwd: Path, timeout: int = 25) -> dict:
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                                timeout=timeout, stdin=subprocess.DEVNULL)
        text = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
        return {"command": command, "exit_code": result.returncode, "output": redact(text[:4000])}
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": 124, "output": f"timeout after {timeout}s"}
    except FileNotFoundError:
        return {"command": command, "exit_code": 127, "output": "catalyst CLI not found"}


def placeholders(root: Path) -> list[dict]:
    findings: list[dict] = []
    if not root.exists():
        return findings
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if PLACEHOLDER.search(line) or "invalid-api" in line.lower():
                findings.append({"path": str(path), "line": line_no, "sample": redact(line.strip()[:240])})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--dc", default="in")
    parser.add_argument("--phase", type=int, default=23)
    args = parser.parse_args()
    repo = args.repo.resolve()
    catalyst = _resolve("catalyst")
    # Run the CLI from the bound project dir (where .catalystrc lives); the CLI
    # is unbound at repo root and its winston file logger crashes on teardown
    # under captured stdio there.
    cli_cwd = repo / "infra" / "catalyst"
    if not cli_cwd.exists():
        cli_cwd = repo
    # `catalyst project:list` is the idempotent, non-interactive auth+access
    # probe: it succeeds only when logged in and runs cleanly under captured
    # stdio from the bound dir. (The interactive `login`/`whoami` subcommands
    # crash this CLI version's winston file logger when stdout is a pipe;
    # `--dc` is retained only for the recorded expectation.)
    checks = [
        command_result([catalyst, "--version"], cli_cwd),
        command_result([catalyst, "project:list"], cli_cwd),
    ]
    found = placeholders(repo / "infra/catalyst")
    record = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "expected": {"project_id": "48361000000030003", "organization_id": "60075362708", "dc": args.dc},
        "cli_checks": checks,
        "placeholder_findings": found,
        "ready": all(item["exit_code"] == 0 for item in checks) and not found,
        "note": "This preflight does not prove live component existence or invocation.",
    }
    out = repo / f"artifacts/phase-{args.phase:02d}/catalyst-preflight.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0 if record["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
