# PHASE 09 REPORT — Jurisdiction boundaries, station geography, maps, and spatial repair

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`ap-south-1`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> The DATABASE is the single source of truth for jurisdiction geography. Versioned
> boundaries live in `JurisdictionBoundary` (state / district / taluk / unit-SHO);
> containment is enforced by `fn_point_in_state` / `fn_point_in_district` /
> `fn_point_in_unit`. A canonical row that fails containment is **never silently
> moved** — it is staged as a `DataQualityIssue`, and only a REVIEWED reassignment
> / override / quarantine (audited in `JurisdictionReassignment`, recorded as a new
> versioned `CaseVersion`) changes its assigned jurisdiction. The map overlays and
> the intake picker read the same persisted geometry the DB validates against, so
> UI and database share one rule set.

---

## 1. Outcome summary

Phase 9 completes and hardens the spatial data path. Much of the base geography was
already built by migration 009 + the v2 datagen (Phase 1); this phase filled the
gaps: taluk persistence, unit-level containment, a location-observation containment
view, a reviewed reassignment/override audit trail, a containment scan/repair job,
a jurisdiction-constrained intake picker with a mismatch→reassign/override workflow,
a supervisory jurisdiction-review queue, and boundary-freshness readouts.

| Definition of Done | Result |
|---|---|
| Boundaries and stations are persisted/versioned | `JurisdictionBoundary` now holds state 1 · district 32 · **taluk 230** · SHO 1000, all `IsCurrent` v1; `UnitLocation` 1000. Taluks were persisted by an idempotent loader (`app/geo/persist.py`) and the datagen generator now emits them too. Verified. |
| Canonical geography has zero containment failures | `vw_caseversion_containment`: out_of_state **0**, out_of_district **0**, checked **100000**. `vw_location_observation_containment`: out_of_state **0**, checked **7684**. Verified read-only against the live DB. |
| UI and database share the same jurisdiction rules | New `GET /geo/db-boundaries/{level}` serves the SAME persisted geometry the DB enforces; the intake `LocationPicker` and the jurisdiction-review queue validate/repair against those DB functions; the map shows persisted counts/version + freshness. |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/016_jurisdiction_repair_reassign.sql` — additive + idempotent
  (applied twice, no error). Adds `fn_point_in_unit` (unit/SHO containment);
  `vw_location_observation_containment` (imported-GPS spatial check);
  `JurisdictionReassignment` (append-only reviewed-repair audit);
  `SpatialRepairRun` (scan before/after metadata); widens the boundary `Level`
  allow-list to include `taluk`; supporting indexes; read-only grants. Re-asserts
  RLS disabled + NO FORCE via `fn_disable_rls_all_app()` / `fn_assert_rls_disabled()`.

### New backend
- `services/ml/app/geo/persist.py` — idempotent boundary loader
  `ensure_boundaries(conn)` that inserts state/district/**taluk** into
  `JurisdictionBoundary` from the bundled KGIS-simplified GeoJSON (same source as
  `datagen/geo`); `summary(conn)` for counts. Skips any level/name/district that
  already has a current row; never deletes or moves.
- `services/ml/app/geo/jurisdiction.py` — `db_boundaries(level)` (GeoJSON from the
  persisted table); `freshness()` (per-level counts/version/as-of + last scan +
  open issues + env label); `scan_containment(conn, scope, actor, limit,
  case_master_id)` (reads the containment view, raises reason-coded
  `DataQualityIssue`s idempotently, records a `SpatialRepairRun`, **no move**);
  `_district_containing(conn, lon, lat)` (GiST `ST_Contains` → detected district);
  `containment_issues(status, page)` (reassignment queue);
  `_reassign(...)` (validates the point is inside the target district for a
  `reassign`, else 409; supersedes the current `CaseVersion` with a new version +
  `CaseEvent`; writes `JurisdictionReassignment` + a `SourceRecord`; resolves the
  open issue; audits) with public `scan()` / `reassign()` wrappers.

### Modified backend
- `services/ml/app/geo/schemas.py` — `JurisdictionFreshnessResponse`,
  `ContainmentScanResponse`, `ContainmentIssue`(+`resolved_district_name`),
  `ContainmentIssuesResponse`, `ReassignRequest`, `ReassignResponse`.
- `services/ml/app/geo/router.py` — 5 new routes (below); imports `Depends` +
  `intake.guards`.
- `services/ml/app/batch.py` — `load-boundaries` (runs the loader) + `geo-scan`
  (runs a containment scan) CLI subcommands.
- `services/ml/app/intake/schemas.py` — `IncidentInfo.jurisdiction_override_reason`.
- `services/ml/app/intake/service.py` — an out-of-assigned-district incident is now
  a **blocking** validation error (`jurisdiction_mismatch`, with the detected
  district hinted) UNLESS a supervisory `jurisdiction_override_reason` is present
  (then downgraded to a `jurisdiction_override` warning); on approval with an
  override, records an accepted `DataQualityIssue` + a
  `JurisdictionReassignment(action='override')`. (out-of-state stays blocking.)

### Datagen (repeatable source of truth for future regenerations)
- `datagen/external_context.py` — `build_context_layer` now also persists **taluk**
  `JurisdictionBoundary` rows (keyed to their district; skips the BBMP
  district-as-taluk fallback already persisted at district level), alongside the
  existing state/district/SHO writes. `py_compile` clean.

### New / modified frontend `web/src/`
- `api/types.ts` — `IntakeIncidentInfo.jurisdiction_override_reason`; Phase-9 types
  (`JurisdictionFreshness`, `JurisdictionBoundaryFreshness`, `ContainmentScanResult`,
  `ContainmentIssue`, `ContainmentIssuesResponse`, `JurisdictionReassignRequest`,
  `JurisdictionReassignResult`).
- `api/endpoints/geo.ts` — `DbBoundaryLevel` type + `geoApi.dbBoundaries`,
  `jurisdictionFreshness`, `jurisdictionIssues`, `jurisdictionScan`,
  `jurisdictionReassign`.
- `routes/intake/fir/LocationPicker.tsx` — an out-of-assigned-district pin now shows
  a blocking mismatch panel with a **"Use detected district"** button (reassign the
  registering district to the detected one) + a supervisory **override reason**
  input (supervisor/super_admin only; a hint otherwise).
- `routes/intake/fir/steps/IncidentStep.tsx` — wires those callbacks to the draft
  payload (`registration.district_id` / `incident.jurisdiction_override_reason`).
- `routes/review/jurisdiction/JurisdictionReview.tsx` (new) — supervisory
  jurisdiction-review queue: lists open mismatches, a "Scan canonical geography"
  action, and per-issue Reassign-to-detected / Override / Quarantine with a recorded
  reason; a boundary-freshness panel (persisted counts/versions, unit locations,
  open issues, last scan, synthetic-demo badge). Policymaker blocked.
- `App.tsx` — route `/review/jurisdiction`.
- `routes/map/MapHotspots.tsx` — a boundary-data-freshness readout in the Boundaries
  panel (persisted state/district/taluk counts + version + open-issue count) with a
  "Review" link to the jurisdiction queue (non-policymaker). (The map already had
  distinct state/district/taluk/SHO overlays, five distinct modes — live / hotspots /
  forecast / patrol / alerts — a time slider, and the persistent synthetic badge.)

### New tests
- `services/ml/tests/test_geo_jurisdiction.py` (9 tests).
- `web/src/routes/intake/fir/LocationPicker.test.tsx` (3 tests).
- `web/src/routes/review/jurisdiction/JurisdictionReview.test.tsx` (2 tests).

---

## 3. Database objects / endpoints / screens

### Database (migration 016)
- Functions: `fn_point_in_unit(unit_id, lon, lat)`.
- Views: `vw_location_observation_containment`.
- Tables: `JurisdictionReassignment` (reviewed-repair audit; `Action ∈
  reassign|override|quarantine|regenerate`; From/To case-version, district, unit;
  reason; reviewer; `SourceRecordID`; `DataQualityIssueID`; Before/After JSONB),
  `SpatialRepairRun` (RunKey, Scope, Checked/OutOfState/OutOfDistrict/IssuesRaised,
  Totals, Actor).
- Constraint change: `chk_jurisdiction_level` now allows `taluk`.

### API endpoints (prefix `/geo`, 5 new)
- `GET /geo/db-boundaries/{level}` — persisted/versioned GeoJSON
  (`state|district|taluk|unit|sho`); public reference geography.
- `GET /geo/jurisdiction/freshness` — boundary versions/counts/as-of + last scan +
  open issues + env label; public.
- `GET /geo/jurisdiction/issues` — reviewed-reassignment queue (non-policymaker).
- `POST /geo/jurisdiction/scan` — stage containment failures as `DataQualityIssue`s
  (supervisory `require_intake_review` + `require_write_allowed`).
- `POST /geo/jurisdiction/reassign` — reviewed reassignment/override/quarantine
  (same guards). 409 if reassigning to a district that does not contain the point.

### Screens
- **Intake → Incident step** — click-to-pin location with live jurisdiction; an
  out-of-district pin blocks submit and offers "Use detected district" (reassign)
  or a supervisory override reason.
- **Review → Jurisdiction** (`/review/jurisdiction`, new) — open-mismatch queue,
  scan action, per-issue reassign/override/quarantine with a reason, and a
  boundary-freshness panel with the synthetic-demo badge.
- **Map & Hotspots** — persisted state/district/taluk/SHO overlays, freshness
  readout + open-issue count + link to the jurisdiction queue.

---

## 4. Before / after spatial counts

The roadmap's original **live-Supabase** audit reported thousands of containment
failures (≈6,732 out-of-state / ≈17,653 out-of-district). Those were fixed at the
source by the Phase-1 v2 datagen: the AWS RDS fixture places every synthetic
coordinate on the real Karnataka landmass, so canonical geography already starts
clean. Phase 9 makes that guarantee explicit, versioned, and repairable.

| Metric | Before (audit) | After (verified read-only) |
|---|---:|---:|
| `JurisdictionBoundary` — state / district / **taluk** / SHO | 1 / 32 / **0** / 1000 | 1 / 32 / **230** / 1000 (all v1, current) |
| `UnitLocation` (current) | 1000 | 1000 |
| CaseVersion containment — out_of_state / out_of_district / checked | 0 / 0 / 100000 | **0 / 0 / 100000** |
| LocationObservation containment — out_of_state / checked | 0 / 7684 (sampled) | **0 / 7684** |
| Unit/SHO containment helper | — | `fn_point_in_unit` present |
| RLS enabled on new Phase-9 tables | — | **false** (JurisdictionReassignment, SpatialRepairRun) |

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `016_jurisdiction_repair_reassign.sql` twice (`python -m app.batch apply-sql`) | PASS — functions/view/tables/constraint created; RLS-disabled asserted; idempotent (0 changes on re-run) |
| `python -m app.batch load-boundaries` (then re-run) | PASS — persisted 230 taluks; re-run inserted 0 (idempotent) |
| Read-only after-snapshot verification | PASS — containment 0/0/100000; boundaries 1/32/230/1000 v1; LO containment 0/7684; RLS=false on both new tables; synthetic marker present |
| Backend smoke (rolled back): scan → reassign / refuse / boundaries / freshness | PASS — scan flags a mis-assigned case (1 issue + SpatialRepairRun), reassign supersedes to v2 + resolves the issue, wrong-district reassign → 409, db_boundaries/freshness OK |
| `python -m pytest tests/test_geo_jurisdiction.py tests/test_geo.py tests/test_intake.py -q` | **42 passed, 2 failed** — the 2 are pre-existing data-dependent batch-output tests, unrelated to Phase 9 (see §7) |
| `npm run typecheck` (web) | PASS (tsc, 0 errors) |
| `npx vitest run` (web, full suite) | **39 passed** (13 files, incl. the 5 new Phase-9 tests) |
| `npm run build` (web) | PASS — 3585 modules transformed; dist emitted (pre-existing chunk-size warning only) |
| `python -m py_compile` (edited datagen + backend files) | PASS |

### Test coverage
- **Backend `test_geo_jurisdiction.py` (9)** — `fn_point_in_state` land (Bengaluru)
  vs outside (Odisha); `fn_point_in_district` own-district true vs neighbour false;
  persisted `db_boundaries` state/district/taluk GeoJSON with a version;
  `ensure_boundaries` idempotent (0 inserts) + `summary`; `freshness` levels + env;
  scan flags a wrong-district case with the detected district in the issue detail +
  records a `SpatialRepairRun` **without moving the row**, then a reviewed reassign
  supersedes the `CaseVersion` (version+1, current, corrected district), resolves
  the issue, and writes a `JurisdictionReassignment`; scan idempotency (second run
  raises 0); reassign to a wrong district raises `JurisdictionConflict`; override
  keeps the district WITHOUT a new version; quarantine supersedes. (All under
  `rw_rollback` — real SQL, then discarded.)
- **Frontend (5)** — `LocationPicker`: mismatch → "Use detected district" calls back
  with the detected id/name; supervisor sees the override input; in-district shows a
  clean match and no mismatch panel. `JurisdictionReview`: supervisor lists an open
  mismatch with an enabled "Reassign to detected" action + freshness badge;
  policymaker is blocked.

---

## 6. Security and data-quality checks

- **RLS** stays disabled + NO FORCE (migration 016 re-asserts `fn_assert_rls_disabled()`;
  verified `relrowsecurity = false` on `JurisdictionReassignment` and
  `SpatialRepairRun`). No RLS policies created.
- **API-only data path**: every screen is React → FastAPI → PostgreSQL; boundaries,
  freshness, issues, scan and reassignment all go through FastAPI. No DB credentials
  or direct table queries in the browser; no secrets printed in this phase.
- **Write guards**: scan + reassign require a supervisory role
  (`require_intake_review`) AND `require_write_allowed` (localhost + synthetic-DB
  marker); the issues queue and case-level views are blocked for policymaker.
- **No silent moves**: a containment failure only ever becomes a `DataQualityIssue`;
  changing a case's jurisdiction requires a reviewed action that supersedes the
  `CaseVersion` and writes a `JurisdictionReassignment` + `SourceRecord`
  (append-only audit). A reassign to a district that does not contain the point is
  refused (409) — the reviewer must override or quarantine instead.
- **Structured input only**: the intake picker canonicalises validated
  form fields (coordinates, district, override reason); no OCR/extraction; a file
  upload never changes a prediction.
- **No high-impact automation**: reassignment is investigation-support case
  administration; nothing here produces person-level criminal-justice decisions or
  offender risk.

---

## 7. Known limitations

1. **No live 100k reload** — the datagen taluk-persistence enhancement applies on
   the next golden regeneration; the existing shared fixture was not reloaded (out
   of scope, avoids replacing shared synthetic data). Live taluks were persisted
   idempotently by `app.batch load-boundaries`. Canonical containment is already
   clean (0/0), so no repair was required on live data — the repair path is proven
   by rolled-back tests + smoke runs.
2. **Full-scope scan cost** — a full `caseversion` scan evaluates all 100k current
   versions through the containment view (~tens of seconds). The scan accepts a
   `case_master_id` for a fast targeted re-check (used by intake and tests); the
   `/geo/jurisdiction/scan` endpoint runs the full scan under a supervisory guard.
3. **Pre-existing full-suite failures (2), unrelated to Phase 9** — verified not
   caused by this phase (no hotspot/alert batch code changed):
   `test_geo::test_hotspots_written_and_active` and
   `test_geo::test_emerging_alerts_present` require the hotspot-KDE / anomaly-alert
   **batch jobs** to have materialized `CrimeHotspot` / `AlertHistory` rows on this
   DB; those jobs were not run here. This is a subset of the pre-existing failures
   noted in the Phase 8 report.
4. **Beat level** — `beat` is allowed by the boundary constraint but no beat
   polygons are persisted (the SHO/unit jurisdiction is the operational sub-district
   cell); beat-level containment can be added when beat geometry exists.
5. **Taluk containment view** — containment is enforced at state/district/unit
   levels (the levels a case is assigned to); taluks are persisted + served for the
   map but are not part of the case-assignment containment check.

---

## 8. Next-phase prerequisites (Prompt 10 — feature schemas / snapshots / predictions)

- Canonical incident geography is validated and versioned per `CaseVersion`
  (`AssignedDistrictID` / `AssignedUnitID`), and a reviewed reassignment produces a
  new current version — the `FeatureSnapshot` builder should read the CURRENT
  `CaseVersion` so a jurisdiction correction is reflected in features.
- Jurisdiction/district may be a permitted spatial feature; caste/religion/gender/
  juvenile/other protected attributes must NOT enter feature schemas.
- `DataQualityIssue` (invalid_jurisdiction_*) + `JurisdictionReassignment` provide
  the provenance a snapshot can cite; only resolved/accepted geography should feed a
  versioned snapshot.
- Prompt 6 (OCR/extraction) remains **Deferred**.

---

## 9. Definition of Done — verification

- [x] Boundaries and stations are persisted/versioned — `JurisdictionBoundary`
      state 1 / district 32 / taluk 230 / SHO 1000 (all current, v1) + `UnitLocation`
      1000; loaded by an idempotent loader and now emitted by the datagen generator;
      containment helpers at state/district/unit. Verified read-only.
- [x] Canonical geography has zero containment failures — `vw_caseversion_containment`
      out_of_state 0 / out_of_district 0 / checked 100000; `vw_location_observation_containment`
      out_of_state 0 / checked 7684. Verified read-only.
- [x] UI and database share the same jurisdiction rules — `GET /geo/db-boundaries/{level}`
      serves the persisted geometry the DB validates against; the intake picker and
      the jurisdiction-review queue validate/repair through the DB containment
      functions; the map shows persisted counts/version + freshness. Mismatch is a
      blocking, reviewable, audited workflow (no silent moves).
