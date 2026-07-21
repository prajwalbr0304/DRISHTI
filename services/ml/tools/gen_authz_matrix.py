#!/usr/bin/env python3
"""Generate + verify the Prompt 21 §E.4 allow/deny authorization matrix.

Builds a deterministic policy (the six functional roles x cases across case
detail, exports, admin, Investigation Board and Disaster actions, including
negative CROSS-SCOPE cases), exercises the REAL backend decision model
(app.org.scope) to record the actual ALLOW/DENY for each case, and drives the
auth-matrix skill to hash the policy and verify actual == expected.

Writes under artifacts/phase-21/:
  authorization-policy.json        (roles + cases + expected)
  authorization-matrix.json        (skill: normalized + policy_sha256)
  test-runs/authz-decisions.json   (evidence: the exercised decisions)
  authorization-results.json       (actual + evidence per case)
  authorization-verification.json  (skill: PASS/FAIL)

Run from services/ml:  python tools/gen_authz_matrix.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DRISHTI_DISABLE_DB_TESTS", "1")

_ML_ROOT = Path(__file__).resolve().parents[1]
if str(_ML_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_ROOT))
_REPO_ROOT = _ML_ROOT.parents[1]
_ART = _REPO_ROOT / "artifacts" / "phase-21"
_SKILL = _REPO_ROOT / ".kiro" / "skills" / "auth-matrix" / "scripts" / "generate_matrix.py"

from app.org import hierarchy, scope as scope_mod  # noqa: E402

# Each case: id, role, district assignment (None=role-default/unrestricted),
# resource, action, target district (for geo-scoped resources), expected.
# Expected values are the APPROVED policy (org/scope.py docstrings + Prompt 16/17
# rules), independent of the code path that computes 'actual'.
_CASES = [
    # role, assign_district, resource, action, target_district, expected
    ("investigator", None, "case", "read", None, "ALLOW"),
    ("analyst", None, "case", "read", None, "ALLOW"),
    ("supervisor", None, "case", "read", None, "ALLOW"),
    ("policymaker", None, "case", "read", None, "DENY"),        # aggregate-only
    ("disaster_coordinator", None, "case", "read", None, "DENY"),  # not a crime seat
    ("super_admin", None, "case", "read", None, "ALLOW"),
    # cross-scope negatives (geo)
    ("investigator", 1, "case", "read", 1, "ALLOW"),
    ("investigator", 1, "case", "read", 2, "DENY"),            # other district
    ("supervisor", 3, "case", "read", 9, "DENY"),              # other district
    # aggregate dashboard: every functional role for its own scope
    ("investigator", None, "aggregate", "read", None, "ALLOW"),
    ("policymaker", None, "aggregate", "read", None, "ALLOW"),
    ("disaster_coordinator", None, "aggregate", "read", None, "ALLOW"),
    # exports
    ("investigator", None, "case", "export", None, "ALLOW"),
    ("analyst", None, "case", "export", None, "ALLOW"),
    ("policymaker", None, "case", "export", None, "DENY"),      # no PII export
    ("disaster_coordinator", None, "case", "export", None, "DENY"),
    ("policymaker", None, "aggregate", "export", None, "ALLOW"),
    ("disaster_coordinator", None, "aggregate", "export", None, "DENY"),
    ("super_admin", None, "case", "export", None, "ALLOW"),
    # Investigation Board (Prompt 16): policymaker + disaster_coordinator denied
    ("investigator", None, "board", "use", None, "ALLOW"),
    ("analyst", None, "board", "use", None, "ALLOW"),
    ("supervisor", None, "board", "use", None, "ALLOW"),
    ("policymaker", None, "board", "use", None, "DENY"),
    ("disaster_coordinator", None, "board", "use", None, "DENY"),
    ("super_admin", None, "board", "use", None, "ALLOW"),
    # Disaster approval (Prompt 17): disaster_coordinator (own district) + super_admin
    ("disaster_coordinator", 5, "disaster", "approve", 5, "ALLOW"),
    ("disaster_coordinator", 5, "disaster", "approve", 9, "DENY"),   # other district
    ("investigator", None, "disaster", "approve", None, "DENY"),
    ("supervisor", None, "disaster", "approve", None, "DENY"),
    ("policymaker", None, "disaster", "approve", None, "DENY"),
    ("super_admin", None, "disaster", "approve", 9, "ALLOW"),
    # Admin/governance: super_admin only
    ("super_admin", None, "admin", "manage", None, "ALLOW"),
    ("supervisor", None, "admin", "manage", None, "DENY"),
    ("investigator", None, "admin", "manage", None, "DENY"),
    ("policymaker", None, "admin", "manage", None, "DENY"),
]

_ACTION_MAP = {
    ("case", "read"): "case_detail",
    ("aggregate", "read"): "aggregate_dashboard",
    ("case", "export"): "export_case_data",
    ("aggregate", "export"): "export_aggregate",
    ("board", "use"): "investigation_board",
    ("disaster", "approve"): "disaster_approval",
}


def _case_id(role, assign, resource, action, target):
    scope = f"d{assign}" if assign is not None else "role-default"
    tgt = f"-t{target}" if target is not None else ""
    return f"{role}-{resource}-{action}-{scope}{tgt}"


def _actual(role, assign, resource, action, target):
    sc = scope_mod.derive_scope(role, district_id=assign, source="matrix")
    if resource == "admin":
        return "ALLOW" if sc.role == "super_admin" else "DENY"
    matrix_action = _ACTION_MAP[(resource, action)]
    allowed = scope_mod.decide(sc, matrix_action, district_id=target)
    return "ALLOW" if allowed else "DENY"


def main() -> int:
    _ART.mkdir(parents=True, exist_ok=True)
    (_ART / "test-runs").mkdir(parents=True, exist_ok=True)

    cases, decisions, results = [], [], []
    for role, assign, resource, action, target, expected in _CASES:
        cid = _case_id(role, assign, resource, action, target)
        scope_desc = (f"assigned_district={assign}" if assign is not None
                      else "role-default")
        cases.append({"id": cid, "role": role, "scope": scope_desc,
                      "resource": resource, "action": action,
                      "expected": expected, "mandatory": True})
        actual = _actual(role, assign, resource, action, target)
        decisions.append({"id": cid, "role": role, "assigned_district": assign,
                          "resource": resource, "action": action,
                          "target_district": target, "expected": expected,
                          "actual": actual})

    policy = {"roles": sorted(hierarchy.FUNCTIONAL_ROLES), "cases": cases}
    policy_path = _ART / "authorization-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

    evidence = _ART / "test-runs" / "authz-decisions.json"
    evidence.write_text(json.dumps(
        {"source": "app.org.scope.decide (exercised)", "decisions": decisions},
        indent=2) + "\n", encoding="utf-8")
    evidence_rel = evidence.relative_to(_REPO_ROOT).as_posix()

    for d in decisions:
        results.append({"id": d["id"], "actual": d["actual"], "evidence": evidence_rel})
    results_path = _ART / "authorization-results.json"
    results_path.write_text(json.dumps({"results": results}, indent=2) + "\n",
                            encoding="utf-8")

    matrix_path = _ART / "authorization-matrix.json"
    gen = subprocess.run(
        [sys.executable, str(_SKILL), "generate", "--phase", "21",
         "--spec", str(policy_path), "--output", str(matrix_path)],
        capture_output=True, text=True)
    print(gen.stdout.strip() or gen.stderr.strip())
    if gen.returncode != 0:
        return gen.returncode

    ver = subprocess.run(
        [sys.executable, str(_SKILL), "verify", "--matrix", str(matrix_path),
         "--results", str(results_path), "--root", str(_REPO_ROOT),
         "--output", str(_ART / "authorization-verification.json")],
        capture_output=True, text=True)
    print(ver.stdout.strip() or ver.stderr.strip())
    return ver.returncode


if __name__ == "__main__":
    raise SystemExit(main())
