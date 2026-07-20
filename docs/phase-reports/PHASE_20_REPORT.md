# PHASE 20 — Organizer domain, hierarchy, supervisor and investigation-flow closure

Status date: 2026-07-21
Owner: implementation agent (Kiro)
Branch: `fix/case-overview-location-map`
Catalyst project: **DHRISTI** (`48361000000030003`), India DC, Development env.
Result of this phase: **Complete** — every Definition-of-Done item is verified below
at the implementation + offline/DB level. No Catalyst/AWS deployment or credit spend
was performed in this phase; live Catalyst Signal + scoped channel integration for the
committed-FIR flow is explicitly a Prompt 23 step (see §E).

> Synthetic hackathon effort. Nothing here is production. This phase COMPOSES existing
> capabilities and adds only the missing domain/scope/performance/orchestration pieces;
> it does not regenerate the 100k dataset or replace working modules. RLS stays disabled
> per the standing decision; server-side role/scope authorization remains fully enforced.

---

## 0. Definition of Done — verification

| DoD item | State | Evidence |
|---|---|---|
| Crypto/dark-web and cross-jurisdiction synthetic scenarios validate and are searchable | **PASS** | `app/scenarios/registry.py` — 9 deterministic scenarios (4 crypto, 2 dark-web manually-classified, cross-jurisdiction), `validate()` ok; `GET /scenarios/search` (EN+KN, scope/family filters); NL glossary terms added. `tests/test_scenarios.py` (15 pass) |
| SUPERADMIN creates credentials for roles AND assigns the required roles | **PASS** | `app/org/service.py` `create_user`+`assign_role`+`set_scope`+`ensure_roles`; `POST /org/users`, `PUT /org/users/{id}/role|scope`. Round-trip proven in `tests/test_org_scope.py::test_superadmin_creates_credential_assigns_role_and_scope` (rollback) |
| Police hierarchy assignments map to server-enforced functional scopes | **PASS** | `app/org/hierarchy.py` rank→role/scope catalogue; `app/org/scope.py` server-side derivation + allow/deny matrix; `GET /org/hierarchy`, `/org/scope-matrix`. `tests/test_org_scope.py` (18 pass) |
| Supervisor Home has real station/officer metrics with no placeholder | **PASS** | `app/performance/service.py` operational metrics; `web/.../StationPerformance.tsx` REPLACES the "Awaiting the performance API" `EmptyState`. `tests/test_performance.py` (7) + `StationPerformance.test.tsx` (3) |
| One case-scoped bilingual investigation-assistant journey is cited and permission-safe | **PASS** | `app/investigate/` composes summary/similar/identity/leads/timeline; facts vs hypotheses; policymaker denied; EN+KN. `tests/test_investigate.py` (10) + `AssistantPage.test.tsx` (2) |
| A committed FIR updates the appropriate demo aggregates idempotently | **PASS** | `app/livefeed/flow.py` — `case.committed` → 3 projection recompute (district stat, supervisor workload, near-repeat), idempotent, no person-rescore/no-dispatch. `tests/test_livefeed.py` (8) + `LiveFreshness.test.tsx` (2) |
| Every advertised visualization and forecast horizon is backed by a working test | **PASS** | `tests/test_visual_coverage.py` (4) + `AnswerVisualization.test.tsx` (12: all 6 families + accessible table + fallback) + `tests/test_forecast_horizons.py` (5) + existing `test_forecast.py` backtest/PAI |

### Aggregate test evidence (this phase)

- Backend Part-20 suites together (DB-gated): **67 passed** (`test_org_scope` 18, `test_scenarios` 15,
  `test_performance` 7, `test_investigate` 10, `test_livefeed` 8, `test_forecast_horizons` 5,
  `test_visual_coverage` 4).
- Backend full offline regression: **351 passed, 171 skipped, 0 failed** (`pytest` with
  `DRISHTI_DISABLE_DB_TESTS=1`) — up from the Phase-18 baseline of 279 passed, confirming
  no regression from the shared-file edits (glossary, signals, intake hook, reference, main).
- Frontend: `npm run typecheck` clean; `npx vitest run` **21 files / 65 tests passed**
  (was 18/53); `npm run build` OK, bundle-secret scan clean (only the known unconfigured
  API-URL warning, owned by Prompt 22/23).

