---
name: evidence-capture
description: Record redacted, hash-verified implementation and test evidence in a machine-readable phase manifest. Use after builds, tests, deployments, cloud checks, demos, or any Prompt 18-26 claim that must survive final release audit.
---

# Evidence Capture

Create durable proof for each claim without storing credentials or sensitive personal data.

## Workflow

1. Read `references/evidence-schema.md` before adding a new evidence category.
2. Save the raw or summarized artifact beneath `artifacts/phase-XX/`.
3. Record it in the manifest:

   `python .kiro/skills/evidence-capture/scripts/record_evidence.py --phase 19 --id auth-backend-tests --capability "Backend authorization" --category test --environment local --status PASS --command "pytest tests/auth" --exit-code 0 --artifact artifacts/phase-19/test-runs/auth.log`

4. For a live cloud claim, also pass `--environment live` and `--resource-id` with a stable deployment, endpoint, job, or service identifier.
5. Use `--optional` only when the governing prompt explicitly marks the capability optional.
6. Re-recording an ID updates that item; IDs must be stable and phase-specific.

## Status Policy

- `PASS`: verified artifact exists, and any supplied exit code is zero.
- `FAIL`: executed and failed or contradicted the claim.
- `BLOCKED`: could not execute because of a concrete external dependency.
- `NOT_RUN`: no verification was performed.
- `N/A`: inapplicable; accepted only for optional items during release audit.

Never use planned work, code presence, mocks, or a UI screenshot as proof of a live backend or cloud resource.

## Safety

- The recorder redacts common bearer tokens, AWS access keys, account IDs, emails, and password-like values in text fields.
- Do not attach environment files, cookies, authorization headers, raw production records, or full cloud responses containing secrets.
- Prefer synthetic test data and the smallest useful excerpt.
- Treat the SHA-256 digest as integrity evidence, not as a secrecy mechanism.

