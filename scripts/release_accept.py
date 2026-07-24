#!/usr/bin/env python3
"""DRISHTI strict release acceptance (Prompt 25 Part J).

ONE command that decides whether DRISHTI may be declared ready for a synthetic
hackathon demonstration. It is deliberately strict: it exits non-zero (PENDING)
if ANY mandatory Prompt-25 requirement is not genuinely PASS, if any required
release artifact is missing, or if the evidence-manifest audit fails.

It aggregates:
  1. required release artifacts exist (Part H);
  2. the strict evidence-manifest audit (release-audit skill) over the p25
     mandatory requirements in docs/execution/RELEASE_REQUIREMENTS.json;
  3. the machine-readable FINAL_TEST_SUMMARY.json verdict.

A zero exit means: declare ONLY "DRISHTI is ready for a synthetic hackathon
demonstration on Zoho Catalyst." Never production readiness. A non-zero exit
means Prompt 25 stays Pending with the printed remediation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED_ARTIFACTS = [
    "docs/phase-reports/PHASE_25_REPORT.md",
    "HACKATHON_DEMO_CHECKLIST.md",
    "HACKATHON_DEMO_RUNBOOK.md",
    "DISASTER_RECOVERY_RUNBOOK.md",
    "MODEL_RELEASE_CHECKLIST.md",
    "POST_HACKATHON_BACKLOG.md",
    "docs/deployment/FINAL_ARCHITECTURE.md",
    "docs/deployment/CATALYST_AWS_SERVICE_INVENTORY.md",
    "docs/deployment/ORGANIZER_CAPABILITY_EVIDENCE.md",
    "docs/deployment/ORGANIZER_NOTES_COVERAGE.md",
    "docs/deployment/FINAL_TEST_SUMMARY.json",
    "docs/deployment/SCREENSHOT_VIDEO_EVIDENCE.md",
]


def check_artifacts() -> list[str]:
    missing = [a for a in REQUIRED_ARTIFACTS if not (REPO / a).exists()
               or (REPO / a).stat().st_size == 0]
    return missing


def run_manifest_audit() -> tuple[bool, str]:
    script = REPO / ".kiro" / "skills" / "release-audit" / "scripts" / "audit_manifest.py"
    cmd = [sys.executable, str(script), "--root", str(REPO),
           "--manifest", "artifacts/phase-25/evidence-manifest-p25.json",
           "--requirements", "artifacts/phase-25/release-requirements-p25.json",
           "--output", "artifacts/phase-25/release-audit.json"]
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    return p.returncode == 0, (p.stdout or "") + (p.stderr or "")


def check_final_summary() -> tuple[bool, dict]:
    f = REPO / "docs" / "deployment" / "FINAL_TEST_SUMMARY.json"
    if not f.exists():
        return False, {"error": "FINAL_TEST_SUMMARY.json missing"}
    data = json.loads(f.read_text(encoding="utf-8"))
    reqs = data.get("p25_requirements", {})
    not_pass = {k: v.get("status") for k, v in reqs.items()
                if v.get("mandatory") and v.get("status") != "PASS"}
    return (not not_pass), {"verdict": data.get("overall_verdict"), "not_pass": not_pass}


def main() -> int:
    print("=" * 68)
    print("DRISHTI STRICT RELEASE ACCEPTANCE (Prompt 25 Part J)")
    print("=" * 68)

    missing = check_artifacts()
    print(f"\n[1] Required artifacts: {len(REQUIRED_ARTIFACTS) - len(missing)}/{len(REQUIRED_ARTIFACTS)} present")
    for m in missing:
        print(f"    MISSING: {m}")

    audit_ok, audit_out = run_manifest_audit()
    print(f"\n[2] Evidence-manifest strict audit: {'PASS' if audit_ok else 'FAIL'}")
    for line in audit_out.strip().splitlines()[-12:]:
        print(f"    {line}")

    summary_ok, summary = check_final_summary()
    print(f"\n[3] FINAL_TEST_SUMMARY mandatory requirements: {'ALL PASS' if summary_ok else 'NOT ALL PASS'}")
    print(f"    overall_verdict={summary.get('verdict')}")
    for k, v in summary.get("not_pass", {}).items():
        print(f"    NOT PASS: {k} = {v}")

    accepted = (not missing) and audit_ok and summary_ok
    print("\n" + "=" * 68)
    if accepted:
        print('RELEASE ACCEPTANCE: PASS')
        print('Declare ONLY: "DRISHTI is ready for a synthetic hackathon demonstration '
              'on Zoho Catalyst." Never production readiness.')
    else:
        print("RELEASE ACCEPTANCE: PENDING — mandatory checks are not all proven.")
        print("Do NOT declare readiness. Remediate the items above "
              "(see POST_HACKATHON_BACKLOG.md RB-1..RB-4) and re-run.")
    print("=" * 68)
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
