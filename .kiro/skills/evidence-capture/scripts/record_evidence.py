#!/usr/bin/env python3
"""Add or update a redacted evidence record in the DRISHTI manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "N/A"}
REDACTIONS = (
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b\d{12}\b"), "[REDACTED_ACCOUNT_ID]"),
    (re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
)


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def within_root(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact must remain beneath repository root") from exc
    return candidate


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "evidence": []}
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("evidence"), list):
        raise ValueError("unsupported or malformed evidence manifest")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--environment", choices=("local", "ci", "staging", "live"), required=True)
    parser.add_argument("--status", choices=sorted(STATUSES), required=True)
    parser.add_argument("--command")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--artifact")
    parser.add_argument("--resource-id")
    parser.add_argument("--notes")
    parser.add_argument("--optional", action="store_true")
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", default="artifacts/evidence-manifest.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    status = args.status.upper()
    if status == "PASS" and args.exit_code not in (None, 0):
        parser.error("PASS cannot have a non-zero exit code")
    if status == "PASS" and not args.artifact:
        parser.error("PASS requires --artifact")
    if status == "PASS" and args.environment == "live" and not args.resource_id:
        parser.error("live PASS requires --resource-id")

    artifact_hash = None
    artifact_value = None
    if args.artifact:
        artifact = within_root(root, args.artifact)
        if not artifact.is_file():
            parser.error(f"artifact does not exist: {args.artifact}")
        artifact_value = artifact.relative_to(root).as_posix()
        artifact_hash = sha256(artifact)

    manifest_path = within_root(root, args.manifest)
    manifest = load_manifest(manifest_path)
    record = {
        "id": redact(args.id),
        "phase": args.phase,
        "capability": redact(args.capability),
        "category": redact(args.category),
        "environment": args.environment,
        "status": status,
        "mandatory": not args.optional,
        "command": redact(args.command),
        "exit_code": args.exit_code,
        "artifact": artifact_value,
        "artifact_sha256": artifact_hash,
        "resource_id": redact(args.resource_id),
        "notes": redact(args.notes),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    records = [item for item in manifest["evidence"] if item.get("id") != record["id"]]
    records.append(record)
    manifest.update(
        {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "evidence": sorted(records, key=lambda item: (int(item.get("phase", 0)), str(item.get("id")))),
        }
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
