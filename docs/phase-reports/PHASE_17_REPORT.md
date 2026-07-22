# PHASE 17 — Disaster Response (Emergency Response context)

Status date: 2026-07-19
Owner: implementation agent (Kiro)
Scope: a separate **Emergency Response** context that turns synthetic (or
approved digital) hazard feeds into reproducible **area-level** forecasts with
visible uncertainty, **human-approved** resource plans and **safe** evacuation-
route proposals — reusing the DRISHTI Catalyst/AWS spine (Data Store, Stratus,
Signals, AlertHistory, ModelVersion, the Investigation Board, the map stack).

> **Honesty note (read first).** Everything below is **IMPLEMENTED and locally
> verified** unless explicitly marked **SCAFFOLDED** (artifact committed, cloud
> step held) or **BLOCKED / External Access Required** (needs a credential or
> access this environment does not have). Disaster records are **Data Store-
> native** (created directly in Catalyst Data Store, populated by the AppSail
> disaster service at runtime) — exactly like the Prompt 16 board. In dev/tests
> the Catalyst services run through their in-memory fakes (Data Store / Cache /
> Signals / Stratus). AWS RDS/PostGIS/pgRouting is the **optional, reconstructable
> analytics mirror**, never the submitted app's operational store. This is a
> **synthetic hackathon decision-support demonstration — not an official warning,
> dispatch or evacuation system.**

---

## 0. Executive status

| Area | State |
|---|---|
| Emergency Response context (switcher + 5 destinations, URL-preserved) | **DONE** |
| Data Store operational schema (14 disaster tables, Data Store-native) | **DONE** |
| Optional AWS PostGIS/pgRouting analytics mirror (`sql/023_disaster_response.sql`) | **DONE (SQL)** / deploy **HELD** |
| `AlertHistory` reuse (+nullable `HazardEventID`, +hazard alert types) | **DONE** |
| Synthetic Karnataka datagen (`datagen/disaster.py`) — 19 scenarios | **DONE** |
| Pluggable feed ingestion (connector interface + synthetic replay) | **DONE** |
| **Read-only LIVE feed connector (Open-Meteo, no API key, CC BY 4.0) end-to-end** | **DONE (LIVE, verified)** |
| Official-gauge connector contract (IMD/KSNDMC recorded sample) | **DONE** / official-gauge live access **External Access Required** |
| Hazard baselines for all 9 HazardTypes | **DONE** |
| MVP validated forecast path (flood) vs persistence/seasonal baselines | **DONE** |
| Forecast pipeline (snapshot → baseline → validate → prediction → review → alert proposal) | **DONE** |
| Weighted-greedy allocator + capacity/no-double-allocation; OR-Tools optional | **DONE** / OR-Tools **OPTIONAL** |
| Versioned road graph + hazard-avoiding evacuation route + explicit no-route | **DONE** |
| Response plans / tasks (per-hazard SOP checklists) | **DONE** |
| `disaster_coordinator` role + district scope + fresh-confirmation + audited allow/deny | **DONE** |
| Signals (`feed.stale`/`forecast.completed`/`alert.review_required`/`allocation.approved`) | **DONE** |
| Investigation Board integration (Send to Board for 7 hazard object kinds) | **DONE** |
| Tests (29 disaster + board/mapping) | **DONE** — 29 pass |
| Catalyst Slate/AppSail/Data Store/Stratus/Signals **cloud deploy** | **SCAFFOLDED / HELD** (credit-spending; Phase 14 posture) |
| AWS SageMaker (TimesFM) / AWS Batch (OR-Tools/pgRouting backfill) | **SCAFFOLDED / HELD** (GPU + AWS spend) |

---

## 1. Files created / changed

### 1.1 Data Store schema (Data Store-native; no operational PG migration)
- `services/ml/app/datastore/disaster_schema.py` — **single source of truth** for
  the 14 Data Store-native disaster tables (columns/types/indexes/search/append-
  only + JSON/GeoJSON size limits). Append-only: `HazardPrediction`,
  `HydroMetReading`, `DisasterActivity`.
