# PHASE 10 REPORT — Feature schemas, snapshots, labels, and prediction governance

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`ap-south-1`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> The safe bridge between verified inputs and any model. A feature is defined,
> classified and approved once (`FeatureDefinition`), grouped into a versioned,
> approvable `FeatureSchemaVersion`, and materialised into an **immutable**
> `FeatureSnapshot` computed strictly from pre-cutoff canonical records. A
> `PredictionRequest` binds an **approved** `ModelVersion` to a snapshot whose
> feature schema matches the model's (strict compatibility); a `PredictionResult`
> carries an explanation, limitations and expiry; a mandatory `PredictionReview`
> records the human decision. Labels come only from verified outcomes after the
> cutoff. Predictions are aggregate decision-support — nothing here operationalises
> the synthetic offender-risk labels, and no protected attribute enters a
> prediction schema.

---

## 1. Outcome summary

The Phase-10 **data contract** was already created by migration 008 and populated
by the datagen (feature/label tables + one governed prediction demo). This phase
built the missing **service, API and UI** on top of it, plus DB-level snapshot
immutability, and verified the governance guarantees end-to-end.

| Definition of Done | Result |
|---|---|
| Every prediction is tied to an immutable feature snapshot | `PredictionRequest`/`PredictionResult` reference a `FeatureSnapshot`; migration 017 adds a trigger that blocks any UPDATE of a snapshot's value/hash/schema/subject/cutoff columns and blocks DELETE (only supersession + quality/stale audit columns may change). The builder writes each snapshot once with a SHA-256 content hash. Verified by tests (immutability trigger + reproducible hash). |
| New inputs do not affect a model until explicitly included in an approved schema/model version | The builder refuses a draft/retired schema (`SchemaNotApproved`); `create_request` refuses an unapproved model (`ModelNotApproved`) and a snapshot whose `FeatureSchemaVersionID` ≠ the model's (`SchemaMismatch`). New canonical rows change nothing until a new approved schema/snapshot includes them. Verified by tests. |
| Labels and observation windows are leakage-safe | `OutcomeLabel` enforces `LabelWindowStart >= ObservationCutoff` (DB CHECK); the builder reads only `CrimeRegisteredDate <= cutoff`; `list_labels` reports `leakage_safe` (0 offending rows). Verified by tests. |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/017_feature_snapshot_immutability.sql` — additive + idempotent
  (applied twice, no error). Adds staleness/audit columns
  (`FeatureSnapshot.StaleReason/SupersededAt/BuiltByActor`,
  `PredictionResult.StaleReason/StaleAt`); a `fn_featuresnapshot_immutable()`
  trigger (`BEFORE UPDATE OR DELETE`) enforcing snapshot immutability; a partial
  index `idx_featuresnapshot_live` for the staleness sweep; re-asserts RLS
  disabled (`fn_disable_rls_all_app()` / `fn_assert_rls_disabled()`).
  (All eight governance tables + the `ModelVersion` governance columns already
  exist from migration 008 — not recreated.)

### New backend module `services/ml/app/governance/`
- `__init__.py`
- `builder.py` — the leakage-safe feature-snapshot builder: loads an **approved**
  schema, blocks protected/restricted features (allow-list empty for the
  hackathon), computes per-district aggregates strictly from pre-cutoff canonical
  cases (`CaseMaster` ⋈ `Unit` → `District`, only rows with a current
  `CaseVersion`), records source system + observation cutoff + pre-cutoff count in
  `SourceVersions`, writes an immutable snapshot with a deterministic SHA-256 hash.
- `service.py` — registry reads; the prediction state machine (`_create_request`
  idempotent + compatibility checks → `_run_request` queued→running→completed →
  `_review_result` accept/override/reject); `_invalidate_for_subject` (stale
  sweep); `_rollback_model`; `list_labels` (with leakage self-check);
  `get_prediction_detail` (assembles request+result+reviews+snapshot+model + an
  `AiResult`). A transparent rule-based **area** baseline `_infer` produces the
  aggregate output (not a person-level judgement; the trained models arrive in
  later phases).
- `schemas.py` — typed pydantic request/response models.
- `router.py` — 13 routes under `/governance` (below).

### Modified backend
- `services/ml/app/main.py` — register `governance_router`.

### New / modified frontend `web/src/`
- `api/types.ts` — appended `Gov*` types (1:1 with the governance schemas).
- `api/endpoints/governance.ts` (new) — `governanceApi` client; registered as
  `api.governance` in `api/index.ts`.
- `routes/governance/GovernanceRegistry.tsx` (new) — tabbed workspace shell +
  synthetic-demo badge.
- `routes/governance/panels.tsx` (new) — Registry (feature catalogue + schema
  versions with a protected/no-protected badge + governed models), Feature
  snapshots (build form + list with data-as-of / quality / hash), Predictions
  (queue + build/run/review, stale/superseded banner, explanation + source
  versions + limitations + `AiResult`), and a leakage-safe Labels panel.
- `App.tsx` — `/governance` (open) route + `/admin` now renders the governance
  registry (super-admin), replacing the placeholder.
- `routes/analytics/Analytics.tsx` — a "Model governance" link in the header.

### New tests
- `services/ml/tests/test_governance.py` (11 tests).
- `web/src/routes/governance/GovernanceRegistry.test.tsx` (1 test).

### Datagen
- No change required (the Phase-10 prompt asks only for the report). The
  governance data is already seeded reproducibly by `datagen/labels.py`
  (`FeatureDefinition`/`FeatureSchemaVersion`/`FeatureSnapshot`/
  `TrainingDatasetSnapshot`/`OutcomeLabel`) and `datagen/loader.py`
  `seed_governed_model_demo` (a governed `ModelVersion` + `PredictionRequest`/
  `Result`/`Review`). Migration 017 (like 010–016) is applied via
  `python -m app.batch apply-sql`; `generate_v2 --migrate` applies 005–009.

---

## 3. Database objects / endpoints / screens

### Database (migration 017)
- Function + trigger: `fn_featuresnapshot_immutable()` / `trg_featuresnapshot_immutable`.
- Columns: `FeatureSnapshot.StaleReason`, `SupersededAt`, `BuiltByActor`;
  `PredictionResult.StaleReason`, `StaleAt`.
- Index: `idx_featuresnapshot_live` (partial, live snapshots by subject).

### API endpoints (prefix `/governance`, 13)
Reads (open — aggregate governance metadata, no PII): `GET /features`,
`GET /schemas`, `GET /models`, `GET /snapshots`, `GET /labels`,
`GET /predictions`, `GET /predictions/{request_id}`.
Writes (governance role + localhost + synthetic-DB guard): `POST /snapshots/build`,
`POST /snapshots/invalidate`, `POST /predictions`, `POST /predictions/{id}/run`,
`POST /predictions/{id}/review`, `POST /models/{id}/rollback`.

Role gates: build / create / run need a governance role
(`analyst|investigator|supervisor|super_admin`); invalidate / review / rollback
need a supervisor (`supervisor|super_admin`). All writes also require the
hackathon guard (localhost + `synthetic_meta.app_environment=synthetic_hackathon`).

### Screens
- **Model governance** (`/governance`, and the Admin destination) — tabs:
  Registry (feature catalogue with sensitivity + a protected-free guarantee per
  schema, governed model versions with digests + schema binding), Feature
  snapshots (build one + list with the observation cutoff as "data as-of"),
  Predictions (job-status queue → run → review, with a stale/superseded banner,
  the explanation, source versions and limitations), and Labels (leakage-safe
  badge + train/test/geo_holdout split counts).

---

## 4. Governance guarantees enforced

1. **Approved-schema-only build** — a snapshot can only be built from an
   `approved` `FeatureSchemaVersion`; a draft/retired schema is refused.
2. **Protected-feature exclusion** — the builder refuses any schema containing a
   `protected`/`restricted` feature unless its task is on the (empty) reviewed
   aggregate allow-list. No protected attribute reaches a snapshot.
3. **Strict pre-cutoff features** — features are computed only from canonical
   records with `CrimeRegisteredDate <= observation_cutoff`; post-cutoff rows
   (and outcome labels) cannot leak in.
4. **Immutable, hashed snapshots** — value/provenance/hash columns are frozen by
   a DB trigger; the SHA-256 content hash makes each snapshot reproducible.
5. **Strict model↔schema compatibility** — a request needs an `approved` model
   whose `FeatureSchemaVersionID` equals the snapshot's.
6. **Idempotent requests** — a repeated `IdempotencyKey` (or the derived
   `auto:model:snapshot:kind` key) returns the same request.
7. **State machine** — `queued → running → completed`, `→ reviewed|rejected`, and
   `→ stale` when the source is corrected; results carry an `ExpiresAt`.
8. **Correction invalidation** — an accepted canonical edit marks the subject's
   live snapshots stale + their results/requests stale (no in-place edit).
9. **Mandatory human review** — every result is `accept|override|reject`d;
   override/reject records a reason; the decision is audited
   (`audit_logs.action='prediction.review'`).

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `017_feature_snapshot_immutability.sql` twice (`python -m app.batch apply-sql`) | PASS — trigger + columns + index created; RLS-disabled asserted; idempotent (no error on re-run) |
| Read-only pre-audit (no secrets) | PASS — synthetic marker present; FeatureDefinition 4 (all normal + approved), FeatureSchemaVersion 1 (approved, 4 features), FeatureSnapshot 32, OutcomeLabel 32 (0 leaks; splits train 18 / test 7 / geo_holdout 7), PredictionRequest/Result/Review 1 each; ModelVersion 13 total (1 governed + schema-bound); 0 protected features in any approved schema; RLS off on all 8 tables |
| Immutability verification (rolled back) | PASS — forbidden UPDATE (mutate `Values`) blocked; allowed stale UPDATE ok; DELETE blocked |
| `python -m pytest tests/test_governance.py -q` | **11 passed** |
| `python -m pytest tests/test_governance.py tests/test_intake.py tests/test_geo_jurisdiction.py -q` | **49 passed** (no regression) |
| `npm run typecheck` (web) | PASS (tsc, 0 errors) |
| `npx vitest run` (web, full suite) | **40 passed** (14 files, incl. the new governance test) |
| `npm run build` (web) | PASS — 3587 modules transformed; dist emitted (pre-existing chunk-size warning only) |

### Backend test coverage (`test_governance.py`, 11)
Reproducible content hash; leakage-safe builder (monotonic pre-cutoff counts +
`n_pre` equals a direct pre-cutoff-only query); unapproved schema blocked;
protected feature blocked; snapshot immutability (trigger blocks a value UPDATE);
full prediction flow + idempotent request (same key → same request; run →
completed with a band + limitations; replay does not recompute); schema mismatch
rejected; unapproved model rejected; stale-after-correction blocks the run;
review writes a `PredictionReview` + flips the request to `reviewed` + an audit
row, and an override without a reason is refused; labels report `leakage_safe`
with splits partitioning the total.

---

## 6. Security and data-quality checks

- **RLS** stays disabled + NO FORCE (migration 017 re-asserts
  `fn_assert_rls_disabled()`; the 8 governance tables verified
  `relrowsecurity=false`). No RLS policies created.
- **API-only path**: every screen is React → FastAPI → PostgreSQL; no DB
  credentials or direct queries in the browser; no secrets printed in this phase.
- **Write guards**: governance writes require a governance role AND the localhost
  + synthetic-DB guard (`require_write_allowed`); review/invalidate/rollback are
  supervisory. Reads are open (aggregate governance metadata, no PII).
- **No protected attributes in prediction schemas**: enforced at build time
  (`ProtectedFeatureError`); the seeded catalogue is protected-free (verified 0
  protected/restricted in any approved schema).
- **Leakage-safe**: `OutcomeLabel` CHECK (`LabelWindowStart >= ObservationCutoff`)
  + strictly-pre-cutoff feature reads; 0 offending label rows.
- **No operationalised risk labels**: predictions are aggregate area forecasts via
  a transparent rule baseline; every result carries a decision-support
  limitations note and requires human review. No person-level automated decision.
- **Auditable**: snapshot builds, prediction requests/results and reviews all emit
  sanitised `audit_logs` rows (`model.run` / `prediction.review`).

---

## 7. Known limitations

1. **Baseline inference, not a trained model** — `_infer` is a transparent,
   rule-based aggregate area projection (a seasonal-naive blend) that proves the
   governed contract end-to-end. The actual forecasting/embedding/graph models
   arrive in Prompts 11–13 and will bind to these same schemas + snapshots.
2. **Builder subject scope** — the builder computes `area_district` aggregates
   (the seeded schema's subject). Other subject kinds (`area_unit`, `beat_window`,
   `case`) are accepted by the schema but not yet computed by this builder.
3. **No live 100k reload** — the governance data was seeded by the earlier
   datagen run; this phase added no data and reloaded nothing (mirrors Phases
   7–9). Migration 017's trigger does not affect the reload path (TRUNCATE/COPY
   bypass row triggers; INSERT is always allowed).
4. **Pre-existing full-suite failures (2), unrelated to Phase 10** — the
   data-dependent `test_geo::test_hotspots_written_and_active` and
   `test_geo::test_emerging_alerts_present` require batch-job outputs not
   materialised on this DB (documented in Phases 8–9). No governance/feature code
   is involved; the contract-audit does not inspect `/governance` routes.

---

## 8. Next-phase prerequisites (Prompt 11 — embeddings / similar cases / graph)

- New models (embeddings, similar-case, graph) must register a governed
  `ModelVersion` bound to an approved `FeatureSchemaVersion` and produce
  `PredictionRequest`/`Result` against immutable snapshots — the plumbing built
  here (`app/governance`) is the pattern to reuse.
- Any new feature must be added as an approved `FeatureDefinition` (protected
  attributes stay excluded) before it can affect a model.
- `TrainingDatasetSnapshot` + `OutcomeLabel` (leakage-safe, split-tagged) are the
  reproducible training inputs a real retraining pipeline (a separate approved
  step) will consume.
- Prompt 6 (OCR/extraction) remains **Deferred**.

---

## 9. Definition of Done — verification

- [x] Every prediction is tied to an immutable feature snapshot —
      `PredictionRequest`/`PredictionResult` → `FeatureSnapshot`; migration-017
      trigger enforces immutability (verified: UPDATE/DELETE blocked, reproducible
      hash).
- [x] New inputs do not affect a model until explicitly included in an approved
      schema/model version — approved-schema-only build, approved-model +
      schema-match request (verified: unapproved schema/model + mismatch all
      rejected).
- [x] Labels and observation windows are leakage-safe — `OutcomeLabel` CHECK +
      strictly-pre-cutoff builder (verified: 0 leaks; `leakage_safe` true).
