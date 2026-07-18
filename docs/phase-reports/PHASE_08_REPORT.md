# PHASE 08 REPORT — Digital/CDR/device/media and financial imports

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`ap-south-1`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> All imports are STRUCTURED CSV/JSON only — no OCR / speech-to-text / document
> extraction. A source file is uploaded as evidence; its structured rows are
> parsed into STAGING, dry-run reviewed, and only after an approved commit do they
> become canonical rows, each with a `SourceRecord` for provenance. Resolved
> phones/accounts/devices become CANDIDATE entity links that must be reviewed —
> never auto-confirmed. Money patterns are rule-based with explicit reason codes
> and a reviewer disposition; no communication/financial link implies guilt.

---

## 1. Outcome summary

Added a template-driven, staged, reviewable import pipeline for the digital
(CDR / chat / IP / device / GPS) and financial (bank transactions / account-KYC /
wallet-UPI) domains, plus rule-based, evidence-backed, reviewable money alerts.

| Definition of Done | Result |
|---|---|
| Digital and financial inputs load through staging/review/provenance | New `/imports` module: upload-as-evidence → template version → parse to `ImportStagingRow` (dry-run) → approve commit → one `SourceRecord` per canonical row → candidate `EvidenceEntityLink` for reviewed resolution. Idempotent, partial-error tolerant, with rollback + supersession. Verified by 19 tests. |
| Graph/money outputs are evidence-backed and reviewable | Committed comm/txn rows + `EvidenceEntityLink` are `candidate` until reviewed (accept/reject); `MoneyAlert` rows carry an explicit `ReasonCode`, the flagged `TransactionIDs`, contributing `SourceRecordIDs` and an `EvidenceItemID`, with a `MoneyAlertReview` disposition. No guilt implied (neutral wording). |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/015_digital_financial_imports.sql` — additive + idempotent
  (applied twice, no error). Adds `ImportTemplate`, `ImportTemplateVersion`,
  `ImportBatch`, `ImportStagingRow`, `MoneyAlert`, `MoneyAlertReview`; the
  `vw_entity_link_queue` view; provenance/version/currency/normalised-channel/
  reviewed-owner columns on `FinancialAccount`/`FinancialTransaction`, review
  columns on `TransactionLink`, and `ImportBatchID`/reviewer columns on
  `Device`/`DeviceArtifact`/`CommunicationEvent`/`LocationObservation`/
  `EvidenceEntityLink`; seeds 8 templates (9 versions — CDR has v1 + v2) and the
  `DIGITAL_IMPORT`/`FINANCIAL_IMPORT` source systems. Re-asserts RLS disabled +
  NO FORCE via `fn_disable_rls_all_app()` / `fn_assert_rls_disabled()`.

### New backend module `services/ml/app/imports/`
`__init__.py`, `templates.py` (type coercion, channel normalisation, canonical
entity-kind map), `parse.py` (dependency-free CSV/JSON parse + column mapping +
per-row validation + dedupe hashing — pure logic), `schemas.py` (typed
request/response models), `service.py` (batch create/dry-run, commit with
provenance + candidate resolution, rollback, supersession, account/transaction/
CDR/device views, entity-link queue + review), `analytics.py` (rule-based money
scan reusing the Phase-11 detectors → reason-coded `MoneyAlert` + disposition),
`router.py` (17 routes, prefix `/imports`). Registered in `services/ml/app/main.py`.

### Modified backend
- `services/ml/app/main.py` — register `imports_router`.

### Datagen generator enhancements (for future golden regenerations)
- `datagen/financial.py` — structuring now routes 6 sub-threshold "smurf"
  deposits into ONE hub (rule-detectable); added a multi-hop **layering** conduit
  chain; every account/transaction carries `Currency` / `NormalizedChannel` /
  `ReviewStatus` / `SyntheticReference` / `IsSynthetic` (registered columns +
  rows updated; arity verified offline).
- `datagen/build.py` — a financial case now draws `structuring | fan_in | layering`.
- `datagen/imports.py` (new) — sample CSVs per template + `seed_import_demo()`
  loader post-step that seeds golden STAGED batches (valid/rejected/duplicate rows).
- `datagen/loader.py` — `TRUNCATE_TABLES` extended with the four derived Phase-8
  tables (`ImportTemplate`/`ImportTemplateVersion` are migration-seeded reference
  and are PRESERVED).
- `generate_v2.py` — wires `seed_import_demo()` into the `--load-derived` step.

### New / modified frontend `web/src/`
- `api/endpoints/imports.ts` (new) wired into `api/index.ts` as `api.imports`;
  `api/types.ts` appended with `Imp*` types.
- New workspace `routes/imports/ImportsWorkspace.tsx` (tabbed) + `routes/imports/panels.tsx`
  (import inbox with dry-run/commit/rollback/error-download/column-mapping;
  reviewed entity-link queue; accounts + transactions; money alerts with
  scan + disposition).
- New case sub-page `routes/cases/subpages/DigitalPage.tsx` (CDR/device timeline +
  aggregate bar chart + per-case money alerts).
- `App.tsx` (route `/imports`), `routes/cases/CaseFile.tsx` (new "Digital &
  financial" sub-nav tab), `routes/intake/IntakeInbox.tsx` (header link to the
  imports workspace).

### New tests
- `services/ml/tests/test_imports.py` (19 tests).
- `web/src/routes/imports/imports.test.tsx` (2 tests).

---

## 3. Database objects / endpoints / screens

### Database (migration 015)
- New tables: `ImportTemplate`, `ImportTemplateVersion`, `ImportBatch`,
  `ImportStagingRow`, `MoneyAlert`, `MoneyAlertReview` (+ indexes, GIN on JSONB,
  updated-at triggers). New view `vw_entity_link_queue`.
- Additive columns: `FinancialAccount` (+`SourceRecordID`, `IngestionJobID`,
  `ImportBatchID`, `Version`, `SyntheticReference`, `Currency`,
  `OwnerCanonicalPersonID`, `CanonicalEntityID`, `OwnerReviewStatus`, `KycDetail`,
  `IsSynthetic`); `FinancialTransaction` (+`SourceRecordID`, `ImportBatchID`,
  `Version`, `SyntheticReference`, `Currency`, `NormalizedChannel`,
  `SupersededByTransactionID`, `ReviewStatus`, `IsSynthetic`); `TransactionLink`
  (+`ReviewStatus`, `SourceRecordID`, `ReviewedByActor`, `ReviewedAt`);
  `CommunicationEvent`/`Device`/`DeviceArtifact`/`LocationObservation` (+`ImportBatchID`);
  `CommunicationEvent`/`EvidenceEntityLink` (+`ReviewedByActor`, `ReviewedAt`).

### API endpoints (prefix `/imports`, 17)
Import pipeline (intake guards): `GET /templates`, `GET /batches`,
`POST /batches`, `GET /batches/{id}`, `GET /batches/{id}/rows`,
`POST /batches/{id}/commit`, `POST /batches/{id}/rollback`,
`POST /batches/{id}/supersede`, `GET /entity-links`,
`POST /entity-links/{id}/review`, `GET /cdr/timeline`, `GET /devices`.
Financial (money_trail permission): `GET /accounts`, `GET /transactions`,
`GET /money/alerts`, `POST /money/scan`, `POST /money/alerts/{id}/disposition`.

### Screens
- **Digital & financial imports** (`/imports`) — tabs: Import inbox (template
  pick → file upload → dry-run report with column mapping + valid/rejected/
  duplicate counts + error download → approve-commit → rollback), Entity-link
  review (accept/reject candidate links), Accounts & transactions, Money alerts
  (scan + reason/source/evidence + reviewer disposition). Policymaker blocked.
- **Case file → Digital & financial** sub-page — CDR/device timeline, by-type /
  by-day aggregates, imported devices + artifacts, and the case's money alerts.

---

## 4. Import workflow enforced (server-side)

1. **Upload source file as evidence** — a batch links (or creates) an
   `EvidenceItem` (+`EvidenceObject` with a real SHA-256 of the content) of type
   `digital_export` / `financial_dataset`.
2. **Select template/schema version** — a batch binds to an exact approved
   `ImportTemplateVersion`; an unapproved (draft) version is refused.
3. **Parse into staging only** — CSV/JSON → mapped canonical fields → typed
   coercion + required-field + self-transfer checks → per-row `staged/valid/
   rejected/duplicate` in `ImportStagingRow`. Nothing canonical is written.
4. **Dry-run report** — parsed/valid/rejected/duplicate counts, the effective
   column mapping, per-row errors, downloadable error rows.
5. **Approve commit** — supervisory role; one `SourceRecord` per committed row.
6. **Provenance** — every canonical row carries its `SourceRecordID`; the batch's
   `ImportBatchID` is stamped on every canonical row for lineage + rollback.
7. **Reviewed entity resolution** — phones/accounts/devices resolve to
   `CanonicalEntity` and produce **candidate** `EvidenceEntityLink`s (and
   `candidate` review state on comm events / transactions); confirmed only on review.
8. **Idempotency / retry / partial / rollback / supersession** — `IdempotencyKey`
   returns the same batch; re-committing a committed/partial batch is a no-op
   replay; rejected/duplicate rows never block valid rows (status `partial`);
   rollback deletes the batch's canonical rows and retracts its source records;
   supersession links an old batch to its replacement and rolls the old one back.

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `015_digital_financial_imports.sql` twice (`python -m app.batch apply-sql`) | PASS — 6 tables + view + columns + 8 templates/9 versions; RLS-disabled asserted (idempotent) |
| Read-only object verification | PASS — all objects present; `rls_enabled_tables = 0`; CDR template has 2 versions |
| `python -c "from app.main import app"` (route registration) | PASS — 17 `/imports` routes registered |
| `python -m pytest tests/test_imports.py -q` | **19 passed** (~23 s, incl. the slow money-scan test) |
| `python -m pytest -q -m "not slow"` (full backend) | 250 passed, 3 skipped, 9 failed — the 9 are pre-existing/unrelated (see §8) |
| `npm run typecheck` (web) | PASS (tsc, 0 errors) |
| `npm run test` (web, vitest) | **34 passed** (11 files, incl. new `imports.test.tsx`) |
| `npm run build` (web) | PASS (dist emitted; pre-existing chunk-size warning only) |
| datagen offline arity + 3-pattern check | PASS — FinancialAccount 11 / FinancialTransaction 15 / TransactionLink 5 cols; structuring/fan_in/layering all build |
| `seed_import_demo` SQL validated against live schema (rolled back) | PASS — 2 golden staged batches |

### Backend test coverage (`test_imports.py`, 19)
Pure parse/validate (valid/rejected/duplicate/bad-datetime/self-transfer);
structuring / fan-in / layering detector fixtures; template versions (CDR v1 vs
v2 use distinct source columns); malformed+duplicate+partial batch → `partial`
commit; idempotent retry (same `IdempotencyKey` → same batch); invalid template
(404) + unapproved draft version (422); commit-state guards (idempotent replay
for committed/partial, conflict after rollback); reviewed vs unreviewed graph
link (candidate → reviewed/rejected, never auto-confirmed); rollback (deletes
canonical rows + retracts sources); supersession (old→new link, old rolled back);
money scan writes reason-coded reviewable alerts + disposition transition; API
guards (templates list 8 domains; policymaker 403 on the pipeline; financial
views gated by `money_trail`; scan needs money **write**).

---

## 6. Datagen coverage (loaded synthetic fixture)

The live fixture was **not** reloaded in this phase (out of scope; mirrors Phase 7).
The generator was enhanced so a future golden regeneration carries Phase-8 fields
and all three money patterns. Current live counts of Phase-8-relevant tables:

| Object | Count | Note |
|---|---:|---|
| ImportTemplate | 8 | cdr / chat / ip_log / device_artifact / location / bank_txn / account_kyc / wallet_upi |
| ImportTemplateVersion | 9 | CDR has v1 + v2 (template-versioning demo) |
| ImportBatch / ImportStagingRow / MoneyAlert | 0 | populated by the API/UI (or `seed_import_demo` on a regen); tests roll back |
| Device / DeviceArtifact | 764 / 764 | existing digital fixture (now import-capable) |
| CommunicationEvent | 6,187 | CDR/chat/IP events (candidate/reviewed) |
| LocationObservation | 7,684 | GPS observations |
| FinancialAccount / FinancialTransaction | 9,360 / 10,977 | existing financial fixture |
| TransactionLink | 3,120 | reviewed case↔txn links |

Generator enhancements (`datagen/financial.py`, `datagen/imports.py`) broaden the
next golden regeneration: detectable structuring hubs, a layering conduit chain,
normalised currency/channel, and golden staged import batches per template.

---

## 7. Security and data-quality checks

- **RLS** stays disabled + NO FORCE (migration 015 re-asserts `fn_assert_rls_disabled()`;
  verified `rls_enabled_tables = 0`). No RLS policies created.
- **API-only data path**: every screen is React → FastAPI → PostgreSQL; the
  browser reads file text and posts it to FastAPI (server parses). No DB
  credentials or direct queries in the browser.
- **Write guards**: batch create needs an investigating/registering role +
  localhost + synthetic-DB marker; commit/rollback/link-review need a supervisory
  role; financial views are gated by the `money_trail` permission and the money
  scan/disposition need `money_trail` **write** (policymaker denied throughout — tested).
- **No raw identifiers in logs**: `audit.record` sanitises the detail payload
  (phone/account/msisdn/etc. keys dropped, strings truncated); imports/commits/
  rollbacks/entity-changes/model-runs/reviews all emit sanitised `audit_logs` rows.
- **Provenance**: every committed canonical row has a `SourceRecord` and an
  `ImportBatchID`; money alerts carry transaction + source-record + evidence ids.
- **Data quality**: invalid rows stay in `ImportStagingRow` as `rejected`/
  `duplicate` and never reach canonical tables; dry-run surfaces them; a file
  upload never triggers a prediction.
- **No guilt implication**: money-alert messages are deliberately neutral
  ("review required; a pattern is not by itself evidence of an offence"); graph
  links stay candidate until a human reviews them.
- **No OCR/extraction**: structured CSV/JSON only; file bytes are hashed and
  referenced, never parsed for content.

---

## 8. Known limitations

1. **No live 100k reload** — the generator enhancements (detectable structuring,
   layering, currency/channel, staged import demo) apply on the next golden
   regeneration; the existing shared fixture was not reloaded (out of scope, and
   avoids replacing shared synthetic data). The import pipeline itself is fully
   exercised by the API/UI and the 19 tests.
2. **Money scan on the current live fixture** finds few structuring hubs because
   the pre-existing v2 financial data splits sub-threshold deposits across two
   mule accounts (below the rule's per-hub count). Alerts surface immediately for
   **imported** bank data and for any regenerated fixture (structuring now targets
   one hub). The money-scan test injects a deterministic hub to prove the path.
3. **Pre-existing full-suite failures (9), unrelated to Phase 8** — verified not
   caused by this phase (my backend changes are the new `app/imports/` module plus
   one router registration; no geo/analytics/risk/graph/money code changed):
   - `test_explain::test_contract_audit` — the 2 non-conforming routes are
     `/geo/boundaries/{level}` and `/geo/sho-regions` (prior-phase geo routes; the
     audit deliberately does not inspect `/imports`; it is data-independent).
   - `test_geo` (hotspots/emerging_alerts), `test_graph_hidden` (feed), `test_risk`
     (offender/by_accused), `test_money` (unified/flagged), `test_analytics`
     (socioeconomic) — all require batch-job outputs (CrimeHotspot / AlertHistory /
     drishti_hidden_associations / CrimeRiskScore / flagged transactions) or a
     populated `FinancialAccount.EntityID` (the v2 datagen leaves it null) that do
     not exist on this freshly-migrated AWS DB (those batch jobs were not run).
4. **IP-log endpoints** are stored as endpoint strings only (IP is not a
   `CanonicalEntity` kind), so IP imports do not create candidate entity links —
   by design.
5. **Import content** is posted through the API body (bounded by the 2 MB request
   cap), which suits synthetic hackathon batch sizes; very large files would need
   the pre-signed-S3 path (deferred).

---

## 9. Next-phase prerequisites (Prompt 9 — jurisdiction/geography)

- `LocationObservation` rows imported here carry a `geom` and a best-effort
  `DistrictID`; Prompt 9's versioned jurisdiction boundaries + containment
  validation should be applied to imported location observations too.
- Committed digital/financial canonical rows + candidate `EvidenceEntityLink`s are
  the evidence-backed inputs Prompt 10's `FeatureSnapshot` builder may consume —
  only after review promotes them (candidate → reviewed).
- `MoneyAlert` + `MoneyAlertReview` (reviewer disposition) are the reviewable,
  reason-coded money outputs Prompt 11 can rebuild from verified transactions.
- Prompt 6 (OCR/extraction) remains **Deferred**.

---

## 10. Definition of Done — verification

- [x] Digital and financial inputs load through staging/review/provenance
      (`ImportBatch`/`ImportStagingRow` staging → dry-run → approve commit → one
      `SourceRecord` per canonical row + candidate `EvidenceEntityLink` review;
      idempotent, partial, rollback, supersession — 19 tests pass).
- [x] Graph/money outputs are evidence-backed and reviewable (candidate entity
      links with source provenance + accept/reject; reason-coded `MoneyAlert`
      with transaction/source/evidence provenance + `MoneyAlertReview`
      disposition; neutral wording — no guilt implied).
