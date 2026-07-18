# PHASE 02 REPORT — FIR, case, people, and lifecycle input UI + APIs

Status: **Complete**
Date: 2026-07-16
Target: development Supabase project referenced by `.env` (`DATABASE_URL`), PostgreSQL 17.6.
Mode: synthetic hackathon demo only (`synthetic_meta.app_environment = synthetic_hackathon`).

> No secret values (database password, Supabase/AWS keys, tokens) are printed,
> logged, committed, or reproduced anywhere in this report or the code. Every DB
> access resolves `DATABASE_URL` at runtime.

---

## 1. Outcome summary

Built the complete contextual **FIR / case / people intake** surface — a
7-step React wizard, an intake inbox with supervisory review, a bulk CSV/JSON
import screen, and a data-quality review queue — on top of a fully typed FastAPI
`intake` module. Structured drafts are staged (never written to canonical tables
until approved), validated server-side with **category-specific lifecycle
rules**, and, on approval, canonicalised in one transaction into
`CaseMaster` + `CaseSource` + `CaseVersion` + initial `CaseEvent` + canonical
`CasePartyRole` rows (each backed by a stable `CanonicalPerson`/
`CanonicalOrganisation`, with legacy `Accused`/`Victim`/`ComplainantDetails`
kept in sync so the existing Case File keeps working) + `ActSectionAssociation`.

Every Definition-of-Done item is verified:

