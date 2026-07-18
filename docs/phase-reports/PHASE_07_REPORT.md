# PHASE 07 REPORT — Structured statements, property/seizure, lab, court & lifecycle inputs

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`ap-south-1`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> All information is entered manually through typed forms / validated APIs. No OCR,
> speech-to-text, or automated parsing is added. An uploaded file may be LINKED as a
> reference (by evidence id) but its content never auto-populates any record. Case
> status is derived from append-only events; verified outcomes come only from final events.

---

## 1. Outcome summary

Added the contextual casework surface the schema had tables for but the app lacked:
typed **statements** (versioned, redaction/access-classified, reviewed), **property /
seizure** metadata (vehicle/weapon/substance/document + disposal lifecycle), optional
**lab-result** metadata, and **court events / bail / disposition / verified outcomes** —
plus an **event-backed case timeline** (CaseEvent + CourtEvent, not just derived dates).

| Definition of Done | Result |
|---|---|
| Major hackathon investigative/court inputs are structured, digital and auditable | New `/casework` module + 4 case sub-pages; every write emits a sanitised `audit_logs` row; statements/lab classified + redaction-aware |
| Case status/timeline is event-backed and consistent | Status derived from `CaseVersion`/`CaseEvent`; lifecycle transitions validated by the seeded `CaseCategoryWorkflow`; timeline merges CaseEvent+CourtEvent(+statements/seizures/dispositions/outcomes) |
| Verified outcomes can support future labels | `OutcomeObservation` can be created ONLY after a verified final event (final disposition or judgment) and never before the observation-window end (leakage guard) — enforced + tested |
| No OCR/transcription/extraction is required | No extraction code/deps; files linked by id only; proven by the existing no-extraction guarantees |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/014_lab_result_court_supplementary.sql` — minimal `LabResult`
  table (test type, lab name, requested/result dates, result summary, status,
  linked report `EvidenceItemID`, access classification; optional Property/Seizure
  link) + widened `CourtEvent.EventType` allow-list (adds `supplementary_chargesheet`,
  `remand`, `framing_of_charges`, `adjournment`, `bail_hearing`, `transfer`) + indexes;
  re-asserts RLS disabled. Additive + idempotent (applied twice, no error).

### New backend module `services/ml/app/casework/`
`__init__.py`, `schemas.py` (typed models), `service.py` (all logic; internal
`_fn(conn, ...)` helpers for rollback tests + public wrappers), `router.py`
(20 endpoints). Reuses `intake.guards` (role/localhost/synthetic gates),
`intake.workflow` (lifecycle rules + `validate_event`), and `intake.service._add_case_event`
(lifecycle CaseEvents). Registered in `services/ml/app/main.py`.

### Modified backend
- `services/ml/app/main.py` — register `casework_router`.

### Datagen generator enhancements (golden coverage for future regenerations)
- `datagen/statements.py` — rotate all statement types incl. `expert`.
- `datagen/property_seizure.py` — add `document` items + full disposal lifecycle
  (`seized/recovered/returned/disposed`).
- `datagen/court_outcomes.py` — add `remand`, `framing_of_charges`, `adjournment`,
  and occasional `supplementary_chargesheet` court events.

### New / modified frontend `web/src/`
- `api/endpoints/casework.ts` (new) wired into `api/index.ts` as `api.casework`;
  `api/types.ts` appended with `Cw*` types.
- New sub-pages `routes/cases/subpages/{StatementsPage,PropertyPage,CourtLifecyclePage}.tsx`
  + shared `routes/cases/subpages/casework/caseworkShared.ts`.
- `routes/cases/subpages/TimelinePage.tsx` — **rewritten** to use the event-backed
  casework timeline (falls back to derived registration/arrest/chargesheet dates).
- `routes/cases/CaseFile.tsx` — sub-nav tabs Statements / Property & seizures /
  Court & lifecycle; TimelinePage now receives `caseId`.

### New tests
- `services/ml/tests/test_casework.py` (16 tests).
- `web/src/routes/cases/subpages/casework/casework.test.tsx` (2 tests).

---

## 3. Database objects / endpoints / screens

### Database (migration 014)
- New `LabResult` table (+3 indexes, updated-at trigger). `CourtEvent.EventType`
  documented allow-list. (Statement/StatementVersion/Seizure/PropertyItem/CourtEvent/
  BailEvent/CaseDisposition/OutcomeObservation already existed from migration 007.)

### API endpoints (prefix `/casework`, 20)
Read (deny policymaker): `GET /lookups`, `GET /cases/{cid}/timeline`,
`GET /cases/{cid}/statements`, `GET /statements/{sid}`, `GET /cases/{cid}/seizures`,
`GET /cases/{cid}/lab-results`, `GET /cases/{cid}/court`.
Write (investigator/supervisor/super_admin + localhost + synthetic): `POST /cases/{cid}/statements`,
`PUT /statements/{sid}`, `POST /cases/{cid}/seizures`, `POST /cases/{cid}/property-items`,
`PUT /property-items/{pid}/status`, `POST /cases/{cid}/lab-results`, `PUT /lab-results/{lid}`,
`POST /cases/{cid}/court-events`, `POST /cases/{cid}/bail`, `POST /cases/{cid}/lifecycle-events`.
Supervisory (supervisor/super_admin): `POST /statements/{sid}/review`,
`POST /cases/{cid}/disposition`, `POST /cases/{cid}/outcome`.

### Screens (case sub-nav)
- **Statements** — list (redaction-aware), record, correct (append-only versions),
  review-lock; restricted badge + access-limited text for non-sensitive roles.
- **Property & seizures** — seizures with items, add seizure (+items+memo ref),
  standalone item, inline status change; **Lab results** panel (add/list, redaction-aware).
- **Court & lifecycle** — current status badge, allowed lifecycle-transition buttons,
  court events (+add), bail grant/reject, disposition (supervisory), verified-outcome
  action gated by `can_record_outcome`.
- **Timeline** — event-backed (badge) vertical timeline; derived fallback.

---

## 4. Prerequisite / consistency rules enforced (server-side)

- **Statement versions** are append-only (`StatementVersion`); a reviewed statement is
  locked against further correction; redaction escalates access to `restricted`.
- **Restricted statements / lab results** are redacted for roles outside
  {investigator, supervisor, super_admin}; the analyst role sees a redaction notice.
- **Court events**: `hearing`/`remand`/`framing_of_charges`/`adjournment`/`supplementary_chargesheet`
  require a prior chargesheet (CourtEvent `chargesheet_filed`, CaseEvent `chargesheet_filed`/
  `court_assigned`, or a legacy `ChargesheetDetails`); `judgment` requires a chargesheet or a
  prior hearing/framing.
- **Disposition**: `convicted`/`acquitted` require a prior recorded `judgment` court event.
- **Outcome**: refused unless a verified final event exists (final `CaseDisposition` or a
  `judgment`); `observed_at` must be on/after the observation-window end (no label leakage).
- **Lifecycle transitions** are validated against the seeded `CaseCategoryWorkflow`; a legacy
  case (no `CaseVersion`) is bootstrapped with a version + an initial event so prerequisite
  gating stays consistent.

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `014_lab_result_court_supplementary.sql` twice | PASS — LabResult + CourtEvent allow-list + indexes; RLS-disabled asserted (idempotent) |
| `python -c "from app.main import app"` | PASS — 20 `/casework` routes registered |
| `python -m pytest tests/test_casework.py -q` | **16 passed** (~22 s) |
| `python -m pytest tests/test_casework.py tests/test_intake.py tests/test_evidence.py tests/test_readonly.py -q` | **73 passed, 1 skipped** (no regressions) |
| `python -m pytest --collect-only -q` | 247 tests collected, no import errors |
| `python -c "from datagen import statements, property_seizure, court_outcomes"` | PASS (generator enhancements import) |
| `npm run typecheck` (web) | PASS (tsc, 0 errors) |
| `npm run test` (web, vitest) | **32 passed** (10 files) |
| `npm run build` (web) | PASS (dist emitted) |

> `npm` exits non-zero on stderr warnings (React Router future flags / chunk size) even
> when all pass; the authoritative signal is the `passed` / `built` lines.

### Backend test coverage (`test_casework.py`, 16)
Statement create + immutable version history; restricted-statement redaction for analyst
vs full text for IO; statement↔evidence linkage; reviewed-statement lock; seizure + items +
memo link + unlinked item; property status change; lab create/update + restricted redaction;
**court-event prerequisites (hearing/judgment rejected before chargesheet, allowed after)**;
**disposition requires a prior judgment**; **outcome refused before a final event** + leakage
guard; bail; **lifecycle bootstrap + valid chain + invalid transition**; timeline event-backed
+ derived fallback; lookups; policymaker 403. A helper inserts a minimal fresh `CaseMaster`
(valid 18-digit CrimeNo) for clean-slate tests, since every loaded case already has CaseEvents.

---

## 6. Datagen coverage (loaded synthetic fixture)

| Domain | Count | Distribution |
|---|---:|---|
| Statement | 9,894 | witness (loaded run); 700 restricted / 9,194 normal; +11,090 StatementVersion |
| Seizure | 13,641 | — |
| PropertyItem | 13,765 | property 10,360 / substance 2,369 / weapon 1,036; seized 9,582 / recovered 4,183 |
| CourtEvent | 64,391 | chargesheet_filed 37,147 / hearing 18,783 / judgment 8,461 |
| BailEvent | 27,196 | granted 16,339 / rejected 10,857 |
| CaseDisposition | 28,309 | all final: closed_b 10,445 / transferred 5,601 / convicted 4,566 / acquitted 3,895 / closed_c 3,802 |
| OutcomeObservation | 28,309 | all verified, all carry an observation window (leakage-safe) |
| CaseEvent | 386,987 | full lifecycle vocabulary |
| CaseCategoryWorkflow | 36 | FIR / Zero FIR / UDR / NCR / PAR transitions |
| LabResult | 0 | new table (migration 014) — populated via the UI/API |

Every Phase-7 domain is represented in the loaded fixture. The generator enhancements above
broaden **type variety** (expert statements, document property, remand/framing/adjournment/
supplementary court events, full disposal lifecycle) for the next golden regeneration; the
API/UI already exercise the full type range (proven by the tests, which create vehicle/weapon/
substance property, chargesheet/hearing/judgment court events, dna lab results, etc.).

---

## 7. Security and data-quality checks

- **RLS** stays disabled + NO FORCE (migration 014 re-asserts `fn_assert_rls_disabled()`).
- **Write guards**: every casework write is localhost + synthetic-DB gated; supervisory
  actions (statement review, disposition, outcome) require a supervisor/super_admin role;
  policymaker is denied all casework reads (403, tested).
- **Restricted access**: restricted statement/lab text is redacted server-side for non-sensitive
  roles (never sent to the browser).
- **Audit**: statements, property, lab, court events, bail, disposition, outcome and lifecycle
  events all write sanitised `audit_logs` rows (no secrets/PII/free-text).
- **No extraction / no prediction**: no OCR/parsing added; uploaded files are referenced by id
  only; casework writes never invoke a model.
- **Leakage guard**: outcomes cannot be recorded before a final event or before the observation
  window ends.

---

## 8. Known limitations

1. **Loaded-fixture type variety** — the 100k fixture predates the generator diversity
   enhancements (statements are all `witness`; no vehicle/document property; court events limited
   to chargesheet_filed/hearing/judgment). Regenerating the golden fixture would apply the fuller
   variety; the app/API/UI already support and are tested against all types. No 100k reload was
   performed (out of scope; would replace the shared synthetic fixture).
2. **Lifecycle bootstrap for legacy cases** — cases without a `CaseVersion` get a bootstrap
   version + initial event on first lifecycle action; advanced-status legacy cases may not have
   every intermediate prerequisite event, so some transitions are unavailable until re-derived.
   Intake-created cases have full event history and are unaffected.
3. **Statement speaker / evidence linking in the UI** uses a canonical-person-id / evidence-id
   field (person search lives on the People page); a combined inline picker is a later refinement.
4. **Lab workflow** is intentionally minimal (metadata only) per the hackathon scope.

---

## 9. Next-phase prerequisites

- Prompt 8 (digital/CDR/device/media + financial imports) can reuse the `/casework` +
  `intake` guard/workflow patterns and the `EvidenceItem` reference model.
- Verified `OutcomeObservation` rows (post-window, final-event-backed) are the leakage-safe
  basis for Prompt 10 outcome labels; `CaseEvent`/`CourtEvent` provide the event history.
- Prompt 6 (OCR/extraction) remains **Deferred**.

---

## 10. Definition of Done — verification

- [x] Major hackathon investigative/court inputs are structured, digital and auditable (statements, property/seizure, lab, court/bail/disposition — APIs + UI + audit).
- [x] Case status/timeline is event-backed and consistent (CaseEvent/CourtEvent timeline + workflow-validated status).
- [x] Verified outcomes can support future labels (OutcomeObservation gated by final event + window; leakage-safe).
- [x] No OCR/transcription/extraction is required (manual entry; files linked by id only; tested).