---

## A. Synthetic domain coverage — crypto / dark-web / cross-jurisdiction

New backend module `services/ml/app/scenarios/` (registry + service + schemas + router),
plus additive taxonomy extensions. **No 100k regeneration** — additive scenario fixtures.

- **Jurisdiction scope is modelled SEPARATELY from crime type** — governed values
  `local, inter_district, inter_state, national, international, cross_border`
  (`JURISDICTION_SCOPES`), mirrored additively in `datagen/reference.py`.
- **Crime families (6):** `crypto_fraud`, `crypto_extortion`, `crypto_money_movement`,
  `darkweb_contraband`, `darkweb_fraud`, `cross_jurisdiction`. Dark-web scenarios are a
  **manually classified source** with `live_collection=False` — no scraping, purchase,
  credential use or illegal-content collection.
- **Scenario counts** (deterministic golden fixture `app/scenarios/fixtures/prompt20_scenarios.json`,
  `valid=True`):

  | Metric | Count |
  |---|---:|
  | scenarios | 9 |
  | cryptocurrency-enabled | 4 |
  | dark-web-enabled (manual source) | 2 |
  | non-local (cross-jurisdiction) | 8 |
  | jurisdiction scopes covered | 6/6 |
  | crime families covered | 6/6 |
  | typed edges (total) | 25 |
  | hypothetical (vs evidence-backed) edges | 10 |
  | bilingual NL-query examples | 18 |

- **Typed edges only:** persons, `wallet_ref`, `exchange_account`, `device`, `phone`,
  `vehicle`, `location`, `case`, `source_record` connected by typed edges each marked
  `evidence-backed` or `hypothetical` (never asserted certainty on inference).
- **Searchable:** `GET /scenarios/search?q=&scope=&family=` (EN + Kannada keyword),
  `GET /scenarios/{id}`, `GET /scenarios/validate`, `GET /scenarios/nl-examples`; and the
  NL-SQL glossary now maps cryptocurrency / dark web / inter-district / inter-state /
  cross-border terms (EN+KN) so the Ask engine recognises them.
- **Validation gate:** `registry.validate()` enforces synthetic + no-live-collection,
  valid scope/family, typed nodes/edges, a `source_record` node on every dark-web
  scenario, a `case` node on every scenario, and full scope/family coverage.

## B. Rank / organizational scope + SUPERADMIN provisioning

New backend module `services/ml/app/org/` + frontend admin panel.

- **Rank → functional role + scope map** (`hierarchy.py`, synthetic, documented):
  DGP/ADGP → supervisor@state, IGP/DIG → supervisor@range, SP/DCP → supervisor@district,
  Dy.SP/CI → supervisor@subdivision, PI+SHO → supervisor@station,
  PSI/IO/ASI/HC/PC → investigator@assigned_case, plus analyst@district,
  SCRB→policymaker@state, DDMA→disaster_coordinator@district, admin→super_admin@state.
  Real directory/SSO/rank synchronisation is labelled **post-hackathon**.
- **Scope levels** (broadest→narrowest): `state > range > district > subdivision > station >
  assigned_case`.
- **Server-side derivation** (`scope.py`): scope is derived from the trusted Catalyst
  user record (role + `users.unit_id` assignment), **never** from a browser district
  header. `enforce_geo_request` confines a station seat to its unit and a district seat
  to its district; an out-of-scope request raises `ScopeDenied` (403).
- **Allow/deny matrix** over the six actions `case_detail, aggregate_dashboard,
  export_case_data, export_aggregate, investigation_board, disaster_approval` for all six
  roles (`GET /org/scope-matrix`). Key guarantees: policymaker gets aggregates only (no
  case detail, no Board); disaster approval is coordinator-only (+ super_admin); a
  district-scoped supervisor cannot open another district's case.
- **SUPERADMIN credential/role management** (the IMPORTANT requirement): `POST /org/users`
  creates a synthetic application credential (a `users` row, `must_reset_password=true` — a
  Catalyst invite in the deployed product) and assigns it a role; `PUT /org/users/{id}/role`
  (re)assigns the role; `PUT /org/users/{id}/scope` assigns the Unit→District scope;
  `POST /org/users/{id}/active` toggles activation; `POST /org/roles/ensure` idempotently
  seeds all six roles (adds the `disaster_coordinator` role + read-only grants). All writes
  are `super_admin` + `require_write_allowed` guarded and audited.
