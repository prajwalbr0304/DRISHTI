# PHASE 01 REPORT — Datagen v2, schema completion, and live development Supabase load

Status: **Complete**
Date: 2026-07-16
Target: development Supabase project referenced by `.env` (`DATABASE_URL`), PostgreSQL 17.6, PostGIS/pgvector/pg_trgm/pgRouting enabled.
Mode: synthetic hackathon demo data only (`app_environment = synthetic_hackathon`).

> No secret values (database password, Supabase keys, tokens) are printed, logged,
> committed, or reproduced anywhere in this report or the tooling. Every DB access
> resolves `DATABASE_URL` at runtime and redacts the host in logs.

---

## 1. Outcome summary

Rebuilt the synthetic-data foundation as a scenario-driven generator (Datagen v2)
with **stable canonical identity**, category-specific case lifecycles, the
structured digital input domains, digital-evidence fixtures with manual metadata
and real SHA-256, versioned jurisdiction geography, leakage-safe outcome labels,
and a safe, gated loader. Applied additive migrations 005–009 to the development
Supabase and loaded both the **golden** fixture and the **100,000-case** fixture,
each passing every integrity gate with **zero failures**.

Every defect called out in the live audit (roadmap §2) is fixed and verified:

| Audit defect (before) | After (verified in the live DB) |
|---|---|
| Accused had 304,278 rows but only **26** distinct PersonID | **16,246** distinct `CanonicalPersonID` linked from Accused; **14,069** canonical persons reused across >1 case |
| 15,000 EntityGraph person nodes, **0** valid links | **205,610** person nodes, **0** without a `CanonicalEntityID` FK |
| All 69,206 NetworkEdge rows had null provenance | **0** edges without provenance (2,141 verified + 270 explicit synthetic-unverified) |
| Case linking fell back to duplicate names | All case parties link via `CasePartyRole → CanonicalPersonID`; **0** name-based identity links |
| 6,732 cases outside Karnataka, 17,653 outside district | **0** out-of-state, **0** out-of-district (full scan of 100k canonical `CaseVersion` coordinates) |
| 5,222 Charge Sheeted cases lacked ChargesheetDetails | **0** Charge Sheeted cases without a chargesheet row + prerequisite event |
| 1,000 Missing Person cases had chargesheets | **0** missing-person/UDR/NCR/PAR cases with a chargesheet (unless an explicit conversion event) |
| Every case had a CourtID | **81,217 / 100,000** cases have no court (court is now an event/result) |
| CaseEvidence, audit_logs, SavedQuery empty | Evidence platform populated (8,015 items / 8,023 objects w/ hashes); audit fixtures present |
| Circular/self-referential risk labels | Aggregate `OutcomeLabel` derived only from post-cutoff outcomes; legacy individual-risk tables cleared and **not** rerun |

---

## 2. Files and migrations changed

### New SQL migrations (`services/ml/sql/`)
- `005_security_rls_audit.sql` — synthetic-environment marker (`synthetic_meta`),
  `SyntheticDataRun` run metadata, `DemoActor`, `vw_audit_events`, and the
  **reusable RLS-disable + verification functions** (`fn_drishti_app_tables()`,
  `fn_disable_rls_all_app()`, `fn_assert_rls_disabled()`). No RLS policies.
- `006_ingestion_evidence.sql` — `SourceSystem`, `SourceRecord`, `IngestionJob`,
  `IngestionRecord`, `DataQualityIssue`, `EvidenceItem`, `EvidenceObject`,
  `EvidenceVersion`, `EvidenceCaseLink`, `EvidenceActivityEvent`.
- `007_identity_case_workflow.sql` — `CanonicalPerson/Organisation/Entity`,
  `PersonAlias/Identifier/Contact/Address`, `EntityResolutionCandidate`,
  `EntityMergeHistory`, `CasePartyRole`, `CaseSource`, `CaseVersion` (canonical
  coordinates + generated geom), `CaseEvent`, `CaseCategoryWorkflow`,
  `EvidenceEntityLink`, `Statement/StatementVersion`, `Seizure`, `PropertyItem`,
  `Device`, `DeviceArtifact`, `CommunicationEvent`, `LocationObservation`,
  `DigitalImportBatch`, `CourtEvent`, `BailEvent`, `CaseDisposition`,
  `OutcomeObservation`; additive canonical FK columns on `Accused`, `Victim`,
  `ComplainantDetails`, `EntityGraph`, `GangMembership`, `NetworkEdge`; the
  `vw_case_parties` compatibility view.
