# Strict Release Statuses

- **PASS**: execution succeeded and the referenced artifact proves the exact claim.
- **FAIL**: execution completed and contradicted the requirement or returned a failure.
- **BLOCKED**: a named external dependency prevented execution; this is not a pass.
- **NOT_RUN**: no qualifying execution evidence exists.
- **N/A**: the requirement is explicitly optional and does not apply.

Mandatory items accept only `PASS`. Optional items accept `PASS` or `N/A`. A blocked live deployment cannot be replaced by local or mocked evidence. A screenshot proves only the visible state shown; it does not prove hidden authorization or cloud execution.

The requirements coverage file uses `{"requirements": [{"id": "stable-id", "mandatory": true}]}`. Every requirement—including optional ones—must have an explicit evidence record so absence cannot disappear from the audit.
