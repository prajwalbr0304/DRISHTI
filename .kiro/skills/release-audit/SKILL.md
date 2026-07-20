---
name: release-audit
description: Perform a strict, read-only audit of DRISHTI evidence manifests and artifact integrity. Use for Prompt 26, release readiness, handoff reviews, or whenever mandatory claims must be independently classified as PASS, FAIL, BLOCKED, or NOT_RUN.
---

# Release Audit

Audit evidence independently. Do not repair implementation while wearing the auditor role.

## Workflow

1. Read `references/strict-statuses.md`.
2. Use a fresh `evidence-auditor` agent when possible so implementation context does not bias classification.
3. Run:

   `python .kiro/skills/release-audit/scripts/audit_manifest.py --root . --manifest artifacts/evidence-manifest.json --requirements docs/execution/RELEASE_REQUIREMENTS.json`

4. Inspect failures and the generated `artifacts/release-audit.json`.
5. Maintain the requirements file from the selected prompt's acceptance criteria. The
   auditor fails if this coverage file is missing, empty, duplicated, or lacks evidence.
6. Report missing coverage as `NOT_RUN`, never silently omit it.
7. Return failed phases to the implementation orchestrator. Re-run the audit only after new evidence is recorded.

## Strict Gate

The audit fails when:

- a mandatory item is not `PASS`;
- an optional item has a status other than `PASS` or `N/A`;
- a passing artifact is absent, outside the repository, or hash-mismatched;
- a live passing claim has no stable resource ID;
- IDs are duplicated or the manifest schema is unsupported;
- the requirements coverage file is missing/empty or names an item with no evidence;
- a passing command records a non-zero exit code.

Code presence, mocked output, or an implementation agent's narrative is not proof.

## Scope

The script verifies structural and artifact integrity. The auditor must separately compare the manifest coverage against Prompt 18-26 acceptance criteria, authorization boundaries, deployment requirements, and demo flow.