- `008_feature_prediction_governance.sql` — `FeatureDefinition`,
  `FeatureSchemaVersion`, `FeatureSnapshot`, `TrainingDatasetSnapshot`,
  `OutcomeLabel` (leakage CHECK), `PredictionRequest`, `PredictionResult`,
  `PredictionReview`; extends `ModelVersion` with artifact/image digest,
  dataset/feature-schema, approval, evaluation report, environment, rollback.
- `009_jurisdiction_external_events.sql` — `JurisdictionBoundary`, `UnitLocation`
  (versioned + GiST), `ExternalSourceVersion`, `HolidayCalendar`, `PublicEvent`,
  `AreaContextObservation`; containment helpers `fn_point_in_state`,
  `fn_point_in_district`, and `vw_caseversion_containment`.

All migrations are additive, idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, guarded `DO` blocks), and
each ends by disabling RLS + NO FORCE on its tables and re-running the global
RLS-disabled verification. Legacy tables are preserved.

### New datagen modules (`datagen/`)
`v2common.py`, `scenario_registry.py`, `identity.py`, `people_roles.py`,
`case_events.py`, `evidence.py`, `statements.py`, `property_seizure.py`,
`digital.py`, `financial.py`, `court_outcomes.py`, `external_context.py`,
`labels.py`, `quality_scenarios.py`, `validation.py`, `build.py`, `preflight.py`,
`loader.py`, `verify_v2.py`, `dbsize.py`, `reclaim.py`.

### New CLI
`generate_v2.py` (repo root) — preflight → build → validate → migrate → backup →
truncate → load → repair identities → DB-side integrity checks → record run.

### Modified (additively, no behavioural regression)
- `datagen/db.py` — added the `Arr` COPY wrapper for `text[]` columns.
- `datagen/reference.py` — appended 6 v2 lifecycle statuses to `CASE_STATUSES`
  (existing indices unchanged; legacy path verified still self-consistent).
- `.gitignore` — ignore `datagen/fixtures/` (generated evidence files/manifests/markers).

Fixture files (gitignored): `datagen/fixtures/<run>/` holds the small already-digital
evidence files, `evidence_manifest.json`, and the pre-reload backup markers.

---

## 3. Commands run and results

| Command | Result |
|---|---|
| `python -m datagen.geo.selftest` | PASS — 32 districts / 230 taluks; 0/3000 incidents out-of-state; 0/150 stations out-of-district |
| `python -m datagen.preflight` | Read-only baseline reproduced (no secrets/rows printed) |
| `python generate_v2.py --mode golden --validate-only` | PASS — 0 failures across all gates + scenario minimums |
| `python generate_v2.py --migrate --no-build` | Migrations 005–009 applied cleanly (public user tables 59 → 114) |
| `python generate_v2.py --mode golden --truncate --confirm-synthetic-dev-target --write-fixture-files --load-derived --run-id golden-001` | Loaded 136,656 rows / 61 tables; all 11 DB-side checks PASS |
| `python generate_v2.py --mode performance --firs 100000 --truncate --confirm-synthetic-dev-target --load-derived --run-id perf-001` | Built 100k in ~145s; validation PASS; loaded **2,978,813** rows / 61 tables; all DB-side checks PASS |
| `python -m datagen.verify_v2` | Final read-only verification — all DoD proofs (see §5) |
| `python generate.py --dry-run 500` | Legacy generator still self-consistent (no regression) |

Note on the disk event: the first attempt at a *fully rich* 100k dataset exceeded
the dev Supabase disk (~772 MB written before `DiskFull`), which left dead-tuple
bloat and flipped the project read-only. Recovery: `python -m datagen.reclaim`
truncated the bloated (logically empty) tables biggest-first, reclaiming space
(772 MB → 32 MB). The generator now runs statistical/performance modes in a
**lean** profile (trimmed per-case child volumes; golden stays fully rich) so a
100k-case fixture fits comfortably (final DB size **727 MB**) while every
integrity gate still holds.

---

## 4. Row counts by domain (100k performance fixture, live)

Operational: CaseMaster 100,000 · Accused 164,860 · Victim 71,602 ·
ComplainantDetails 100,000 · ArrestSurrender 72,762 · ChargesheetDetails 37,147 ·
ActSectionAssociation 172,372.

Canonical identity: CanonicalPerson 210,883 · CanonicalOrganisation 60 ·
CanonicalEntity 223,161 · CasePartyRole 374,272 · PersonAlias 20 ·
EntityResolutionCandidate 22 · EntityMergeHistory 13.