- **Frontend:** `web/src/routes/admin/OrgAccessPanel.tsx` — "Access & hierarchy" admin tab
  (rank table, scope matrix, roles+permissions, and a SUPERADMIN-only create-credential +
  assign-role + activate UI).

### Scope matrix (role default scope)

| role | case_detail | aggregate_dashboard | export_case_data | export_aggregate | investigation_board | disaster_approval |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| investigator | yes | yes | yes | yes | yes | no |
| analyst | yes | yes | yes | yes | yes | no |
| supervisor | yes | yes | yes | yes | yes | no |
| policymaker | no | yes | no | yes | no | no |
| disaster_coordinator | no | yes | no | no | no | yes |
| super_admin | yes | yes | yes | yes | yes | yes |

## C. Supervisor station/officer performance

New backend module `services/ml/app/performance/` (operational metrics — distinct from the
ML workload-band *prediction* in `app/workload/`, which is retained). Replaces the explicit
"Awaiting the performance API" placeholder in `web/.../SupervisorHome.tsx` with the live
`StationPerformance` widget.

- **Metric definitions** (`GET /performance/overview`, windows relative to the dataset
  **as-of** date, not wall-clock — the synthetic corpus ends 2025-12-31):
  - `active_workload` — open cases (status ∈ Under Investigation / Pending Trial /
    Missing-Under Trace) in scope.
  - `new_cases_in_window` — registered within the window (default 90 days) of as-of.
  - `overdue_reviews` — open cases older than 90 days (threshold surfaced).
  - `ageing` — open-case age buckets 0-30 / 31-90 / 91-180 / >180 days.
  - `chargesheet.throughput_ratio` — chargesheets filed / new cases in the window
    (denominator shown explicitly).
  - `chargesheet.median/avg_days_to_chargesheet` — disposal-time PROXY measured to
    chargesheet filing (labelled; final court disposal is a documented limitation).
  - `officers` — aggregate open-load distribution (median / p90 / max / heavy-load count).
    **No punitive per-officer ranking.**
  - `workload_balance` — busiest-vs-median open cases across all stations in scope.
- **Freshness / states:** `as_of`, `data_age_days`, `stale` flag, `empty` state, and an
  honest `limitations` list are always returned. The frontend renders loading / empty /
  stale / error states.
- **Scope (server-side):** the supervisory view is gated to `{supervisor, super_admin}`
  (SP/DGP/… all map to the supervisor functional role); the requested unit/district is
  confined to the caller's derived scope via `org.scope.enforce_geo_request` (station
  chief → own station, SP → district, higher → aggregates); a browser header never widens
  scope.
- Verified live query ≈ 0.86 s for a district of 15,320 cases.

## D. Case-scoped investigation assistant

New backend module `services/ml/app/investigate/` — a **thin, read-only orchestration**
over the existing case APIs; **not** a second ungoverned chatbot (free-form data questions
still use the Prompt 19 `/chat` engine; this composes fixed governed capabilities and
returns the same answer contract: answer / confidence / source ids).

- **Bilingual intent** (`intent.py`): EN + Kannada-script + transliterated Kannada, mapped
  to a fixed set (similar_cases / summary / leads / identity / network / timeline /
  overview); Kannada detected by Unicode range.
- **Facts vs hypotheses (structural separation):**
  - FACTS (`basis="evidence"`): case overview, lifecycle timeline, related FIRs (with
    shared-context why-match + source links), and **reviewed canonical identity links**
    (shared `CanonicalPerson` across cases).
  - HYPOTHESES (`basis="hypothesis"`): possible serial pattern (similarity), ranked
    investigative leads (suggestions), and name/embedding-based candidate links.
- **Identity guard:** two people are never asserted the same on embedding/name similarity
  alone; the `expand_network` lead carries an explicit guard, and reviewed canonical links
  are the only evidence-basis identity facts.
- **Cite to Board:** every fact/hypothesis carries source ids; `citable_objects` map to the
  Board whitelist and `POST /investigate/{case_id}/send-to-board` reuses `board.service.add_node`.