- `services/ml/app/datastore/mapping.py` — promoted the disaster tables from
  `RESERVED` to `Disposition.DATASTORE_NATIVE` (Prompt 17 removed from
  `RESERVED_NAMESPACES`/prefixes, matching how Prompt 16 went live);
  `datastore_native_tables(domain=…)` optional filter; `MAPPING_VERSION`
  bumped to `2026.07.19-2`.

### 1.2 Optional AWS analytics mirror (retained corpus / geospatial)
- `services/ml/sql/023_disaster_response.sql` — additive, idempotent PostGIS/
  pgRouting mirror keyed by the same stable `ExternalID`s: `HazardType`,
  `HazardEvent`, `HazardPrediction`, `HazardRiskZone`, `HydroMetReading`,
  `Resource`, `ReliefShelter`, `ResourceAllocation`, `EvacuationRoute`,
  `ResponsePlan`, `ResponseTask`, `FeedSource`, `FeedIngestionRun`, plus the
  separate geographic road topology `DisasterRoadNode` / `DisasterRoadEdge`
  (pgr_dijkstra-compatible). Reuses `AlertHistory` via an **additive nullable
  `HazardEventID`** + hazard `alert_type_enum` values (`flood_warning`, …). GiST
  indexes exist **only** here. RLS/FORCE RLS stay **disabled** (no policy).

### 1.3 Backend — `services/ml/app/disaster/`
`__init__.py`, `geometry.py` (pure-python haversine / ray-cast PIP / segment
intersection / GeoJSON validation), `repo.py` (Data Store persistence, id
allocation, soft-delete, append-only activity), `guards.py` (`disaster_coordinator`
role + permissions + district scope + fresh-confirmation + audited denials),
`schemas.py`, `feeds.py` (connector interface + synthetic-replay + recorded-
sample connectors + idempotency/unit-conversion/quality/DLQ + freshness),
`models.py` (9 hazard baselines + immutable FeatureSnapshot + fusion + fail-safe
confidence/staleness + flood validation), `allocation.py` (weighted-greedy +
capacity + no-double-allocation + optional OR-Tools), `routing.py` (versioned
synthetic road graph + hazard-aware Dijkstra + no-route), `service.py`
(orchestration + lifecycle + audit + Signals), `seed.py` (loads the datagen
fixture), `router.py` (31 routes). Registered in `main.py`; `signals.py` gained
4 events.

### 1.4 Datagen
- `datagen/disaster.py` — deterministic standalone fixture generator (uses the
  vendored Karnataka boundaries for spatial containment; no DB). Emits
  `datagen/fixtures/golden-001/disaster_response.json`.

### 1.5 Frontend — `web/src/`
- `config/roles.ts` (+`disaster_coordinator`), `auth/roleMapping.ts`,
  `config/destinations.tsx` (workspace context + 5 ER destinations +
  `visibleDestinations(role,isAdmin,context)`), `components/shell/
  WorkspaceSwitcher.tsx` + `Sidebar.tsx` (context switcher), `api/client.ts`
  (`setDistrictGetter`), `providers/RoleProvider.tsx`, `stores/useDisasterStore.ts`,
  `api/endpoints/disaster.ts` (+`api/index.ts`), `routes/emergency/*`
  (`erShared.tsx`, `erLayers.ts`, `SituationOverview`, `LiveSituation`,
  `ForecastRisk`, `Resources`, `ResponsePlans`), `App.tsx` routes.
- Board: `components/board/boardEncoding.ts` (disaster node styles).

### 1.6 Investigation Board
- `services/ml/app/board/references.py` — 7 disaster `RefSpec`s +
  `_DATASTORE_REF_TABLES` + `_hydrate_datastore()` (hydrates a pinned hazard/
  resource/route object from the Data Store disaster repo, with a bounded pin-
  time snapshot + integrity hash). `NODE_KINDS` extended.

### 1.7 Tests
- `services/ml/tests/test_disaster.py` (29 tests).

---

## 2. Context & navigation (Prompt 17 §A)

- **Workspace switcher** at the top of the shell: **Crime Intelligence |
  Emergency Response**. The active context lives in the **URL** (`/er…` ⇒
  emergency, else crime), not just local state, so a deep link opens the right
  workspace and back/forward works. `contextForPath()` derives it;
  `visibleDestinations(role,isAdmin,context)` filters the sidebar.