Case workflow: CaseSource 200,000 · CaseVersion 100,000 · CaseEvent 386,987 ·
CaseCategoryWorkflow 36.

Evidence: EvidenceItem 8,015 · EvidenceObject 8,023 · EvidenceVersion 8,007 ·
EvidenceCaseLink 8,007 · EvidenceActivityEvent 8,007 · EvidenceEntityLink 5,276.

Domains: Statement 9,894 · StatementVersion 11,090 · Seizure 13,641 ·
PropertyItem 13,765 · Device 764 · CommunicationEvent 6,187 ·
LocationObservation 7,684 · FinancialAccount 9,360 · FinancialTransaction 10,977 ·
TransactionLink 3,120 · CourtEvent 64,391 · BailEvent 27,196 ·
CaseDisposition 28,309 · OutcomeObservation 28,309.

Jurisdiction/context: JurisdictionBoundary 1,033 (1 state + 32 district + 1,000 SHO) ·
UnitLocation 1,000 · ExternalSourceVersion 4 · HolidayCalendar 30 · PublicEvent 6 ·
AreaContextObservation 160.

Features/prediction: FeatureDefinition 4 · FeatureSchemaVersion 1 ·
FeatureSnapshot 32 · TrainingDatasetSnapshot 1 · OutcomeLabel 32 ·
PredictionRequest 1 · PredictionResult 1 · PredictionReview 1.

Graph: EntityGraph 205,670 · NetworkEdge 2,411 · GangMembership 524.

Staging/quality/audit: SourceSystem 4 · SourceRecord 100,056 · IngestionJob 8 ·
IngestionRecord 24 · DataQualityIssue 56 · audit_logs 12.

Golden fixture (run `golden-001`): 2,000 cases / 136,656 rows across 61 tables,
with every named scenario minimum in `scenario_registry.GOLDEN_SCENARIOS` met.

---

## 5. Integrity gates (all zero failures)

In-memory (`datagen/validation.py`, run pre-load on the full fixture) — 32 gates,
0 failures for both golden and 100k, including: duplicate CrimeNo/source key,
orphan FKs (15+ relationships), unstable canonical identity, name-based identity
links, unlinked graph-person nodes, unprovenanced graph edges, invalid category
transitions, chargesheet-without-prerequisite, invalid missing-person/UDR
lifecycle, out-of-state/out-of-jurisdiction canonical coordinates, evidence object
without hash/version/provenance, outcome label before cutoff, feature-snapshot
cutoff/hash, protected feature in schema, and (golden) scenario-minimum coverage.

DB-side (`datagen/loader.py::db_integrity_checks`, run post-load) — all `0`:
`orphan_casepartyrole_case`, `orphan_caseversion_case`, `accused_without_canonical`,
`graph_person_without_canonical`, `edge_without_provenance`,
`chargesheeted_without_row`, `evidence_object_without_hash`, `outcome_label_leak`,
`caseversion_out_of_state`, `caseversion_out_of_district`, `rls_enabled_app_tables`.

Final full-scan verification (`datagen/verify_v2.py`) confirms 0 out-of-state,
0 out-of-district over all 100,000 current `CaseVersion` coordinates.

---

## 6. Security and data-quality checks

- **RLS**: `fn_assert_rls_disabled()` passes after every migration and after load;
  **0** application tables have `relrowsecurity` or `relforcerowsecurity` = true.
  No RLS policies created (hackathon requirement). Prompt 3 owns the API-only
  access path and anon/authenticated grant revocation.
- **Synthetic guard**: `synthetic_meta.app_environment = synthetic_hackathon`;
  the loader refuses destructive writes unless the marker is present or
  `--confirm-synthetic-dev-target` is passed.
- **Backup gate**: a `SyntheticDataRun` backup marker + a local count-snapshot
  (`datagen/fixtures/<run>/pre_reload_backup_marker.json`) is written before any
  truncate; the reload refuses to proceed without a marker.
- **No secrets** printed/logged/committed; error messages are credential-scrubbed.
- **Data-quality scenarios** live only in staging (`SourceRecord` /
  `IngestionRecord` / `DataQualityIssue` / quarantined `EvidenceObject`) — never in
  canonical tables: 56 DataQualityIssue rows covering missing-required, duplicate
  source, conflicting dates, invalid jurisdiction, corrupt/duplicate file,
  late/retracted source, partial/retried import.
- **Evidence**: every file-backed object carries a real SHA-256 + byte size +
  version + append-only activity trail; storage status `fixture_pending_cloud_upload`
  (no S3 upload this phase). No OCR/extraction — manual metadata only.
