# Phase 14 Part E — Data Store / Stratus / NoSQL / Cache migration

Companion to `PHASE_14_REPORT.md` §E. Status date: 2026-07-18.
Catalyst project: **DHRISTI** (`48361000000030003`), India (IN) DC, Development env.

> **Status legend:** **DONE** — executed + verified here (evidence inline) ·
> **IMPLEMENTED** — code/config written and locally verified · **HELD** — real
> artifact ready; the only remaining step is credit-spending or a console action.
>
> The read-only AWS RDS export actually ran (the DB is reachable). The
> credit-spending writes — `ds:import` into Catalyst Data Store and the Stratus
> object copy — are HELD; their offline equivalents are verified against the real
> data / real fixtures.

---

## 0. Item-by-item status (spec Part E, 1–12)

| # | Requirement | State |
|---|---|---|
| 1 | Versioned AWS PG → Data Store mapping covering every submitted domain | **DONE** (§1) |
| 2 | Stable ExternalID + idempotent imports; preserve lineage; no creds/PII | **DONE** (§2) |
| 3 | `CatalystDataStoreRepository` deployed default; RDS only offline/read-only | **DONE** (§3) |
| 4 | Export + validate a curated serving subset (~1–5k linked cases, ≤5k/table) | **DONE** — 106 tables, 86,472 rows, 1,500 linked cases (§4) |
| 5 | Import via supported CLI/SDK; capture ids/counts/rejects/relationships/hashes | **IMPLEMENTED**; `ds:import` write HELD (§5) |
| 6 | Data Store full-text search for deployed case/FIR/person/evidence; not external | **IMPLEMENTED** (§6) |
| 7 | Private Stratus buckets/prefixes; versioning/retention; quarantine; hash lineage | **IMPLEMENTED** (§7) |
| 8 | Copy Prompt 5 evidence fixtures S3→Stratus; verify hashes; update references | **IMPLEMENTED** (dry-run verified on real fixtures); commit HELD (§8) |
| 9 | NoSQL only for semi-structured state | **DONE** (§9) |
| 10 | Cache only for bounded-TTL state | **DONE** (§9) |
| 11 | One-way analytics sync boundary; results back as new records | **DONE (documented + enforced by design)** (§10) |
| 12 | Explicit bootstrap/cutover contract; reconciliation; repeatable rebuild | **DONE** (§10/§11) |

---

## 1. Versioned mapping — every submitted domain (item 1 — DONE)

`services/ml/app/datastore/mapping.py` (`MAPPING_VERSION = 2026.07.18-1`) is the
single source of truth: 122 source tables classified across organisation/
geography, case lifecycle, canonical identity, evidence, structured domains,
governance, analytics contract, reference, external context and assistant — each
with a `Disposition` (OPERATIONAL / UI_PROJECTION / ANALYTICS_ONLY / RESERVED /
NOT_IMPORTED). Board + Disaster namespaces are **RESERVED only** (phase-order
rule; `reserved-namespaces.json`), not created. `validate_mapping()` guards
against prefix collisions, reserved-vs-live collisions, and any protected
attribute (`CasteMaster`/`ReligionMaster`) being importable. The generator
emits **106 `ds:import` configs** (93 operational + 13 ui_projection) + the rich
`import-manifest.json`; regeneration is clean and drift-checked.

## 2. ExternalID + idempotency + no PII (item 2 — DONE)

Every imported row carries `ExternalID = "<prefix>:<pk...>"`; imports upsert by
it (`find_by:ExternalID`), so re-runs never duplicate. Sensitive columns are
dropped at export (`excluded_columns`: `RawIdentifierValue`, `RawAccountNo`,
`RestrictedText`, `RawPrompt`, `raw_payload`); protected attributes are
`NOT_IMPORTED`; `users`/`roles` are never imported (identity is Catalyst Auth).
Synthetic-data labels, timestamps and lineage columns are preserved verbatim.

## 3. CatalystDataStoreRepository is the deployed default (item 3 — DONE)

