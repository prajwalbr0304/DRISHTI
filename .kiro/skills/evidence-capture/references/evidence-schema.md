# Evidence Manifest Schema

The canonical manifest is `artifacts/evidence-manifest.json` and contains:

- `schema_version`: currently `1`;
- `updated_at`: UTC timestamp;
- `evidence`: array of evidence records.

Each record contains a stable `id`, phase, capability, category, environment, status, mandatory flag, optional command and exit code, artifact path and SHA-256, stable live resource ID when applicable, notes, and recording timestamp.

Use repository-relative artifact paths. A `PASS` record must reference an existing file. A live `PASS` must include `resource_id`. The release auditor recomputes hashes and rejects missing or changed artifacts.

Recommended categories are `build`, `test`, `security`, `contract`, `deployment`, `cloud`, `demo`, and `documentation`.

