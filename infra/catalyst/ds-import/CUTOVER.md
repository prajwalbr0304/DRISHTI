# Bootstrap / cutover + analytics sync boundary (Prompt 14 Part E, items 11 + 12)

This is the explicit, one-way contract between the **Catalyst serving layer**
(Data Store + Stratus — the deployed operational system of record) and the
**retained AWS corpus** (RDS + S3 — history, feature engineering, GPU analytics).
There is **no uncontrolled two-way replication and no last-write-wins** anywhere.

## Roles

| Store | Role after cutover |
|---|---|
| **Catalyst Data Store** | Deployed operational relational records + full-text search. Source of truth for application input. |
| **Catalyst Stratus** | Application object system of record: evidence, import staging, reports, board/disaster exports. |
| **Catalyst NoSQL / Cache** | Semi-structured/ephemeral state / bounded-TTL only. Never authoritative. |
| **AWS RDS (retained)** | Full historical/analytics corpus; offline migration source; read-only analytics adapter. Never required by the operational CRUD path. |
| **AWS S3 (retained)** | Temporary SageMaker/AWS Batch model I/O copies only. |

## Bootstrap (before cutover) — one-way AWS -> Catalyst

1. **Export** the curated, referentially-linked serving subset (read-only) from
   AWS RDS: `python export_serving_subset.py --all --target-cases <1000-5000>`
   → `serving-export/<Table>.export.jsonl` + `_export-report.json`
   (per-table counts + content SHA-256). Golden seed cases first, then a
   deterministic fill; case-scoped children FK-scoped to the seed; person/org
   entity-scoped to those the seed cases reference; ≤ 5,000 rows/table (dev cap).
   Excluded/sensitive columns dropped; synthetic labels + lineage preserved.
2. **Import** by idempotent upsert on `ExternalID`
   (`catalyst ds:import --config configs/<Table>.import.json` with
   `operation:upsert, find_by:ExternalID`, or the offline
   `import_serving_subset.py --commit`). Capture job ids / row counts / rejects.
3. **Copy objects** S3/local → Stratus (private evidence bucket, `quarantine/`
   prefix): `python ../stratus/copy_fixtures_to_stratus.py --commit`. Verify
   SHA-256; record object key/version/size/MIME/hash + lineage in Data Store as
   `EvidenceObject`. Objects stay **quarantined** until the isolated
   size/type/hash + malware scan passes.
4. **Reconcile**: `python reconcile.py --against-datastore` — count / content-hash
   / mapping-version parity + referential relationship checks (every case-scoped
   row resolves to an exported Case; `CasePartyRole` person/org refs resolve).

## Cutover

- After cutover, **all new application input is written to Data Store / Stratus
  first** (the deployed CRUD path never requires `DATABASE_URL`).
- AWS RDS is demoted to a read-only analytics adapter; no operational endpoint
  depends on it.

## One-way analytics synchronization boundary (item 11)

```
Data Store / Stratus change
   -> Signals / Event Function  (or a scheduled export)
   -> protected AWS adapter (signed, server-side; app/predict/adapter.py)
   -> AWS analytics / model store (feature store, GPU inference)
   -> validated, versioned results returned through the adapter
   -> written back to Data Store as NEW result records (PredictionResult,
      ForecastResult, GraphEdge projections, ...), keyed by ExternalID +
      source version — NEVER as competing edits to the operational input.
```

- Only **validated / versioned feature snapshots or analytics projections** are
  sent to AWS, keyed by `ExternalID` and source version hash.
- AWS returns model / geospatial results as **new records**, not edits to the
  source input. The operational record and the analytics result never fight over
  the same row.
- The heavy analytics graph / vector index / GPU models stay in AWS; only a
  curated, reviewed **UI projection** is imported to Data Store
  (`UI_PROJECTION` disposition in `mapping.py`).

## Reconciliation + repeatable rebuild (item 12)

- **Scheduled reconciliation**: `reconcile.py` runs count / hash / version +
  relationship checks and writes `serving-export/_reconcile-report.json`
  (non-zero exit on a hard failure → CI/cron gate). Wired to the
  `cron_reconcile` Catalyst cron (disabled until `DRISHTI_RECONCILE_ENABLED`).
- **Repeatable rebuild**: re-run `export_serving_subset.py` then re-import.
  Because every write is an **upsert by `ExternalID`**, a rebuild converges to
  the same serving subset with no duplicates and no manual cleanup. The mapping
  is versioned (`MAPPING_VERSION`) so a rebuild is reproducible and auditable.

## Hard invariants

- One-way AWS → Catalyst bootstrap; Catalyst → AWS is analytics-only via the
  signed adapter, results-back-as-new-records.
- No two-way row replication. No last-write-wins conflict resolution.
- No credentials or real PII ever imported (protected attributes are
  `NOT_IMPORTED`; sensitive columns are dropped). Synthetic labels + lineage
  preserved. Secrets never printed.