`app/datastore/repository.py`: narrow `DataStoreRepository` (upsert/get/query/
search/bulk_upsert by ExternalID) with `InMemoryDataStore` (tests/local) and
`CatalystDataStoreRepository` (SDK). `get_repository()` returns the Catalyst
repo when `DRISHTI_USE_CATALYST_DATASTORE=true`. No deployed operational endpoint
requires RDS; `DATABASE_URL` is in the AppSail `must_not_set_for_crud` list.

## 4. Curated serving-subset export (item 4 — DONE, real run)

**New** `infra/catalyst/ds-import/export_serving_subset.py` — a read-only,
one-way, reproducible exporter. It auto-detects each table's scope from its
columns and builds a **referentially-linked** subset:

- seed case set = golden ids first, then a deterministic fill up to
  `--target-cases` (≤ dev cap 5,000);
- **case-scoped** tables (have `CaseMasterID`) → filtered to the seed cases;
- **entity-scoped** tables (`CanonicalPerson`/`CanonicalOrganisation` and their
  FKs) → filtered to exactly the persons/orgs those seed cases reference
  (second-level FK resolution);
- reference/geography/governance/lookup → capped whole (small).

It drops excluded columns, adds `ExternalID`, preserves lineage, masks the DB
target, and writes `serving-export/<Table>.export.jsonl` + `_export-report.json`
(per-table source/exported/rejected counts + content SHA-256).

**Executed** against the live AWS RDS (`aws-rds:…ap-south-1…/drishti`, 100,000
cases) read-only: `--all --target-cases 1500` → **106 tables, 86,472 rows**,
`CaseMaster` = 1,500, `CanonicalPerson` = 3,970 (exactly the referenced persons).
Offline transform self-test: 9/9. `serving-export/` is git-ignored (synthetic
data, not committed).

## 5. Import + evidence capture (item 5 — IMPLEMENTED; write HELD)

Primary path is `catalyst ds:import <Table.csv> --config configs/<Table>.import.json`
(`operation:upsert, find_by:ExternalID`) — a real command in CLI 1.27.0. The
exporter emits **both** `serving-export/<Table>.csv` (ExternalID column first;
consumed directly by `ds:import`) and `<Table>.export.jsonl` (offline importer +
reconcile). The offline SDK equivalent `import_serving_subset.py` was verified
(dry-run + a `--commit` into the in-memory repo: 2 inserted, 1 rejected for an
incomplete PK, content SHA-256 emitted). Both capture source/accepted/rejected
counts + hashes. The real write into Catalyst Data Store is credit-spending and
HELD.

## 6. Data Store full-text search (item 6 — IMPLEMENTED)

**New** `app/datastore/search.py` (`RepositoryMetadataSearch`) runs case/FIR/
person/evidence metadata search over the mapping's search-enabled tables via
`DataStoreRepository.search` — the **Catalyst Data Store full-text search
component** in deployment, the in-memory fake locally. It is **never** sent to an
external search service. Exposed additively at **`GET /search?q=&kind=&limit=`**
(`app/search/router.py`, gated by `require_case_read`); existing rich list
endpoints (which use the retained AWS FTS for local/analytics richness) are
untouched. Offline search checks: 7/7 (case/person/evidence hits, kind filter,
limit, empty-query, backend reported).

## 7. Private Stratus buckets + quarantine + hash lineage (item 7 — IMPLEMENTED)

`infra/catalyst/stratus/buckets.json`: three PRIVATE, versioned buckets
(evidence / import / report) with lifecycle + short-expiry exact-object presigned
access. Evidence uploads land in `evidence/quarantine/` and are promoted to
`available/` only after the isolated size/type/hash + malware scan passes (a
security control that extracts no semantic content and triggers no predictions).
For every object, SHA-256 + size + MIME + object key + version + lineage are
recorded in Data Store — never the bytes through the API or logs.

## 8. Evidence fixtures S3 → Stratus (item 8 — IMPLEMENTED; commit HELD)