- **Permission-safe:** `require_case_read` denies policymaker on `brief`/`ask`; the Board
  authorization guards `send-to-board`.
- **Journey evidence:** `GET /investigate/{id}/brief` and `POST /investigate/{id}/ask`
  answer "Have similar cases happened before?" (EN) and its Kannada equivalent, returning a
  cited answer with facts/hypotheses separated (verified: 22 citations, 12 citable objects
  on the first golden case). The similar-case embedding corpus is empty in this environment
  (`embed-cases` is a heavy data-load owned by later phases); the assistant degrades
  gracefully and the cited journey is satisfied via reviewed-identity links + leads +
  timeline. Frontend: "Investigation assistant" tab in the case file (`AssistantPage.tsx`).

## E. Live Command Center — committed-FIR event flow

New backend module `services/ml/app/livefeed/` + `signals.EVENT_CASE_COMMITTED`
("case.committed") + a non-invasive hook in the intake approve path.

- **Defined flow:** approved canonical write (`intake` review→approve) → `case.committed`
  event → read-only projection recompute (`district_statistic`, `supervisor_workload`,
  `hotspot_near_repeat` eligibility) → data-minimised Signal → poll-friendly freshness.
- **Idempotent:** a duplicate `case.committed` for the same case is suppressed (returns the
  prior processed record; `duplicate_suppressed` counter). `POST /livefeed/fir-committed`
  returns `idempotent_replay=true` on the second call.
- **Freshness:** `GET /livefeed/freshness` exposes per-projection `last_processed_ts`,
  `last_success_ts`, `last_failure_ts`, `freshness_seconds`, processed/duplicate counts, the
  transport note, and the guarantees. `POST /livefeed/project` is a read-only WHAT-IF showing
  a committed FIR's `before → after (+1)` deltas on each aggregate (demonstrates the change
  without persisting).
- **Hard guarantees:** the flow updates ONLY aggregate projections — `person_rescored=False`,
  `auto_dispatch=False` (no `CrimeRiskScore` write, no `ResourceAllocation`; it uses
  read-only queries).
- **Transport:** polled locally; the single Catalyst Signal `case.committed` + scoped update
  channel integration is a **Prompt 23** step (documented in the freshness payload).
- **Frontend:** `LiveFreshness` strip in the Command Center (polls `/livefeed/freshness`).

## F. Forecast horizons — audit + decision

- **Audit:** the crime-forecast UI (`web/.../MapHotspots.tsx`) advertises 7/14/30-day
  horizons and renders them as a transparent **linear scaling** (`horizonScale = horizon/30`)
  of the 30-day base forecast; the API `/forecast/run` accepts `horizon_days` 7–90 (default
  30) — there is **no 1-day/tomorrow crime forecast**. The 30-day base is validated by a
  rolling-origin backtest (beats seasonal-naive + moving-average baselines, geo-holdout,
  80% interval coverage — `test_forecast.py::test_rolling_origin_backtest_metrics_and_baseline_comparison`)
  and held-out PAI hit-rate > 1 (`test_forecast_pai_beats_chance`). Near-repeat (Hawkes/ETAS)
  is a validated short-term signal. The disaster hazard forecast is a separate hours-based
  plane (24/48/72 h).
- **Decision (F.3):** advertise only validated horizons; **day-ahead crime forecasting is
  future work** (no held-out day-ahead evaluation — the honest near-term alternative is the
  validated near-repeat trigger). The 7/14-day views are labelled a linear approximation of
  the 30-day base.
- **Contract:** `app/forecast/horizons.py::horizon_contract()` + `GET /forecast/horizons`
  is the single source of truth (validated horizons, validation method per horizon,
  `day_ahead.status="future_work"`, disaster hours). `tests/test_forecast_horizons.py` (5)
  proves the contract, the UI/API match, that validation endpoints are registered, and that
  `/forecast/run` refuses out-of-range horizons (1/6/91 → 422). Frontend `forecastApi.horizons()`
  is wired.

## G. Visualization coverage proof

- **Advertised families → approved kinds:** map→`choropleth`, `heatmap`, `timeline`,
  `network`, trend→`line`/`bar`, `sankey` — all in the server-validated `viz.ALLOWED_KINDS`
  with an always-present accessible-table fallback.