- **ML separation**: aggregate `OutcomeLabel` derived only from post-cutoff
  `OutcomeObservation`s; protected attributes (caste/religion/gender/juvenile)
  excluded from feature schemas; legacy individual-risk outputs (`CrimeRiskScore`,
  `ModelInference`) were cleared and **not** rerun. The one seeded governed model
  is an **aggregate area-incident-forecast**, not person-level scoring.

---

## 7. Known limitations

1. **Disk-constrained scale.** The dev Supabase disk (~0.8–1 GB usable) cannot
   hold a *fully rich* 100k dataset (~1 GB+). Statistical/performance modes run a
   lean per-case profile (fewer victims/witnesses/evidence/statements, shorter
   narratives) so 100k fits at 727 MB. Golden stays fully rich. This is an
   environment limit, not a generator limit — a larger disk (or AWS RDS later)
   would allow the full-density 100k.
2. **Reference tables are preserved, not regenerated.** The loader relies on the
   live reference tables matching the generation config (Unit 1,032 / District 32 /
   Employee 12,000 / Court 500 — asserted before load) and additively inserts the
   6 v2 lifecycle statuses. A full reference reload path is deferred (protects the
   governance seed) to a later phase.
3. **Graph node breadth.** Every canonical person appearing in a case is promoted
   to an `EntityGraph` node (205k), which is broad but fully canonical-linked and
   provenanced. Prompt 11 will rebuild/prune derived graph analytics.
4. **Backup = marker + count snapshot + regenerable seed**, not a full `pg_dump`
   (the synthetic data is deterministic from `--seed`). A full pg_dump is the
   recommended production backup and is documented in §9.
5. **Prediction governance demo is minimal** (one approved aggregate ModelVersion +
   one request/result/review). Full feature/prediction workflows are Prompt 10.

---

## 8. Definition of Done — verification

- [x] Datagen v2 exists and is scenario-driven (`scenario_registry` state machines as data).
- [x] Stable canonical identity replaces A1/A2/name matching (16,246 distinct canonical persons; 14,069 reused across cases; 0 name-based links).
- [x] Migrations 005–009 apply cleanly (idempotent; verified 59 → 114 tables).
- [x] Golden fixture covers every required scenario (scenario-minimum gate passes).
- [x] 100k synthetic fixture loads into development Supabase (100,000 cases / 2,978,813 rows).
- [x] Zero canonical spatial, lifecycle, identity, evidence, and FK integrity failures (in-memory + DB-side + full scan).
- [x] No current synthetic individual-risk batch is rerun (legacy risk tables cleared; only an aggregate model demo seeded).

---

## 9. Backup / restore procedure

- **Before any destructive reload** the loader records a `SyntheticDataRun`
  backup marker (`IsBackupMarker = true`) and writes a JSON count snapshot to
  `datagen/fixtures/<run>/pre_reload_backup_marker.json`; the reload refuses
  without a marker.
- **Restore option A (recommended, deterministic):** re-run
  `python generate_v2.py --mode <mode> --firs <n> --seed <seed> --truncate
  --confirm-synthetic-dev-target` — the fixture is fully reproducible from the seed.
- **Restore option B (full):** take a `pg_dump` before a reload and restore it,
  e.g. `pg_dump "$DATABASE_URL" -Fc -f backup.dump` / `pg_restore -d "$DATABASE_URL" backup.dump`.
- **Disk recovery:** if a load exhausts disk, `python -m datagen.reclaim` truncates
  the bloated (logically empty) fixture tables biggest-first to free space.

---

## 10. Next-phase (Prompt 2) prerequisites — satisfied

- Canonical identity + `CasePartyRole` schema and populated data are available for
  the People/roles APIs.
- `SourceSystem`/`SourceRecord`/`IngestionJob` staging + `CaseVersion`/`CaseEvent`
  + `CaseCategoryWorkflow` back the intake draft/validate/workflow endpoints.
- Category-specific workflow rules are queryable in `CaseCategoryWorkflow`.
- `synthetic_meta` marker + RLS-disabled verification are in place for the Prompt 3
  hackathon-mode guards.
- Reference lookups (units, districts, categories, statuses incl. the 6 new
  lifecycle statuses, acts/sections, crime taxonomy) are present and consistent.

Prompt 2 should build the FIR/case/people intake UI + APIs against the canonical
schema; enable UI writes only after Prompt 3 finalises the API-only access path,
synthetic-data guard, restricted CORS, and the repeatable RLS-disabled check.