**New** `infra/catalyst/stratus/copy_fixtures_to_stratus.py` copies the Prompt 5
golden synthetic fixtures into the evidence bucket `quarantine/` prefix, verifies
SHA-256 after transfer, parses lineage from the fixture name
(`case<id>_<SYN-EV-…>`), and records an idempotent `EvidenceObject`
(`ExternalID = evobj:<sha256>`, quarantine state, scan pending). **Dry-run
verified against the real local fixtures**: 12/12 objects hashed + recorded;
cross-platform MIME (`.csv → text/csv`, etc.). Objects are never auto-promoted.
The `--commit` transfer to Catalyst Stratus is HELD. S3 remains only a temporary
SageMaker/Batch I/O copy; Stratus is the object source of truth.

## 9. NoSQL + Cache scope (items 9, 10 — DONE)

`app/nosql.py` + `nosql/segments.json`: only `UiPreferences` / `Presence`
(+ reserved `BoardLayout`/`FeedEnvelope`); any other segment is rejected — never
a duplicate of authoritative Data Store records. `app/cache.py` +
`cache/namespaces.json`: only bounded-TTL `idempotency` / `ratelimit` / `nonce` /
`lookup`; never a system of record.

## 10. One-way analytics boundary + cutover contract (items 11, 12 — DONE)

**New** `infra/catalyst/ds-import/CUTOVER.md` states the explicit contract:
bootstrap AWS→Catalyst (export → upsert-by-ExternalID → Stratus object copy →
reconcile); after cutover all new input is written to Data Store/Stratus first;
Catalyst→AWS is **analytics-only** through the signed adapter (Data Store/Stratus
event → Signals/Event Function or scheduled export → protected AWS adapter →
model store), and validated/versioned results are written back **as new records**
keyed by ExternalID + source version — never competing edits. No two-way row
replication; no last-write-wins.

## 11. Reconciliation + repeatable rebuild (item 12 — DONE, real run)

**New** `infra/catalyst/ds-import/reconcile.py` runs count / content-hash /
mapping-version parity + referential relationship checks (every case-scoped row
resolves to an exported Case; `CasePartyRole` person/org refs resolve) + dev-cap,
writing `serving-export/_reconcile-report.json` (non-zero exit on a hard failure
= CI/cron gate; wired to the disabled `cron_reconcile`). **Executed** on the real
export: **106 tables, 0 hard + 0 soft failures, 0 dangling person refs**. Rebuild
= re-run export then re-import; upsert-by-ExternalID makes it idempotent and
reproducible (`MAPPING_VERSION`).

## 12. Verification evidence

- Python diagnostics clean: `export_serving_subset.py`, `reconcile.py`,
  `copy_fixtures_to_stratus.py`, `datastore/search.py`, `search/router.py`,
  `main.py`. JSON valid; `/search` route registered.
- Real read-only export: 106 tables / 86,472 rows / 1,500 linked cases.
- Reconciliation: 0 hard + 0 soft failures on the real export.
- Fixture copy dry-run: 12/12 verified against real local bytes.
- Offline unit checks: export transform 9/9, metadata search 7/7, importer
  dry-run + commit (in-memory).
- No committed test files added (per the task constraint); targeted verification
  used throughout. `serving-export/` + fixture-copy report are git-ignored.

## 13. Held cloud steps (ordered; run only with go-ahead)

1. `export_serving_subset.py --all --target-cases <N>` (read-only; already
   proven) → refresh `serving-export/`.
2. For each table: `catalyst ds:import serving-export/<Table>.csv --config
   configs/<Table>.import.json` (the exporter already writes the CSV with the
   ExternalID column). Capture job ids + rejects.
3. `copy_fixtures_to_stratus.py --commit` (evidence bucket must exist;
   `DRISHTI_USE_CATALYST_STRATUS=true`).
4. `reconcile.py --against-datastore` → expect target ≥ source per table.

## 14. Honest gaps / limitations

- **Financial second-level scoping**: `FinancialTransaction`/`FinancialAccount`
  are capped whole (not scoped through `AccountID → CaseMasterID`); acceptable
  for a bounded demo subset and surfaced by reconciliation. Case + person/org
  dimensions are fully linked.
- **Live writes not executed**: `ds:import` into Data Store and the Stratus
  object copy are credit-spending and HELD; both offline equivalents are verified
  against the real data / fixtures.
