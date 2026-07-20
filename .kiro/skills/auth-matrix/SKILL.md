---
name: auth-matrix
description: Generate and verify explicit role, scope, resource, and action authorization matrices. Use when implementing or testing RBAC, tenant isolation, station or district boundaries, disaster assignments, privileged actions, or Prompt 19-26 security gates.
---

# Authorization Matrix

Turn authorization requirements into deterministic cases and fail when actual results disagree with the approved policy.

## Workflow

1. Read `references/authorization-policy.md`.
2. Identify the authoritative policy in backend guards, product requirements, or an approved policy file. Never infer access from the current UI.
3. Create a policy JSON containing roles and explicit cases.
4. Generate a normalized matrix:

   `python .kiro/skills/auth-matrix/scripts/generate_matrix.py generate --phase 19 --spec path/to/policy.json`

5. Exercise every mandatory case through the narrowest meaningful layer. Record `ALLOW` or `DENY`, plus an evidence path, in a results JSON.
6. Verify the results:

   `python .kiro/skills/auth-matrix/scripts/generate_matrix.py verify --phase 19 --matrix artifacts/phase-19/authorization-matrix.json --results path/to/results.json`

7. Treat a missing result, unexpected result, duplicate case ID, or missing evidence as a failed security gate.

## Input Formats

Policy specification:

```json
{
  "roles": ["investigator", "supervisor", "super_admin"],
  "cases": [
    {
      "id": "investigator-own-case-read",
      "role": "investigator",
      "scope": "own_station",
      "resource": "case",
      "action": "read",
      "expected": "ALLOW",
      "mandatory": true
    }
  ]
}
```

Results specification:

```json
{
  "results": [
    {
      "id": "investigator-own-case-read",
      "actual": "ALLOW",
      "evidence": "artifacts/phase-19/test-runs/auth-own-case.json"
    }
  ]
}
```

`expected` and `actual` accept only `ALLOW` or `DENY`. Evidence must resolve beneath the repository root and must exist.

## Safety Rules

- Include negative cross-scope and cross-tenant cases, not only allowed paths.
- Test server-side enforcement; disabled controls are not proof.
- Do not put access tokens, cookies, credentials, or personal records in evidence.
- Use synthetic IDs and redact account numbers, emails, and bearer values.
- Preserve the generated policy hash so reviewers can detect policy drift.