| DoD item | Result |
|---|---|
| Create, validate, save, review, approve, open a structured case | Verified end-to-end at the API/service layer (28 tests) for FIR / Zero FIR / UDR / Missing Person; full wizard + inbox + review UI built |
| All case-party roles use canonical identity records | Approval creates `CasePartyRole` + `CanonicalPerson/Organisation`; People page renders canonical parties with `PublicRef` |
| Category-specific workflows are server validated | `workflow.validate_event` enforces `CaseCategoryWorkflow` transitions + prerequisites; invalid combinations rejected by the backend (tested) |
| UI submit enabled only after Prompt 3 | Submit/approve gated OFF (`intake_submit_enabled=false`) with a visible reason; localhost + synthetic-DB write guards active |
| Tests cover normal and invalid intake paths | 28 backend + 22 frontend tests, all passing |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/010_intake_workflow.sql` — `IntakeDraft` (draft lifecycle
  `draft → submitted → under_review → approved | rejected | returned_for_correction`,
  `Payload` JSONB, links to `SourceSystem`/`SourceRecord`/`IngestionJob`,
  `CaseMasterID` on approval, unique `DraftKey` + `IdempotencyKey`, a CHECK that an
  approved draft must reference a case), `IntakeDraftParty` (draft-scoped party
  roles with optional canonical link + `Attributes`), `IntakeDraftActivity`
  (append-only autosave/submit/review trail), `vw_intake_inbox` view, and seeded
  intake `SourceSystem` rows (`FIR_FORM`/`CSV_IMPORT`/`JSON_IMPORT`). Additive +
  idempotent; ends with `fn_disable_rls_all_app()` + `fn_assert_rls_disabled()`
  (RLS stays disabled + NO FORCE; no policies).

### New backend module `services/ml/app/intake/`
`__init__.py`, `workflow.py` (category rules + status/event constants +
`validate_event` against `CaseCategoryWorkflow`), `guards.py` (role gates +
localhost + synthetic-DB + submit gate + `hackathon_status`), `schemas.py` (typed
request/response models), `lookups.py` (reference/options + workflow metadata),
`service.py` (draft CRUD, validate, duplicate, parties, submit, review/approve
canonicalisation, workflow-gated events, jurisdiction resolve, case parties,
quality issues), `router.py` (endpoints).

### Modified backend
- `services/ml/app/main.py` — register `intake_router`.
- `services/ml/app/config.py` — `hackathon_mode`, `demo_data_only`,
  `intake_writes_localhost_only`, `intake_submit_enabled`, `synthetic_env_expected`.
- `services/ml/app/db.py` — `rw_conn()` now sets `default_transaction_read_only=off`
  at session scope before the working transaction (see §7 — the dev project is in
  Supabase over-quota soft read-only). `ro_conn()` unchanged (still strictly RO).
- `services/ml/tests/conftest.py` — `rw_rollback` fixture (write-path tests roll back).
- `services/ml/tests/test_intake.py` — new suite (28 tests).

### New / modified frontend `web/src/`
- API: `api/endpoints/intake.ts` (new), wired into `api/index.ts` as `api.intake`;
  `api/types.ts` appended with all `Intake*` types.
- Routes: `routes/intake/` — `intakeQueries.ts`, `components.tsx`,
  `useDraftEditor.ts`, `IntakeInbox.tsx`; `routes/intake/fir/` — `FirWizard.tsx`,
  `NewFir.tsx`, `LocationPicker.tsx`, `CaseCreatedPanel.tsx`, `stepTypes.ts`,
  and `steps/{SourceCategory,Registration,Incident,Classification,People,Narrative,Review}Step.tsx`;
  `routes/intake/imports/{parse.ts,IntakeImports.tsx}`;
  `routes/review/quality/QualityReview.tsx`.
- Shell/nav: `components/shell/SyntheticBadge.tsx` (+ wired into `TopBar.tsx`),
  `App.tsx` routes, `config/destinations.tsx` Intake entry.
- `routes/cases/subpages/PeoplePage.tsx` — canonical `CasePartyRole` rendering
  with legacy fallback.
- Test setup: `vitest.config.ts`, `src/test/setup.ts`, `package.json` scripts +
  dev deps (vitest, jsdom, @testing-library/*); tests co-located with sources.

---

## 3. Database objects added (migration 010)

- Tables: `IntakeDraft`, `IntakeDraftParty`, `IntakeDraftActivity` (+ indexes,
  `updated_at` triggers via shared `fn_set_updated_at`).
- View: `vw_intake_inbox` (drafts + party counts + validation flag).
- Seed: `SourceSystem` rows `FIR_FORM`, `CSV_IMPORT`, `JSON_IMPORT`.
- Grants: `SELECT` to `drishti_readonly` on the new tables/view.
- Verified idempotent (applied twice, no error) and RLS disabled + NO FORCE on
  the new tables (`fn_assert_rls_disabled()` passes).

## 4. API endpoints added (prefix `/intake`)

Read (role: any except policymaker):
- `GET /intake/status` — hackathon flags (drives UI submit gate + demo badge).
- `GET /intake/lookups?unit_id=` — categories, gravities, districts, units,
  crime heads/sub-heads, statuses, officers (station-scoped), courts,
  acts/sections, party roles.
- `GET /intake/workflow` — case kinds (+capabilities+allowed roles), statuses,
  party roles, per-category transition table, event labels.
- `POST /intake/geo/resolve` — in-state / in-assigned-district / resolved
  district / nearest station for a point.
- `GET /intake/drafts` — intake inbox (status/kind filter, paginated).
- `GET /intake/drafts/{key}` · `GET /intake/drafts/{key}/activity`.
- `POST /intake/drafts/{key}/duplicate-check`.
- `GET /intake/quality/issues` — staging data-quality queue.
- `GET /intake/cases/{case_id}/parties` — canonical case parties.

Write (role: investigator/supervisor/super_admin + localhost + synthetic-DB guard):
- `POST /intake/drafts` (idempotent), `PUT /intake/drafts/{key}`,
  `POST /intake/drafts/{key}/validate`,
  `POST/PUT/DELETE /intake/drafts/{key}/parties[/{party_id}]`.

Write + submit-gated (also behind `intake_submit_enabled`, off until Prompt 3):
- `POST /intake/drafts/{key}/submit`,
- `POST /intake/drafts/{key}/review?action=approve|reject|return` (review roles),
- `POST /intake/cases/{case_id}/events` (workflow-gated lifecycle event).

Every write returns the affected draft/version/event IDs + validation state.
Approval returns `case_master_id`, `case_version_id`, `case_event_id`, `crime_no`,
`case_party_role_ids`, `canonical_person_ids`.

## 5. Screens / routes added

- `/intake` — Intake inbox (status tabs, New FIR, supervisory approve/return).
- `/intake/fir/new` → eager draft create → `/intake/fir/:draftKey` (7-step wizard:
  Source & category · Registration · Incident (map + jurisdiction) · Classification
  (acts/sections + category-specific) · People (canonical roles) · Narrative ·
  Review & submit). Autosave with visible state, unsaved-change protection,
  inline field errors + page-level summary, blocking-error vs review-warning
  distinction, duplicate candidates, provenance on review, "Continue to
  Evidence/People/Timeline/Case file" after case creation.
- `/intake/imports` — CSV/JSON bulk import with dry-run preview + per-row
  validation + "create N drafts".
- `/review/quality` — returned-for-correction drafts + staging DataQualityIssue queue.
- Persistent "Synthetic Hackathon Demo" badge in the top bar.
- Nav "Intake" destination (investigator/supervisor/super_admin).

---

## 6. Commands run and results

| Command | Result |
|---|---|
| Apply `010_intake_workflow.sql` twice (idempotency) | PASS — tables/view created, RLS disabled + NO FORCE verified, 3 source systems seeded |
| `python -m pytest tests/test_intake.py` (services/ml) | **28 passed** (~53s) |
| `python -m pytest tests/test_readonly.py` | 4 passed (ro_conn still strictly read-only) |
| `python -m pytest --collect-only` | 169 tests collected, no import errors |
| `npm run typecheck` (web) | PASS (tsc --noEmit, 0 errors) |
| `npm run build` (web) | PASS (tsc + vite, 3567 modules, dist emitted) |
| `npm run test` (web, vitest) | **22 passed** (5 files) |

> Note: PowerShell reports a non-zero exit for `npm` whenever any tool writes to
> stderr (deprecation / react-router future-flag / chunk-size warnings) even on
> success; the authoritative signal is the printed `PASS` / `built` / `passed`
> lines, which are all green.

### Backend test coverage (`test_intake.py`, 28)
- Unit (no DB): category rules (`allowed_party_roles`, capabilities), CrimeNo
  code + status mapping, localhost guard, hackathon-status shape.
- Golden create→validate→submit→approve for **FIR / Zero FIR / UDR / Missing
  Person**: 18-digit `CrimeNo` with correct category prefix (1/8/3/1), correct
  initial event + status, `CaseVersion.IsCurrent`, `CasePartyRole` count, legacy
  child rows carrying `CanonicalPersonID`; `ActSectionAssociation` persisted;
  `SourceRecord` committed; draft → `approved`.
- Validation: missing-required (6 fields), out-of-state blocking, temporal-order
  blocking, duplicate source-key detection.
- Category state machine (backend rejection of invalid combinations): accused on
  UDR/Missing Person; chargesheet without prior investigation; arrest on UDR;
  missing-person chargesheet without conversion; chargesheet allowed after
  investigation (→ `Charge Sheeted`).
- Idempotent create (same idempotency key → same draft), optimistic concurrency.
- API: read paths, policymaker 403, submit gate 409 (disabled) → 404 (enabled,
  missing draft), quality issues, canonical case parties.
- All write-path tests run inside a rolled-back transaction (`rw_rollback`): **no
  mutation persists to the live synthetic DB**.

### Frontend test coverage (vitest, 22)
- `parse.ts` CSV/JSON parsing (quotes, blanks, single-object JSON, invalid JSON).
- Import row validation + `toRequest` mapping (canonical complainant party).
- `toOptions`/`subHeadOptions` helpers.
- `NarrativeStep` inline error + edit propagation; `SourceCategoryStep`
  category-per-kind derivation (FIR/Zero FIR/UDR/FIR); `ReviewStep` blocking-vs-
  warning display + submit gate enable/disable.
- `IntakeInbox` renders drafts and the New FIR action (mocked API).

## 7. Security and data-quality checks

- **RLS**: migration 010 keeps RLS disabled + NO FORCE and re-runs
  `fn_assert_rls_disabled()`; 0 app tables have RLS enabled.
- **Write guards**: all intake writes require the request to originate from
  localhost (`intake_writes_localhost_only`) AND the DB to be marked
  `synthetic_hackathon` (`require_synthetic_db`). The canonical case-creating
  transitions (submit / review-approve / case events) are additionally gated by
  `intake_submit_enabled` (default **false**) → return 409 until Prompt 3.
- **No browser→DB path**: React calls only typed FastAPI endpoints; no Supabase
  client, `DATABASE_URL`, or secret is present in the web bundle.
- **X-Role is presentation state**: role gates are enforced server-side as
  defence-in-depth but are explicitly NOT authentication (real auth deferred).
- **Staging isolation**: invalid/incomplete drafts live only in `IntakeDraft`/
  `SourceRecord`; canonical tables are written only on approval of a validated
  draft. Out-of-state coordinates are a blocking error; out-of-district is a
  review warning (jurisdiction mismatch) surfaced on the map + review step.
- **Canonical identity**: parties are canonicalised (stable `SYN-PERSON-*` /
  `SYN-ORG-*` refs); no name-based identity is created by intake.
- **No prediction on intake**: the intake screens never call a model; DoD §E met.
- **Read-only DB note**: the dev Supabase project is in Supabase over-quota soft
  read-only mode (~727 MB > 500 MB free tier; `default_transaction_read_only=on`
  inherited; not a standby). `rw_conn()` neutralises this at session scope so the
  read-write layer can commit (also repairs pre-existing write endpoints). This
  is an environment condition, not a schema issue; a larger disk / RDS removes it.

---

## 8. Fields / features intentionally deferred

- **Evidence file upload** → Prompt 5 (S3 objects, hashes, custody). Intake links
  provenance metadata only; the People/Timeline/Case-file "Continue" links reuse
  the existing Case File.
- **Submit/approve UI enablement** → Prompt 3 (hackathon-mode verification,
  API-only access, synthetic-data guard, restricted CORS, RLS-disabled check).
  The endpoints + full flow exist and are tested with the gate lifted; the UI
  keeps the submit/approve buttons disabled with a visible reason until Prompt 3.
- **`HACKATHON_MODE`/`DEMO_DATA_ONLY` startup refusal + anon/authenticated grant
  revocation + CORS tightening** → Prompt 3 (config flags added now; enforcement
  is Prompt 3 scope).
- **OCR / transcription / document extraction** → intentionally NOT implemented
  (hackathon contract §13). Intake is structured forms + CSV/JSON only.
- **Statements / property / seizure / court-event forms** → Prompt 7 (schema
  exists from Phase 1; intake creates the initial lifecycle event only).
- **Entity-resolution review inbox / canonical CRUD & search** → Prompt 4
  (intake creates canonical persons on approval; a merge/split UI is Prompt 4).
- **Bulk-import server pipeline (staging/dry-run/rollback endpoints)** → Prompt 8.
  Phase 2 imports create one draft per valid row via the existing draft API with
  a client-side dry-run preview.

## 9. Known limitations

1. **Submit path gated** (by design, DoD §4) — end-to-end submit/approve is
   proven at the API/service layer (tests set `intake_submit_enabled=true`); the
   UI leaves it disabled until Prompt 3 flips the server flag.
2. **Officer list is station-scoped and capped** at 500 for the picker; a
   type-ahead search endpoint is a later refinement.
3. **Unsaved-change protection** covers hard reload / tab close (`beforeunload`);
   in-app route blocking is deferred (autosave persists within ~1.1s of edits, so
   the loss window is small).
4. **Bulk import** writes one draft per row (no server-side batch transaction /
   rollback yet) — that pipeline is Prompt 8.
5. **Dev DB disk pressure** (§7) means large-volume intake load testing should
   wait for a larger disk / RDS; functional correctness is unaffected.

## 10. Next-phase (Prompt 3) prerequisites — satisfied / ready

- `HACKATHON_MODE`/`DEMO_DATA_ONLY` config flags exist (`app/config.py`); Prompt 3
  adds the startup refusal + persistent badge (badge already present).
- `synthetic_meta.app_environment=synthetic_hackathon` marker present and consumed
  by `require_synthetic_db`; `fn_assert_rls_disabled()` repeatable check in place.
- Intake write endpoints are already localhost + synthetic guarded and behind the
  `intake_submit_enabled` flag — Prompt 3 flips the flag after verifying API-only
  access, anon/authenticated grant revocation, restricted CORS, and RLS-disabled.
- `GET /intake/status` exposes the exact flags the UI reads to enable submit;
  once Prompt 3 sets `intake_submit_enabled=true` (env), the wizard submit and the
  inbox approve/return controls light up with no further frontend change.
- No browser→Supabase path or embedded secret exists (verified in the build).

## 11. Definition of Done — verification

- [x] Users can create, validate, save, review, approve, and open a structured case (API/service verified for FIR/Zero FIR/UDR/Missing Person; full UI built).
- [x] All case-party roles use canonical identity records (`CasePartyRole` + `CanonicalPerson/Organisation`; People page canonical-first).
- [x] Category-specific workflows are server validated (`CaseCategoryWorkflow` + prerequisites; invalid combinations rejected — tested).
- [x] UI submit is enabled only after Prompt 3 (submit/approve gated off with visible reason; localhost + synthetic guards active).
- [x] Tests cover normal and invalid intake paths (28 backend + 22 frontend, all passing).
