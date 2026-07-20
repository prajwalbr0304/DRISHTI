---
name: test-triage
description: Reproduce, minimize, classify, and record DRISHTI Python, TypeScript, integration, browser, and infrastructure test failures with bounded timeouts and durable logs. Use after any failing, hanging, flaky, or unexplained test gate.
---

# DRISHTI Test Triage

## Triage loop

1. Identify the smallest failing test or command.
2. Run `scripts/run_and_record.py` with a bounded timeout and a phase artifact directory.
3. Inspect the first relevant traceback/assertion, not the entire log.
4. Classify the failure using `references/test-tiers.md`.
5. Assign likely owning files and one minimal reproduction command.
6. Fix the cause without weakening assertions, then rerun targeted and affected suites.

Example:

```text
python .kiro/skills/test-triage/scripts/run_and_record.py \
  --phase 19 --name nlsql-policy-scope --cwd services/ml --timeout 120 -- \
  python -m pytest tests/test_nlsql.py::test_name -q
```

Use `--` before the command. The script stores a full redacted log and JSON summary under `artifacts/phase-XX/test-runs/`.

Never suppress, skip, xfail, or loosen a legitimate failure. Treat a timeout as `TIMEOUT`, not PASS or FAIL. Keep local, disposable integration, live Catalyst, live AWS, E2E, security, load, and recovery results separate.
