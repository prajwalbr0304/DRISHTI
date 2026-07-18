# infra/catalyst/ds-import — serving-layer bootstrap (Phase 14 workflow §2)

The deployed operational database is **Catalyst Data Store** (matrix rows 6 +
10). AWS RDS keeps the complete historical/analytics corpus; only a curated,
linked serving subset is imported here. This directory owns the one-way
`bootstrap-catalyst-serving-data` workflow.

> **Deploy status:** SCAFFOLDED + LOCALLY VERIFIED. Config generation and the
> offline importer run and pass a dry-run/in-memory commit. The real import
> writes to Catalyst Data Store and is credit-spending — held for go-ahead.

## Import mechanism (corrected after live CLI inspection 2026-07-18)

`catalyst ds:import` **is** a real CLI command (`ds:import`, `ds:export`,
`ds:status` are all present in CLI 1.27.0 — an earlier note in this repo that
claimed otherwise was wrong and is corrected here). It bulk-writes a **CSV**
(uploaded to Stratus, or passed as a local path) into a Data Store table, driven
by a JSON config with `operation` and `find_by`:

```jsonc
// configs/CaseMaster.import.json (real ds:import schema)
{ "table_identifier": "Case", "operation": "upsert", "find_by": "ExternalID" }
```

`operation:"upsert"` + `find_by:"ExternalID"` = **idempotent upsert by the stable
ExternalID unique column**, exactly workflow §2's contract (re-running never
duplicates). Primary path:

```powershell
# CSV exported from AWS must include an ExternalID column
# (ExternalID = "<external_id_prefix>:<pk...>"; see import-manifest.json). $
catalyst ds:import serving-export/Case.csv --config configs/CaseMaster.import.json
catalyst ds:status import <job_id>     # or use a callback URL in the config
```

## Files

| File | Role |
|---|---|
| `generate_import_configs.py` | Reads `services/ml/app/datastore/mapping.py` → emits one real `configs/<Table>.import.json` per imported table + `import-manifest.json` (rich metadata) + `reserved-namespaces.json`. Fails closed on mapping drift. |
| `configs/*.import.json` | **Real `catalyst ds:import` configs** (`table_identifier` + `operation:upsert` + `find_by:ExternalID`). Passed directly to `--config`. |
| `import-manifest.json` | ExternalID prefix + pk/search/excluded columns + disposition + dev cap per table (drives CSV export + reconciliation + the offline importer). Disposition counts prove no source table is silently dropped. |
| `reserved-namespaces.json` | Board / Disaster namespaces reserved but **not** imported (phase-order rule). |
| `import_serving_subset.py` | **Offline / CI alternative** to `ds:import`: reads a JSONL export + the manifest, computes ExternalID, drops excluded columns, enforces the dev cap, and upserts by ExternalID via `CatalystDataStoreRepository.bulk_upsert` (same idempotency). In-memory dry-run by default; `--commit` writes. |
| `serving-export/` | (gitignored) AWS→CSV/JSONL exports; never committed. |

## Regenerate configs (safe, offline)

```powershell
python generate_import_configs.py
# -> 106 ds:import configs (93 operational + 13 ui_projection); 16 search-enabled.
```

## Offline import (held; credit-spending on --commit against Data Store)

```powershell
# Dry-run (in-memory, no cloud):
python import_serving_subset.py --source-table CaseMaster `
  --export serving-export/CaseMaster.export.jsonl
# Commit via SDK (inside AppSail / Catalyst-auth env):  $
$env:DRISHTI_USE_CATALYST_DATASTORE = "true"
python import_serving_subset.py --source-table CaseMaster `
  --export serving-export/CaseMaster.export.jsonl --commit
```

Each run prints source/accepted/rejected counts + content SHA-256 (and, on
commit, inserted/updated/rejected) — the reconciliation evidence for the cutover
report. No credentials or real PII are imported; synthetic labels + lineage are
preserved.

## Contract (workflow §2)

Read-only AWS export → validate synthetic/golden subset → hash/count → Data Store
upsert by `ExternalID` (`ds:import` or the offline importer) → S3→Stratus fixture
copy → relationship/object reconciliation → cutover report. **One-way only** —
never a two-way sync, never last-write-wins. Development imports are capped at
5,000 rows/table (Data Store dev ceiling); the curated subset is designed around
this.
