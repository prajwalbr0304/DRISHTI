#!/usr/bin/env python3
"""Generate and verify deterministic authorization test matrices."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DECISIONS = {"ALLOW", "DENY"}
REQUIRED = {"id", "role", "scope", "resource", "action", "expected"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def repo_path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"evidence escapes repository root: {value}") from exc
    return candidate


def normalize_cases(spec: dict[str, Any]) -> list[dict[str, Any]]:
    cases = spec.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("policy spec must contain a non-empty cases array")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in cases:
        if not isinstance(raw, dict) or not REQUIRED.issubset(raw):
            raise ValueError(f"case is missing required fields: {raw!r}")
        case_id = str(raw["id"]).strip()
        expected = str(raw["expected"]).upper()
        if not case_id or case_id in seen:
            raise ValueError(f"duplicate or empty case id: {case_id!r}")
        if expected not in DECISIONS:
            raise ValueError(f"{case_id}: expected must be ALLOW or DENY")
        seen.add(case_id)
        normalized.append(
            {
                "id": case_id,
                "role": str(raw["role"]),
                "scope": str(raw["scope"]),
                "resource": str(raw["resource"]),
                "action": str(raw["action"]),
                "expected": expected,
                "mandatory": bool(raw.get("mandatory", True)),
            }
        )
    return sorted(normalized, key=lambda item: item["id"])


def generate(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec = load_json(spec_path)
    cases = normalize_cases(spec)
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    output = Path(args.output or f"artifacts/phase-{args.phase:02d}/authorization-matrix.json")
    document = {
        "schema_version": 1,
        "phase": args.phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(spec_path),
        "policy_sha256": hashlib.sha256(canonical).hexdigest(),
        "roles": sorted({case["role"] for case in cases}),
        "cases": cases,
    }
    write_json(output, document)
    print(output)
    return 0


def verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    matrix = load_json(Path(args.matrix))
    results_doc = load_json(Path(args.results))
    results_list = results_doc.get("results") if isinstance(results_doc, dict) else None
    if not isinstance(results_list, list):
        raise ValueError("results file must contain a results array")
    results: dict[str, dict[str, Any]] = {}
    for item in results_list:
        case_id = str(item.get("id", ""))
        if not case_id or case_id in results:
            raise ValueError(f"duplicate or empty result id: {case_id!r}")
        results[case_id] = item

    checks: list[dict[str, Any]] = []
    failed = 0
    for case in matrix.get("cases", []):
        result = results.get(case["id"])
        issues: list[str] = []
        if result is None:
            issues.append("missing result")
        else:
            actual = str(result.get("actual", "")).upper()
            if actual not in DECISIONS:
                issues.append("actual must be ALLOW or DENY")
            elif actual != case["expected"]:
                issues.append(f"expected {case['expected']}, got {actual}")
            evidence = str(result.get("evidence", "")).strip()
            if not evidence:
                issues.append("missing evidence")
            elif not repo_path(root, evidence).is_file():
                issues.append(f"evidence not found: {evidence}")
        if issues and case.get("mandatory", True):
            failed += 1
        checks.append({"id": case["id"], "mandatory": case.get("mandatory", True), "issues": issues})

    unknown = sorted(set(results) - {case["id"] for case in matrix.get("cases", [])})
    if unknown:
        failed += len(unknown)
    report = {
        "schema_version": 1,
        "phase": matrix.get("phase"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "policy_sha256": matrix.get("policy_sha256"),
        "status": "PASS" if failed == 0 else "FAIL",
        "failed_count": failed,
        "unknown_result_ids": unknown,
        "checks": checks,
    }
    output = Path(args.output or f"artifacts/phase-{int(matrix.get('phase', 0)):02d}/authorization-verification.json")
    write_json(output, report)
    print(f"{report['status']}: {output}")
    return 0 if failed == 0 else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    make = commands.add_parser("generate")
    make.add_argument("--phase", type=int, required=True)
    make.add_argument("--spec", required=True)
    make.add_argument("--output")
    make.set_defaults(handler=generate)
    check = commands.add_parser("verify")
    check.add_argument("--phase", type=int, help="accepted for command symmetry; matrix phase remains authoritative")
    check.add_argument("--matrix", required=True)
    check.add_argument("--results", required=True)
    check.add_argument("--root", default=".")
    check.add_argument("--output")
    check.set_defaults(handler=verify)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