- **Emergency Response destinations (5):** Situation Overview (`/er`), Live
  Situation (`/er/live`), Forecast & Risk (`/er/forecast`), Resources
  (`/er/resources`), Response Plans (`/er/plans`).
- Investigation Board stays in Crime Intelligence; hazard objects can be **Sent
  to a Board** for after-action analysis (§9).
- A distinct **urgent-but-calm disaster palette** (severity tokens + amber/teal/
  green), accessible status labels, and confidence/freshness/synthetic chips —
  deliberately **not** the criminal-person risk visuals.

---

## 3. Data Store tables & row counts (Prompt 17 §B)

14 **Data Store-native** tables (11 required + `FeedSource`, `FeedIngestionRun`,
append-only `DisasterActivity`). ExternalID prefixes: `haztype, hazevt, hazpred,
riskzone, hydromet, resource, shelter, alloc, evacroute, resplan, restask,
feedsrc, feedrun, dact`.

Deterministic demo fixture (`datagen/disaster.py`, seed 42) row counts:

| Table | Rows | Table | Rows |
|---|---:|---|---:|
| HazardType | 9 | Resource | 10 |
| FeedSource | 2 | ReliefShelter | 7 |
| FeedIngestionRun | 2 | ResponsePlan | 1 |
| HazardEvent | 7 | ResponseTask | 6 |
| HazardRiskZone | 6 | AlertHistory (proposed) | 1 |
| HydroMetReading | 42 | | |

`HazardPrediction`, `ResourceAllocation` and `EvacuationRoute` rows are produced
at **runtime** by the forecast/allocation/routing pipelines (not pre-seeded), so
they carry live model/feature/version provenance.

**Indexes / search:** every child table indexes its parent id + status/time/
district access paths; search columns declared on `HazardEvent.Description`,
`Resource.Name`, `ReliefShelter.Name`, `ResponsePlan.Title`, `HazardType`. GiST
spatial indexes exist **only** on the AWS mirror (§4).

**Verification:** `mapping.validate_mapping() == []`;
`test_disaster_tables_datastore_native`, `test_disaster_schema_append_only_and_rls_note`.

---

## 4. Optional AWS PostGIS/pgRouting mirror & reconciliation

`services/ml/sql/023_disaster_response.sql` is the **reconstructable** analytics/
geospatial mirror, keyed by the **same ExternalIDs** as Data Store. It is used
only for the justified advanced geospatial workload (impact overlay, pgRouting
evacuation routing) through the protected AWS adapter — never a browser/AppSail
CRUD path.

- **Reconciliation contract:** Data Store is authoritative; the mirror is rebuilt
  from Data Store rows by ExternalID (count/hash reconciliation reuses the
  Phase-14 bootstrap/cutover contract). No two-way replication, no last-write-wins.
- **Road graph:** a separate geographic topology (`DisasterRoadNode`/
  `DisasterRoadEdge`, osm2pgrouting-shaped, ODbL attribution + extract date) —
  never the entity-intelligence `NetworkEdge` graph.
- **RLS-disabled:** the migration ends with `SELECT fn_disable_rls_all_app();
  SELECT fn_assert_rls_disabled();` and creates **no** `CREATE POLICY`
  (asserted by `test_migration_023_rls_disabled_no_policies`).
- **Deploy state:** **HELD** (credit/DB-spend), consistent with the Phase 14
  posture. The migration is idempotent and safe to apply when an AWS PostGIS/
  pgRouting instance is provisioned.

For the hackathon demo the routing runs on an **in-code deterministic road grid**
(`routing.RoadGraph`, version `osm-ka-demo-grid@2024.10.01`) so the safe-route /
no-route behaviour is fully demonstrable without the AWS mirror; the mirror is
the documented post-hackathon upgrade to a real OSM extract + pgRouting.

---

## 5. Synthetic datagen & scenario coverage (Prompt 17 §C)

`datagen/disaster.py` places every point/polygon **inside the real Karnataka
district polygons** (vendored boundaries) so all geometry passes spatial
containment. **19 scenario keys**, all asserted by
`test_datagen_scenario_coverage_and_containment` + `test_datagen_deterministic`:

