#!/usr/bin/env python3
"""Strictly audit the DRISHTI evidence manifest and referenced artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "N/A"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {value}") from exc
    return candidate


def audit_record(root: Path, item: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    status = str(item.get("status", ""))
    mandatory = bool(item.get("mandatory", True))
    if status not in STATUSES:
        issues.append(f"invalid status: {status!r}")
    elif mandatory and status != "PASS":
        issues.append(f"mandatory item is {status}")
    elif not mandatory and status not in {"PASS", "N/A"}:
        issues.append(f"optional item is {status}")
    if status == "PASS":
        if item.get("exit_code") not in (None, 0):
            issues.append("PASS has non-zero exit code")
        artifact_value = item.get("artifact")
        expected_hash = item.get("artifact_sha256")
        if not artifact_value or not expected_hash:
            issues.append("PASS lacks artifact path or hash")
        else:
            try:
                artifact = safe_path(root, str(artifact_value))
                if not artifact.is_file():
                    issues.append(f"artifact not found: {artifact_value}")
                elif digest(artifact) != expected_hash:
                    issues.append(f"artifact hash mismatch: {artifact_value}")
            except ValueError as exc:
                issues.append(str(exc))
        if item.get("environment") == "live" and not item.get("resource_id"):
            issues.append("live PASS lacks resource_id")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", default="artifacts/evidence-manifest.json")
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--output", default="artifacts/release-audit.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = safe_path(root, args.manifest)
    if not manifest_path.is_file():
        parser.error(f"manifest not found: {args.manifest}")
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("evidence"), list):
        parser.error("unsupported or malformed evidence manifest")

    requirements_path = safe_path(root, args.requirements)
    if not requirements_path.is_file():
        parser.error(f"requirements file not found: {args.requirements}")
    requirements_doc = json.loads(requirements_path.read_text(encoding="utf-8"))
    if requirements_doc.get("schema_version") != 1:
        parser.error("unsupported requirements schema")
    requirements = requirements_doc.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        parser.error("requirements file must contain a non-empty requirements array")
    requirement_ids: set[str] = set()
    for requirement in requirements:
        requirement_id = str(requirement.get("id", "")) if isinstance(requirement, dict) else ""
        if not requirement_id or requirement_id in requirement_ids:
            parser.error(f"duplicate or empty requirement id: {requirement_id!r}")
        requirement_ids.add(requirement_id)

    seen: set[str] = set()
    findings: list[dict[str, Any]] = []
    for item in document["evidence"]:
        record_id = str(item.get("id", ""))
        issues = audit_record(root, item)
        if not record_id:
            issues.append("missing id")
        elif record_id in seen:
            issues.append("duplicate id")
        seen.add(record_id)
        findings.append({"id": record_id, "phase": item.get("phase"), "issues": issues})

    for requirement in requirements:
        requirement_id = str(requirement["id"])
        if requirement_id not in seen:
            findings.append(
                {
                    "id": requirement_id,
                    "phase": requirement.get("phase"),
                    "mandatory": bool(requirement.get("mandatory", True)),
                    "issues": ["missing evidence (NOT_RUN)"],
                }
            )

    failed = sum(bool(item["issues"]) for item in findings)
    report = {
        "schema_version": 1,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if failed == 0 else "FAIL",
        "requirements_count": len(requirements),
        "evidence_count": len(document["evidence"]),
        "finding_count": len(findings),
        "failed_count": failed,
        "findings": findings,
        "coverage_note": "Every declared requirement has an explicit evidence disposition.",
    }
    output = safe_path(root, args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: {output}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