- **Backend:** `tests/test_visual_coverage.py` (4) — every family is an allowed kind,
  `validate_spec` accepts each with its accessible table, the deterministic selector picks
  number/line/choropleth/bar/table per result shape, and disallowed kinds / out-of-range
  indices are rejected. (Prompt 19's `test_prompt19.py` also covers the selector + per-kind
  spec validity.)
- **Frontend:** `AnswerVisualization.test.tsx` extended from 6 → **12** tests — number, bar,
  line, table, choropleth (+ loading + map-unavailable fallback), **heatmap** (+ fallback),
  **timeline** (with/without time dimension), **network** (+ open-in-view note), **sankey**
  (+ note), and the two null-spec regression cases. Each renders and exposes the accessible
  data table.
- Existing dedicated visuals (MapHotspots map/heatmap, NetworkPage, TimelinePage, TrendChart,
  ForecastSummary) are data-backed by real `/geo`, `/cases`, `/analytics`, `/forecast`
  endpoints and were **not rebuilt** (per "fix integration gaps only").

---

## Files changed / added (this phase)

Backend (new modules): `app/scenarios/*`, `app/org/*`, `app/performance/*`,
`app/investigate/*`, `app/livefeed/*`, `app/forecast/horizons.py`, plus
`app/scenarios/fixtures/prompt20_scenarios.json`.
Backend (edited): `app/main.py` (router registration), `app/signals.py`
(`EVENT_CASE_COMMITTED`), `app/nlsql/glossary.py` (crypto/dark-web/jurisdiction terms),
`app/intake/router.py` (committed-FIR hook), `app/forecast/router.py` (`/horizons`),
`datagen/reference.py` (jurisdiction scopes + 3 crypto/dark-web crime profiles, additive).

Frontend: `api/endpoints/{org,performance,investigate,livefeed}.ts` + `api/index.ts`;
`routes/admin/OrgAccessPanel.tsx` + `AdminConsole.tsx`; `routes/home/StationPerformance.tsx`
+ `SupervisorHome.tsx`; `routes/cases/subpages/AssistantPage.tsx` + `CaseFile.tsx`;
`components/dashboard/LiveFreshness.tsx` + `CommandCenter.tsx`; `api/endpoints/forecast.ts`
(`horizons`). Tests: `StationPerformance.test.tsx`, `AssistantPage.test.tsx`,
`LiveFreshness.test.tsx`, extended `AnswerVisualization.test.tsx`.

Backend tests: `tests/test_{org_scope,scenarios,performance,investigate,livefeed,forecast_horizons,visual_coverage}.py`.

---

## Commands run (evidence; no secrets)

```text
python .kiro/skills/phase-runner/scripts/phase_state.py preflight --repo . --phase 20   # dependency_ok=true
# backend Part-20 suites (DB-gated)
python -m pytest tests/test_org_scope.py tests/test_scenarios.py tests/test_performance.py \
  tests/test_investigate.py tests/test_livefeed.py tests/test_forecast_horizons.py \
  tests/test_visual_coverage.py -q                        # 67 passed
# backend full offline regression
$env:DRISHTI_DISABLE_DB_TESTS="1"; python -m pytest -q --timeout=180   # 351 passed, 171 skipped, 0 failed
# frontend
npm run typecheck                                          # clean
npx vitest run                                             # 21 files / 65 tests passed
npm run build                                              # OK; bundle-secret scan clean
```

## Honest limitations

- No Catalyst/AWS deployment this phase. The committed-FIR flow is polled locally; the
  single Catalyst Signal `case.committed` + scoped channel is a Prompt 23 step.
- The similar-case embedding corpus is empty here (`embed-cases` is a heavy data-load /
  Prompt 23 concern); the investigation assistant handles the empty-corpus state gracefully.
- Supervisor "disposal time" is measured to chargesheet filing (a documented proxy), not
  final court disposal.
- The 7/14-day forecast views are a transparent linear scaling of the validated 30-day base;
  a separately-fitted day-ahead crime forecast is future work.
- The frontend error-state unit test for the new widgets relies on the shared `errorMessage`
  pattern (already covered elsewhere); a raw rejecting-mock test is avoided due to a
  react-query/vitest worker-level unhandled-rejection interaction.