`coastal_cyclone_flood` (Dakshina Kannada/Udupi/Uttara Kannada), `ghats_landslide`
(Kodagu/Chikkamagaluru), `north_drought_heatwave` (Kalaburagi/Vijayapura/Bagalkot),
`river_basin_flood` (Cauvery-Mandya / Krishna-Bagalkot / Tungabhadra-Ballari),
`bengaluru_urban_flood`, `normal_no_event`, `stale_feed` (Davanagere — only a 48 h-
old reading), `missing_sensor` (Koppal), `conflicting_readings` (Raichur),
`false_alarm` (Uttara Kannada), `low_confidence_forecast`,
`late_corrected_observation`, `resource_available` / `resource_maintenance` /
`resource_deployed`, `shelter_varying_occupancy` (incl. one **full**),
`blocked_route_hazard` + `alternate_safe_route` (Dakshina Kannada),
`no_safe_route` (Bengaluru Urban — a band separates the zone from all shelters).

**Containment test:** every `Resource`/`ReliefShelter` point and every
`HazardEvent`/`HazardRiskZone` centroid is asserted inside its district polygon.

---

## 6. Feeds, connectors & source decisions (Prompt 17 §D)

Connector interface emits normalized `ReadingCandidate`s + source/version/licence
metadata. Ingestion is **idempotent** (value-in-key), **deduplicating**,
**unit-converting** (ft→m, cm/in→mm, °F/K→°C, m/s/knots→kmph), **geometry-
validating**, **quality-tracked** (`valid|suspect|missing|superseded|late`), with
**observed-at vs received-at**, **late/correction** handling (append-only; latest
received wins by derivation via `resolve_effective`), **in-batch conflict**
detection, a **DLQ** for rejects and **retry** (once) on connector failure. Every
run records a **FeedIngestionRun heartbeat**; freshness is exposed to the UI.

| Connector | Kind | Decision |
|---|---|---|
| `open_meteo_live` | **LIVE** (Open-Meteo) | **Working live connector — verified end-to-end.** Open-Meteo (`https://api.open-meteo.com/v1/forecast`) is a documented, free, **no-API-key** weather API under **CC BY 4.0** (free for non-commercial use) that covers Karnataka. It supplies live precipitation (rainfall), temperature, wind and humidity for 4 Karnataka stations (Mangaluru/DK, Bengaluru, Madikeri/Kodagu, Kalaburagi). Verified: a real call ingested **16 readings** (4 stations × 4 metrics), 0 rejected; re-ingest → 16 duplicates (idempotent); freshness `fresh` with attribution "Weather data by Open-Meteo.com (CC BY 4.0)". No credential is stored; we do not scrape a portal. Gated by an ops kill-switch `DRISHTI_LIVE_FEED_ENABLED`. |
| `synthetic_replay` | deterministic JSON/CSV replay | **Reliable offline demo path** — the required hackathon connector; no network needed. |
| `imd_rainfall_recorded` | recorded sample (IMD/KSNDMC rainfall) | **Official-gauge access = External Access Required.** A documented live endpoint + licence + credential for the official **IMD/KSNDMC/CWC gauge** networks was **not** available at implementation time, so the same connector contract runs against an **approved, versioned recorded sample** (`recorded-2024-07-15`), flagged `ExternalAccessRequired=true` in the freshness banner. |

**Live verification:** `python -m pytest tests/test_disaster.py::test_live_openmeteo_smoke`
with `DRISHTI_LIVE_FEED_TEST=1` makes a real Open-Meteo call → **1 passed** (offline
CI skips it). `test_live_openmeteo_response_mapping_and_ingest` is the deterministic
(no-network) contract test; `test_live_feed_disabled_guard` proves the kill-switch.
The UI **Situation Overview → “Fetch live feed”** button triggers the live ingest and
the freshness banner then shows `open_meteo_live` fresh.

**External Access Required (documented blocker for official gauges only):** live
IMD/KSNDMC/CWC/WRD/GSI/Bhuvan/NASA-FIRMS/FSI **gauge** access requires current
official registration, credential, licence and rate-limit/attribution verification.
When granted, such a connector drops into the same interface (raw approved payloads
→ private Stratus, normalized rows → Data Store; payloads/credentials never logged).
The live Open-Meteo connector already satisfies the "≥1 read-only live connector"
requirement; the deterministic replay remains the reliable offline path.

**Verification:** `test_unit_conversion`, `test_ingest_idempotent_and_dedup`,
`test_ingest_missing_conflict_and_correction`, `test_ingest_retry_dlq_on_connector_failure`,
`test_ingest_rejects_invalid_metric`, `test_feed_freshness_surfaces_stale_and_external_access`.

---

## 7. Models & baseline comparison (Prompt 17 §E/§F)

Transparent baselines first, one per HazardType (all 9 return a probability +
`rule` + factors): flood (rainfall+river threshold), urban_flood (drainage
threshold), landslide (RTM slope+antecedent-rain+susceptibility), drought (SPI
deficit), heatwave (temperature percentile), cyclone (track/cone wind buffer),
forest_fire (dryness/temperature), dam_breach (reservoir level), lightning
(instability). Every forecast is built from an **immutable FeatureSnapshot**
(sha256 id) and stores data-as-of, model/rule version, factors, quality state,
calibrated confidence and horizon. **Fusion** distributes a coarse district
probability over validated susceptibility geometry, retaining both layers with
per-cell confidence ≤ the coarse input.

**MVP validated path — flood** (`models.validate("flood")`, deterministic
time-based holdout, n=120): the transparent threshold model **beats** both
baselines.

| Model | Precision | Recall | False-alarm | Missed | Brier | F1 |
|---|---:|---:|---:|---:|---:|---:|
| **flood-threshold-persistence@1.0.0** | 0.624 | **1.000** | 0.415 | 0.000 | **0.195** | **0.768** |
| persistence baseline | 0.500 | 0.593 | — | — | 0.310 | 0.542 |
| seasonal baseline | 0.000 | 0.000 | — | — | 0.303 | 0.000 |

The safety-appropriate bias is **high recall** (catch every event) with moderate
precision (some false alarms), while clearly beating the baselines on F1 + Brier.
(The eval set is synthetic — replace with a historical backtest post-hackathon.)

**Fail-safe (no automatic all-clear):** a stale or sparse/absent-reading district
never returns "safe" — it returns `quality_state` `stale`/`low_confidence` **with
an escalation to a human**. Verified: `test_stale_feed_forecast_escalates_no_allclear`
(Davanagere → `stale` + "no automatic all-clear"), `test_low_confidence_forecast_escalates`
(Koppal → `low_confidence`), `test_fresh_forecast_ok_and_reproducible_snapshot`
(Dakshina Kannada → `ok`, carries the immutable snapshot id, beats baselines).

---

## 8. Allocation & evacuation routing (Prompt 17 §G)

- **Impact estimation** from hazard geometry × explicitly-versioned synthetic
  population assumptions (`synthetic-impact@1.0.0`).
- **Weighted-greedy allocator:** nearest capable **available** resource under
  capacity/quantity/coverage limits; transparent score (proximity + capacity) +
  reasons. **OR-Tools** is an optional CPU upgrade compared on the same fixture
  (falls back to greedy + a documented note when the package is absent).
- **No double-allocation:** a proposal tentatively reserves capacity so greedy
  never over-proposes; at **human approve** time the invariant is re-checked
  against **committed** allocations only (`committed_quantity`) so two commitments
  can never exceed a resource's quantity. Verified: `test_allocation_capacity_and_unmet`
  (boats capped at available 5, `medical` fully unmet), `test_no_double_allocation_beyond_quantity`
  (second approve → 409).
- **Human-in-the-loop lifecycle:** `proposed → approved → dispatched → enroute →
  onsite → released` (or `rejected`). Approve **and** dispatch require a **fresh
  confirmation** (428 without). Dispatch marks the resource `deployed`; release
  returns it to `available`. Verified: `test_allocation_requires_approval_and_dispatch_confirmation`.
- **Evacuation routing:** versioned road graph + hazard-aware Dijkstra that
  **excludes road edges intersecting the active hazard polygon**; returns an
  explicit **`no_route`** when the hazard disconnects the zone from every shelter.
  A route is never described as guaranteed safe; selecting a route requires a
  fresh confirmation. Verified: `test_evacuation_route_avoids_hazard_and_no_route`
  (Dakshina Kannada: a `proposed` ~9 km route whose polyline **does not cross** the
  hazard polygon; Bengaluru Urban: `no_route`) + `test_routing_unit_open_avoid_noroute`.

---

## 9. Alerts, Signals & Investigation Board (Prompt 17 §I)

- **AlertHistory reuse:** hazard alerts are `AlertHistory` rows carrying a
  `HazardEventID`, confidence, freshness and a `synthetic` flag — **no competing
  alert system**. Threshold/forecast output creates a **`proposed`** alert; a
  demo coordinator must **explicitly confirm** (fresh confirmation) before it
  becomes an active warning. Verified: `test_alert_proposal_requires_human_confirmation`.
- **Signals (post-commit, data-minimized):** `feed.stale`, `forecast.completed`,
  `alert.review_required`, `allocation.approved` (added to `signals.py`
  `_VALID_EVENTS`). No forecast auto-publishes an alert / auto-dispatches / auto-
  clears.
- **Send to Board:** 7 hazard object kinds are pinnable — `hazard_event`,
  `hazard_prediction`, `hazard_risk_zone`, `resource`, `shelter`, `allocation`,
  `evacuation_route`. They hydrate from the Data Store disaster repo as **live
  references with a bounded pin-time snapshot + integrity hash**; allocation
  reasoning added on the board stays a hypothesis/annotation, not source
  evidence. Verified: `test_send_hazard_event_to_board`.

---

## 10. Security / RLS-disabled verification (Prompt 17 authorization)

AWS PostgreSQL **RLS and FORCE RLS remain disabled** and the mirror adds **no RLS
policy**. The access boundary is the **Catalyst-authenticated API + server-side
role middleware** (`app/disaster/guards.py`):

- new synthetic **`disaster_coordinator`** role (+ `super_admin`) holds the
  `disaster_forecast` / `resource_allocation` / `evacuation_plan` permissions;
- ordinary crime roles (investigator/analyst/supervisor/policymaker) get a
  **read-only situational view** (GET 200, mutating POST 403);
- a coordinator may act only inside the **assigned synthetic district**
  (`X-Disaster-District` seat); acting elsewhere → 403; `super_admin` covers all;
- **warning approval, dispatch and evacuation-plan approval** require a **fresh
  authenticated confirmation** (428 without);
- **every allow/deny decision** on a sensitive action is audited (append-only
  `DisasterActivity`, `access.denied` records).

Verified: `test_role_allow_deny_matrix`, `test_denied_decisions_are_audited`,
`test_lifecycle_and_append_only_activity`, and the RLS-posture tests in §3/§4.

---

## 11. Catalyst deployment & AWS external workloads (Prompt 17 §J)

**Catalyst application layer (target):** Slate/Web Client Hosting serves the
Emergency Response React routes; Catalyst Authentication + API Gateway front the
Function facade → AppSail disaster/resource/plan services; **Data Store** is
authoritative for readings/hazards/forecasts/zones/resources/shelters/allocations/
routes/plans/tasks/alert metadata; **Stratus** for raw approved feed snapshots +
after-action reports; **NoSQL/Cache** only for flexible feed envelopes / short-TTL
lookups; **Job Scheduling** for synthetic replay + freshness checks + aggregate
forecasts + cleanup; **Signals + Event Functions** publish the 4 events after
commit; **Circuits** is **UNAVAILABLE in the IN DC** (verified in Phase 14) →
documented **Functions + Job Scheduling** fallback; SmartBrowz for after-action
PDF/map export; Catalyst Mail/Push for non-sensitive summaries; Pipelines deploy/
verify.

**Deploy state:** **SCAFFOLDED / HELD** — the code, schema and jobs are committed
and locally verified against the in-memory Catalyst fakes, but the credit-spending
cloud deploy (Slate/AppSail/Data Store import/Signals/Job Scheduling enablement)
is held pending go-ahead, exactly as recorded for Phases 14–16. The disaster
tables provision through the same repeatable `infra/catalyst/ds-schema` pattern as
the board (an equivalent `disaster-tables.schema.json` generator is the small
remaining infra step).

**AWS external layer (target, HELD):** RDS PostgreSQL/PostGIS/pgRouting for the
retained analytics/geospatial mirror (`sql/023`); S3 only for temporary SageMaker/
Batch I/O; protected API Gateway + Lambda/ECS adapter for private-VPC access;
SQS+DLQ for async ingestion/forecast/allocation; **AWS Batch/SageMaker Batch** for
TimesFM (river-level trajectory) and heavy OR-Tools/pgRouting backfills — **CPU by
default, GPU only when measurement proves it, and stopped after use**; ECR for
pinned images; Secrets Manager/SSM (no static keys); CloudWatch dashboards/alarms;
budgets + automatic shutdown for temporary compute. TimesFM/GPU runs go through the
Prompt 14 AWS Batch/SageMaker batch contract (no idle endpoint) and are **HELD**
(no GPU/AWS spend in this environment).

**Credit/cost:** no new duplicate AppSail/Signals/cron beyond the Phase 14
baseline; the disaster feature reuses the single `drishti-api` AppSail, the
existing Signals publisher and Job Scheduling. No credit was spent this phase
(local fakes only).

---

## 12. Tests & failure exercises (Prompt 17 §K)

`services/ml/tests/test_disaster.py` — **29 tests, all pass** (no DB required;
Data Store/Cache/Signals in-memory fakes; synthetic write-guard forced true):

```
python -m pytest tests/test_disaster.py -q   ->  29 passed
```

Coverage: Data Store-native schema + append-only + RLS-disabled + migration-023
posture; datagen 19-scenario coverage + spatial containment + determinism;
geometry kernel; unit conversion; ingest idempotency/dedup/missing/conflict/late-
correction/retry-DLQ/invalid + derived supersession; all-9 hazard baselines + MVP
flood beats baselines + calibration metrics; fresh-OK vs **stale/low-confidence →
escalate, never all-clear**; alert proposal requires human confirmation; allocation
human approval + fresh dispatch confirmation + capacity/unmet + **no double-
allocation**; **safe-route avoids the hazard polygon** + select-confirm + explicit
**no_route**; lifecycle + append-only `DisasterActivity`; role allow/deny matrix +
out-of-scope 403 + super_admin anywhere + **audited denials**; Send to Board pin +
provenance; feed freshness (stale + External Access Required).

**Full backend suite:** `python -m pytest -q` → **417 passed, 6 skipped, 6
failed**. The 6 failures are **pre-existing, data-state-dependent `@requires_db`
tests in modules NOT touched by Phase 17** (`test_analytics` socio-economic,
`test_graph_hidden` matview, `test_money` ×3, `test_risk` calibration). They fail
because the shared dev DB has `SocialIndicator=0`, `CrimeRiskScore=0`, an empty
hidden-associations matview and no persisted money flags (while
`FinancialTransaction=10977`, `EntityGraph=205670`) — a data-load/refresh gap in
the environment, not a regression. All Phase 17 + board + datastore-mapping tests
pass.

**Frontend:** `npm run typecheck` PASS; `npm run build:fast` PASS.

---

## 13. Screenshots

Captured from the running dev app (`npm run dev` + `uvicorn app.main:app`, then
`POST /disaster/demo/seed` as a coordinator) and attached to the submission deck
rather than committed (the repo keeps no binary UI assets). Reproduce:
`/er` (Situation Overview: readiness KPIs, freshness banner incl. the stale
External-Access feed, active hazards, alert review), `/er/live` (deck.gl hazard/
zone/sensor/resource/shelter/route layers + legend), `/er/forecast` (risk gauge +
factor bars + baseline-vs-model table + Evidence Trail; try Davanagere for the
stale escalation), `/er/resources` (allocation planner → propose → approve/dispatch
+ evacuation route incl. Bengaluru no-route), `/er/plans` (SOP checklists). The
workspace switcher toggles Crime Intelligence ↔ Emergency Response.

---

## 14. Definition of Done — verification

| DoD item | Evidence |
|---|---|
| Separate navigable ER context with all 5 destinations | §2; `destinations.tsx`, `App.tsx`, `WorkspaceSwitcher` |
| Synthetic readings/events/resources cover the required Karnataka scenarios | §5; `test_datagen_scenario_coverage_and_containment` (19 keys) |
| ≥1 approved live-feed connector end-to-end **or** recorded-sample contract + documented blocker | §6; **`open_meteo_live` LIVE connector verified end-to-end (16 real readings)** + `imd_rainfall_recorded` recorded-sample contract for official gauges (External Access Required) |
| One forecast path beats/compares vs a transparent baseline w/ confidence+freshness+evidence | §7; flood F1 0.768 vs 0.542/0.0; `test_mvp_flood_beats_baselines_with_metrics` |
| A threshold/forecast can create a human-reviewed synthetic AlertHistory warning | §9; `test_alert_proposal_requires_human_confirmation` |
| All HazardType values have baselines/fixtures; MVP path has held-out validation | §7; `test_all_hazard_baselines_exist`, `models.validate` |
| Allocator proposes a feasible plan requiring human approval | §8; `test_allocation_requires_approval_and_dispatch_confirmation` |
| Coordinator tracks a resource planned→dispatched→…→released within assigned district | §8/§10; lifecycle test + district scope |
| Evacuation routing avoids the fixture hazard polygon or reports no safe route | §8; `test_evacuation_route_avoids_hazard_and_no_route` |
| Hazard/resource/route objects can be sent to the Investigation Board | §9; `test_send_hazard_event_to_board` |
| Stale/low-confidence never silently all-clears or auto-dispatches | §7/§8; stale+low-confidence escalation tests; no-auto-dispatch (approval+confirm) |
| Deployed via Catalyst Auth/Gateway/Slate/AppSail/Data Store/Stratus/Signals/Job Scheduling | §11 (SCAFFOLDED/HELD; local fakes verified) |
| AWS RDS retained for analytics/geospatial; AWS compute only for justified work; RLS off; no Supabase/OCR/direct browser-DB | §4/§10/§11; migration-023 RLS-disabled test; browser → Catalyst APIs only; no OCR |

---

## 15. Limitations & post-hackathon requirements

- **Cloud deploy HELD** (credit/GPU/AWS spend) — same posture as Phases 14–16.
  Remaining infra step: a `disaster-tables.schema.json` generator/provisioner
  mirroring `infra/catalyst/ds-schema` for the board.
- **Live feed is WORKING** via Open-Meteo (no API key, CC BY 4.0, non-commercial),
  verified end-to-end (16 real readings ingested, idempotent, fresh). It is a live
  **weather-model** provider, not the official IMD gauge network. **Official gauge
  feeds (IMD/KSNDMC/CWC/WRD/GSI/FIRMS/FSI) remain External Access Required** —
  registration/credential/licence/attribution must be verified before use; the
  recorded-sample connector proves that contract and swaps in when granted. The
  deterministic replay remains the reliable offline path.
- **TimesFM / pgRouting / OR-Tools at scale** run through the AWS Batch/SageMaker
  batch + protected-adapter contract (CPU by default; GPU only when measured;
  stopped after use). The hackathon uses transparent CPU baselines + an in-code
  road graph so the full flow is demonstrable without AWS spend.
- **Forecast validation is synthetic** (deterministic held-out) — replace with a
  real historical backtest (time-based + geographic holdouts) before any real use.
- **Not an operational system.** No auto-publish, no auto-dispatch, no auto all-
  clear; every warning/dispatch/evacuation-plan approval is a human, audited,
  freshly-confirmed action. Area/time-period granularity only — never person-level.


---

## Prompt 23 live-evidence addendum (2026-07-23) — additive, historical text unchanged

Live on Catalyst (see `docs/phase-reports/PHASE_23_REPORT.md`):

- The **scheduled forecast job is proven live** — cron `drishti_forecast` (Recursive,
  Daily, `00:10` Asia/Kolkata) → `cron_forecast` fired (execution `48361000000061010`) and
  created a `queued` `forecast-2026-07-22` `PredictionRequest`. This is the disaster/hazard
  forecast dispatch path running on a real Catalyst schedule (bounded, idempotent per
  window; AWS model compute stays on the Prompt 24 plane).
- Disaster records are **Data Store-native**; the Catalyst Data Store operational path is
  proven live (insert + Signal update on `PredictionRequest`).
- **Honest caveat (report §5):** a dedicated Disaster *business* API operation was not
  separately API-captured this session; disaster is a Data Store-backed UI context
  exercised via the live Slate frontend. Nothing was faked.
