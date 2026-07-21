# DRISHTI — End‑to‑End Build Prompt Library

**How to take DRISHTI from an empty repo to a demonstrable, near‑production intelligence platform for the Karnataka State Police — one copy‑paste prompt per phase.**

This file is a *playbook*. Each phase below has an **Objective**, what it **Depends on**, a **Copy‑paste prompt** (give it verbatim to your AI coding agent — Kiro, Claude, Cursor, etc.), and a **Definition of Done**. Run them in order. Do not skip the "golden context block" — paste it at the start of every new session so the agent never loses the plot.

> Source of truth for scope: the six blueprint docs in `POLICE FILES/` (`00_MASTER_PLAN.md` … `05_GEOSPATIAL_CRIME_ANALYTICS.md`). Keep those open; the prompts below reference them.

---

## 0. What already exists (don't rebuild it)

| Asset | File(s) | State |
|---|---|---|
| Base FIR schema (28 tables, PKs/FKs/enums/PostGIS/triggers/views) | `police_fir_schema.sql` | ✅ written, needs applying to Supabase |
| Intelligence layer (17 AI tables, pgvector/pg_trgm/FTS, GIN/GiST/HNSW, matviews, optional pgRouting) | `police_fir_intelligence.sql` | ✅ written, needs applying |
| Synthetic data engine (100k FIRs, criminologically realistic, multiprocessing COPY) | `datagen/`, `generate.py`, `requirements.txt` | ✅ written + offline‑validated |

Everything from Phase 1.5 onward is **new work**.

---

## 1. The golden context block  *(paste FIRST in every session)*

```text
You are a senior engineer building DRISHTI — an object‑centric crime‑intelligence
platform ("Palantir for the Karnataka State Police"). Read these before coding:
  - POLICE FILES/00_MASTER_PLAN.md          (vision, architecture, roadmap)
  - POLICE FILES/01_UX_UI_ARCHITECTURE.md   (8 destinations, design system, roles)
  - POLICE FILES/02_ADVANCED_TECHNOLOGY.md  (TabFM/TimesFM/embeddings/NL→SQL)
  - POLICE FILES/03_DATA_VISUALIZATION.md   (data‑type → widget grammar)
  - POLICE FILES/04_NETWORK_GRAPH_ANALYSIS.md (graph engine + hidden associations)
  - POLICE FILES/05_GEOSPATIAL_CRIME_ANALYTICS.md (hotspots + forecasting)
  - police_fir_schema.sql, police_fir_intelligence.sql (the live schema)

Non‑negotiable ground rules that apply to EVERY phase:
1. Supabase Postgres is the single source of truth. All derived intelligence is
   written back into TYPED tables with a ModelVersion + input snapshot. No files.
2. Every AI output honours the contract:
   { answer, confidence, source_record_ids[], reasoning_summary, model_version }.
3. NL→SQL and all AI DB access run under a READ‑ONLY, whitelisted‑SELECT DB role.
   The model proposes SQL; a guarded executor runs it. Never DDL/DML from a model.
4. Design language = "Calm Authority": one panel = one idea; the data type
   chooses the visual; show provenance always; act where you look. Dark "Ops"
   mode is default. Fixed 12‑hue category palette reused everywhere. No pie>4
   slices, no 3D charts, no dual axes, no rainbow ramps, never colour‑alone.
5. Predictions are decision‑support at area/period granularity, never individual
   targeting; always show confidence; keep a human in the loop; audit everything.
6. RLS is currently DISABLED for dev speed. It MUST be re‑enabled and driven by
   role_permissions before any networked deploy (Phase 14). Treat all PII tables
   (Victim, Accused, ComplainantDetails, Financial*) as sensitive now.
7. Match the existing code style; verify with build/tests before declaring done;
   never invent columns — check the .sql files for exact names/casing.

Confirm you've read the relevant doc(s) for THIS phase, then proceed.
```

---

## 2. Build order at a glance

| Wave | Phases | Outcome |
|---|---|---|
| **A · Foundation** | 0 → 1 → 1.5 | Schema live in Supabase, 100k FIRs loaded, financial/chat/RBAC tables added |
| **B · Intelligence Core** | B0 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 | The differentiators: graph, hotspots, socio‑economic, TabFM risk, similar‑case/leads, money trail, forecasting, explainability |
| **C · Human Interface** | 15a–h → 2 → 3 → 4 → 5 | Role‑adaptive React shell, then NL→SQL chat, Kannada, voice, PDF export |
| **D · Hardening & Delivery** | 14 → 16 → 17 | RBAC + RLS, containerize + deploy, tests + demo + pitch |

> **Prefer a pitch demo first?** Jump to **§Fast Track** — a frontend‑only clickable prototype you can build in a day, then come back and build the real thing.

---

# WAVE A — Foundation

## Phase 0 — Apply the schema to Supabase

**Objective:** get both SQL files running cleanly on a real Supabase Postgres with PostGIS + pgvector.
**Depends on:** a Supabase project; `DATABASE_URL` (Project Settings → Database → Connection string, URI).

```text
Apply the DRISHTI database schema to my Supabase Postgres.

1. Confirm required extensions are available on this Supabase instance: postgis,
   vector, pg_trgm. Report whether pgrouting is available (it is optional).
2. Run police_fir_schema.sql, then police_fir_intelligence.sql, in that order,
   against $DATABASE_URL. Use psql if available, otherwise the Supabase SQL editor
   in ordered chunks.
3. After each file, verify: list created tables, enum types, materialized views,
   and confirm the CaseMaster BEFORE‑INSERT trigger (CrimeNo validation) exists
   and the generated geom / BriefFactsFTS columns are present.
4. Report any statement that failed and fix it in place (do not silently skip).
   Do NOT enable RLS yet — that is Phase 14.

Deliver: a short "schema up" report (table counts by group, extensions, matviews)
and confirmation both files applied with zero errors.
```

**Definition of Done:** 28 base + 17 intelligence tables exist; extensions enabled; matviews created empty; no errors.

---

## Phase 1 — Generate & load the synthetic dataset

**Objective:** populate the DB with ~100k FIRs and all dependent + intelligence data.
**Depends on:** Phase 0; `DATABASE_URL` set; `pip install -r requirements.txt`.

```text
Load the synthetic dataset using the existing generator in datagen/ + generate.py.

1. First do a dry run to confirm logic + distributions with no DB writes:
     python generate.py --dry-run 10000
   Show me the crime‑type Zipf mix, district weighting, and murder hour histogram.
2. Then run the full load into $DATABASE_URL:
     python generate.py --truncate --workers 4 --seed 42
   Targets: ~100k FIRs, ~300k accused, ~250k victims, ~120k complainants,
   ~100k arrests, ~40k chargesheets, plus the full intelligence layer.
3. After load, run verification queries and report actual row counts per table,
   confirm every FK resolves (no orphans), CrimeNo is unique + 18 digits,
   and refresh + sanity‑check the three materialized views.
4. If Supabase connection limits bite, lower --workers and retry; report timing.

Deliver: a row‑count table (actual vs target) and a "data healthy" confirmation.
```

**Definition of Done:** counts within ~±10% of targets; zero orphan FKs; matviews populated; a couple of spot‑check queries look realistic (e.g., Bengaluru dominates cyber).

---

## Phase 1.5 — Schema completion & reconciliation  *(new tables the blueprint assumes)*

**Objective:** add the tables the docs reference but the current schema lacks — **financial sub‑graph**, **conversational/voice**, **RBAC/governance** — and reconcile a few columns. Non‑breaking, additive only.
**Depends on:** Phase 1.

```text
Extend the DRISHTI schema with the tables the blueprint (docs 00, 01, 04) assumes
but police_fir_schema.sql / police_fir_intelligence.sql do not yet contain. Create
a new migration file police_fir_extensions.sql. Match the existing conventions
exactly: quoted PascalCase identifiers, GENERATED BY DEFAULT AS IDENTITY PKs,
TIMESTAMPTZ, FK indexes, GIN on JSONB, GiST on geom, RLS left DISABLED (with the
same loud security note), and COMMENT ON TABLE for each.

Add:
A. Financial sub‑graph (for Phase 11 money trail, ref doc 04 §1):
   - FinancialAccount(AccountID PK, AccountNo, AccountType, HolderName,
     EntityID BIGINT NULL FK→EntityGraph, Bank, IFSC, geom, IsFlagged, Attributes jsonb)
   - FinancialTransaction(TransactionID PK, SourceAccountID FK, DestinationAccountID FK,
     Amount numeric(14,2), TxnTimestamp timestamptz, Channel, IsFlagged, FlagReason,
     EvidenceCaseID INT NULL FK→CaseMaster, Properties jsonb)
   - TransactionLink(...) if useful for many‑to‑many case/txn links.
B. Conversational (for Phases 2–5, ref doc 01 §4.7):
   - ChatSession(SessionID PK, UserID, Role, Language, Title, CreatedAt)
   - ChatMessage(MessageID PK, SessionID FK, Sender enum(user,assistant),
     ContentText, Language, GeneratedSQL, CitedRecordIds jsonb, Confidence,
     ModelVersionID FK NULL, CreatedAt)
   - VoiceTranscript(TranscriptID PK, MessageID FK NULL, RawAudioRef, TranscriptText,
     Language, Confidence, IsLowConfidence bool, CreatedAt)
   - SavedQuery(SavedQueryID PK, UserID, Name, PromptText, Scope jsonb, CreatedAt)
C. Governance / RBAC (for Phase 14, ref doc 01 §4.8):
   - roles(role_id PK, role_name unique, description, is_system bool)
   - users(user_id PK, username unique, display_name, role_id FK, unit_id FK→Unit NULL,
     is_active, must_reset_password, created_at)
   - role_permissions(id PK, role_id FK, resource text, action enum(read,write,none),
     unique(role_id,resource,action))
   - audit_logs(log_id BIGINT PK, user_id FK NULL, action, resource, resource_id text,
     ip_address inet NULL, detail jsonb, created_at) + index on (created_at), (user_id)
D. Reconcile for the ML phases (additive columns, nullable):
   - ALTER TABLE "CrimeRiskScore" ADD COLUMN "AccusedMasterID" INTEGER NULL
     REFERENCES "Accused"("AccusedMasterID");   -- offender‑level risk (Phase 9)
   - ALTER TABLE "NetworkEdge" ADD COLUMN "EvidenceCaseID" INTEGER NULL
     REFERENCES "CaseMaster"("CaseMasterID");    -- edge provenance (Phase 6/11)
   Seed roles + role_permissions with the 5 built‑in roles from doc 01 §7.

Validate the migration parses (sqlglot postgres or a psql dry run), apply it, and
report the new tables. Then extend datagen to populate FinancialAccount/
FinancialTransaction (realistic mule‑account / structuring patterns tied to gang
entities) and a handful of ChatSession/ChatMessage rows for demo. Re‑run the load.
```

**Definition of Done:** `police_fir_extensions.sql` applies cleanly; financial + chat + RBAC tables exist and are seeded; datagen populates financial data with some flagged/structuring patterns; roles seeded.

---

# WAVE B — Intelligence Core

## Phase B0 — ML / analytics service scaffold  *(prerequisite for 6–13)*

**Objective:** stand up the FastAPI service that every downstream ML/analytics phase plugs into, with the read‑only DB role and the shared response contract.
**Depends on:** Phase 1.5.

```text
Scaffold the DRISHTI ML/analytics service per doc 02 §9. Create a `services/ml/`
FastAPI app (containerizable, its own requirements). Requirements:

1. Config from env: DATABASE_URL (full), plus a SEPARATE read‑only connection using
   a restricted DB role. Create the role via SQL:
     CREATE ROLE drishti_readonly NOLOGIN; GRANT USAGE ON SCHEMA public ...;
     GRANT SELECT ON ALL TABLES ... ; (document the exact grants). NL→SQL later uses
     ONLY this role.
2. A shared Pydantic response model AiResult = { answer, confidence: float,
   source_record_ids: list[str], reasoning_summary: str, model_version: str } used
   by every endpoint that returns intelligence.
3. A ModelVersion helper: register/lookup a row in "ModelVersion" and return its id;
   every write to CrimeRiskScore/CrimePrediction/CrimeHotspot/AISummary/AlertHistory
   must include a ModelVersionID and a ModelInference audit row.
4. A batch job runner (CLI entrypoints) + a place for scheduled refresh of the
   materialized views after each write.
5. Health endpoint that reports DB connectivity and extension availability
   (postgis, vector, pg_trgm, pgrouting).
6. Dockerfile + docker‑compose service stub. Do NOT put secrets in the image.

No models yet — just the skeleton, the DB layers (read‑only + read‑write), the
contract, and one trivial end‑to‑end endpoint proving a typed write + audit row.
Add tests for the contract and the read‑only role rejection of a DML statement.
```

**Definition of Done:** service boots; `/health` green; read‑only role blocks DML (tested); a demo endpoint writes one `CrimeRiskScore` + `ModelInference` row with a valid `ModelVersion`.

---

## Phase 6 — Network / graph analysis  *(the "Palantir" engine)*

**Objective:** N‑hop subgraphs, community detection, and the **hidden‑association detector**.
**Depends on:** B0. Read `04_NETWORK_GRAPH_ANALYSIS.md` fully.

```text
Implement the graph‑analysis engine on top of EntityGraph + NetworkEdge
(+ FinancialAccount/Transaction), per doc 04. Start Postgres‑native (Option A).

Endpoints (all return the AiResult contract + typed data):
1. GET /graph/neighbourhood?entity_id&max_hops(≤3)&top_n — recursive‑CTE N‑hop
   subgraph, capped fan‑out by edge weight. Return nodes+edges for the canvas.
2. POST /graph/communities — run Louvain/Leiden in a Python job (networkx/igraph/
   graphology) over EntityGraph+NetworkEdge; WRITE community labels back to
   EntityGraph.Properties and cross‑check detected clusters against GangMembership;
   report precision/recall vs known gangs (the demo metric).
3. GET /graph/path?source&target — shortest path via fn_entity_shortest_path
   (pgRouting) with a CTE fallback if pgrouting is absent.
4. GET /graph/centrality — precompute PageRank + betweenness in a batch job, store
   on the node (Properties), expose ranked "persons of interest".
5. POST /graph/hidden-associations — THE HEADLINE. Materialize nightly into a table
   drishti_hidden_associations: pairs of entities that share ≥2 DISTINCT indirect
   links (same address AND account, shared phone AND vehicle, …) but appear in ZERO
   common FIRs. Each row: entity_a, entity_b, independent_links, link_kinds[],
   proof_record_ids[]. Expose a ranked, pageable feed + a /proof-path endpoint that
   returns the subgraph to highlight.

Cap traversal depth/fan‑out in the API. Index edges both directions (already done).
Precompute expensive metrics in scheduled jobs; the API reads, never recomputes.
Add tests on a small fixture graph with a KNOWN hidden association and assert it's
surfaced. Document how to later swap to Apache AGE (Option B) behind the same API.
```

**Definition of Done:** all endpoints return real data from the loaded graph; communities job writes labels + reports gang precision/recall; a seeded hidden association is detected with its proof path; depth/fan‑out capped.

---

## Phase 7 — Geospatial hotspots, trends & emerging alerts

**Objective:** KDE/DBSCAN hotspots, trend series, and threshold‑breach alerts.
**Depends on:** B0. Read `05_GEOSPATIAL_CRIME_ANALYTICS.md` (Layers 0) and `03 §3`.

```text
Implement descriptive geospatial analytics (doc 05 Layer 0 + Phase 7).

1. Hotspot job: run KDE and ST‑DBSCAN over CaseMaster.geom + IncidentFromDate
   (scikit‑learn DBSCAN, PySAL/PostGIS for KDE), per district & crime head & period.
   WRITE surfaces to CrimeHotspot (geom polygon, Centroid, Intensity, CaseCount,
   PeriodStart/End) with a ModelVersion. Refresh mv_active_hotspots.
2. Trends endpoint: crime volume by head/sub‑head/district over time with MoM/YoY
   deltas; include a rolling‑average band and STL decomposition toggle data.
3. Emerging‑trend alerts: where a cell/category's current count exceeds its historical
   rolling average by a configurable threshold, WRITE AlertHistory rows (Severity,
   Title, Payload, geom) → these drive the map red‑zone pulse + 🔔 feed.
4. All spatial outputs are typed rows with ModelVersion (auditable), not files.
   Provide GET endpoints the map UI will consume (hotspots by bbox+time, trends by
   scope+period, active alerts). Aggregate server‑side; never ship 100k raw rows.

Validate against the known Karnataka patterns in the synthetic data (Bengaluru cyber,
coastal smuggling, border NDPS, festival theft spikes). Report a hit‑rate/PAI‑style
sanity check on held‑out incidents.
```

**Definition of Done:** `CrimeHotspot`/`AlertHistory` populated by jobs; trends endpoint returns anomaly‑banded series; alerts fire on synthetic spikes; matview refreshed.

---

## Phase 8 — Socio‑economic correlation

**Objective:** correlate crime with `SocialIndicator`/`EconomicIndicator`/`WeatherIndicator`, with honest, plain‑language read‑outs.

```text
Implement the socio‑economic correlation analytics (Phase 8, doc 01 §4.6, doc 03 §2.10).

1. Endpoint /analytics/socioeconomic: join district crime rates (per capita, NOT raw
   counts) against SocialIndicator/EconomicIndicator/WeatherIndicator over matching
   periods. Return a correlation matrix + scatter data per crime category.
2. Generate a PLAIN‑LANGUAGE narrative card, e.g. "districts with unemployment above
   X show Y% more property crime — correlational, not causal." The causation
   disclaimer is mandatory and must be part of the payload, not optional UI text.
3. Enforce k‑anonymity: suppress any cell below a small count threshold.
4. Return the AiResult contract so the number is traceable to the underlying rows.
```

**Definition of Done:** correlation endpoint returns matrix + scatter + narrative with the causation disclaimer; small‑N suppression enforced.

---

## Phase 9 — Offender profiling + TabFM risk scoring  *(TabFM #1)*

**Objective:** zero‑shot offender/area risk via TabFM, written to `CrimeRiskScore` with factor attributions.
**Depends on:** B0, Phase 1.5 (`CrimeRiskScore.AccusedMasterID`). Read `02 §2`.

```text
Implement offender risk scoring with TabFM (doc 02 §2, primary engine).

1. Feature builder: per accused (via Accused/ArrestSurrender/ActSectionAssociation/
   CaseMaster) assemble a feature row — prior‑incident count, severity trend, recency,
   MO cluster (from Phase 6/embeddings), district, gang affiliation. Build a stratified
   context sample (few hundred–few thousand rows) so rare habitual‑violent offenders
   are represented.
2. Serve TabFM behind a ModelInterface (so TabPFN v2 is a drop‑in alt, and XGBoost is a
   calibration baseline). Classify risk into a SMALL ordinal set:
   Low / Guarded / Elevated / High / Severe.
3. WRITE results to CrimeRiskScore: AccusedMasterID, RiskScore, RiskLevel,
   ModelVersionID, and Factors jsonb (signed SHAP‑style contributions for the gauge+
   factor‑bars widget). Also write a ModelInference audit row per scoring.
4. Batch path (nightly, all offenders) + on‑demand path (re‑score one entity when its
   profile opens). Refresh mv_district_risk_profile.
5. Treat scores as decision support; store inputs + model version so every score is
   reproducible and contestable. Keep classes bounded; sample rows, don't pass all.

Add a calibration check vs the XGBoost baseline and expose a /risk/{accused_id}
endpoint returning score + factors + provenance.
```

**Definition of Done:** offenders scored into 5 ordinal levels; `CrimeRiskScore` rows carry `Factors` + `ModelVersion`; on‑demand + batch both work; calibration report produced.

---

## Phase 10 — Decision support: summaries, similar cases, leads

**Objective:** grounded AI case summaries, semantic similar‑case search (pgvector), and ranked leads.
**Depends on:** B0. Read `02 §5–6`.

```text
Implement case decision‑support (Phase 10).

1. Similar cases: use CrimeEmbedding (vector(768), HNSW). Endpoint
   /cases/{id}/similar → embed the query case features (multilingual sentence‑
   transformer, keep EmbeddingDim in sync), ORDER BY embedding <=> :qvec LIMIT 5,
   return cases + outcomes + similarity scores. Compute at query time (live corpus).
2. AI Summary: generate a case summary + timeline STRICTLY from linked records
   (CaseMaster + children). Every claim carries an inline citation to a source
   record ID (Ontology‑Augmented Generation pattern). WRITE to AISummary with
   ModelVersion + confidence. No claim without a citation.
3. Leads: rank next investigative steps with the evidence behind each; WRITE to
   OfficerRecommendation (Score, RankOrder, Rationale jsonb, Status). Suggestions,
   not orders.
4. All three return the AiResult contract. Summaries/leads must be reproducible
   (inputs + model version stored).
```

**Definition of Done:** similar‑case search returns ranked results live; AI summaries are fully cited (no uncited claims); leads written to `OfficerRecommendation`.

---

## Phase 11 — Financial money‑trail

**Objective:** multi‑hop transaction tracing with structuring/layering/circular flags, unified with the people graph.
**Depends on:** Phase 1.5 (financial tables), Phase 6. Read `04 §5–7`.

```text
Implement the money‑trail analysis (Phase 11, doc 04 §5 pattern D).

1. /money/trace?account&max_hops — recursive CTE over FinancialTransaction with a
   cycle guard; return the directed weighted flow (for a Sankey) + node/edge data.
2. Detection jobs that FLAG patterns: structuring/smurfing (many transfers just under
   a reporting threshold), layering (long chains), circular flows (cycles). Set
   FinancialTransaction.IsFlagged + FlagReason; surface as AlertHistory where warranted.
3. Unified view: when a FinancialAccount has EntityID, its node joins the same graph
   canvas as its owner (people + money as one network, tables NOT merged).
4. Gate everything behind a "financial" permission (enforced server‑side; wire fully
   in Phase 14). Return provenance (record IDs) on every flagged finding.
```

**Definition of Done:** trace endpoint returns multi‑hop flows with cycle protection; structuring/circular patterns flagged on synthetic data; accounts link into the entity graph.

---

## Phase 12 — Forecasting + early warning  *(TabFM #2 + spatial stack)*

**Objective:** district/beat forecasts (TabFM), count trajectories (TimesFM), near‑repeat + learned spatio‑temporal surfaces, fused on the map.
**Depends on:** Phase 7, 9. Read `05 §2–4` + `02 §4`.

```text
Implement crime forecasting + early warning (Phase 12, doc 05 Layers 1–3 + doc 02 §4).

1. TabFM district/beat forecast: recent per‑district time‑series features + the Phase 8
   socio‑economic overlay as context → next‑period risk class per district. WRITE to
   CrimePrediction (PredictionStart/End, PredictedCount, Probability, Confidence,
   Features) + ModelVersion.
2. TimesFM: per‑area crime‑count trajectory (fan charts). Feeds both the ST model and
   the Analytics forecasts.
3. Near‑repeat (Hawkes/ETAS via `tick` or custom): short‑horizon grid‑cell intensity
   after an event → CrimePrediction. Trigger near‑real‑time when a new FIR lands in a
   watched area.
4. ST‑GNN (PyTorch Geometric Temporal): districts/beats as a graph, learned risk
   surface + spillover, UNCERTAINTY‑AWARE (emit distributions for confidence bands).
5. Fusion rule (transparent, inspectable — not a mystery ensemble): TabFM sets the
   district expectation; spatial layers distribute it over geometry + add near‑term
   spikes. Each predicted cell records contributing models + confidence for the
   Evidence Trail. Provide a layer switcher API so each model can be inspected alone.
6. Early warning: threshold breaches → AlertHistory. Refresh mv_active_hotspots.

Report a PAI/hit‑rate validation on held‑out incidents per district & crime type.
```

**Definition of Done:** `CrimePrediction` populated by TabFM + spatial layers; forecasts carry confidence; fusion is inspectable per layer; PAI validation reported; alerts fire.

---

## Phase 13 — Explainability & evidence trails  *(cross‑cutting)*

**Objective:** make the provenance contract real and uniform across every AI surface.

```text
Harden explainability across all AI outputs (Phase 13, doc 02 §10).

1. Audit every AI endpoint returns { answer, confidence, source_record_ids[],
   reasoning_summary, model_version } — fix any that don't.
2. Guarantee every AI write already created a ModelInference row with the input
   snapshot, so any score is reproducible (same inputs+version → same output). Add a
   /explain/{table}/{id} endpoint that reconstructs the evidence chain for any
   CrimeRiskScore / CrimePrediction / AISummary / AlertHistory row.
3. Risk‑score Factors jsonb must drive the gauge + signed factor bars widget.
4. Model Explainability data: expose calibration/reliability + drift per ModelVersion
   for the Analytics → Model Explainability sub‑page.
5. Add a k‑anonymity + causation‑disclaimer guard as shared middleware so no
   aggregate/exported payload can leak individuals or imply causation.
```

**Definition of Done:** every AI endpoint conforms to the contract; `/explain` reconstructs chains; calibration/drift exposed; shared honesty guards in place.

---

# WAVE C — Human Interface

> Frontend = AWS UI STYLE SIDEBAR AND CUSTOMIZABLE FEATURES/Dashboard , Map:Maplibre, street view:Mappilary , React SPA, Tailwind, shadcn/ui + Tremor, deck.gl/kepler.gl + MapLibre (maps), sigma.js/Cytoscape/React Flow (graph), Recharts/visx/ECharts (charts), vis‑timeline. Read `01_UX_UI_ARCHITECTURE.md` + `03_DATA_VISUALIZATION.md` before every frontend phase. Build the shell first (15a), then destinations.

## Phase 15a — App shell & design system

```text
Build the DRISHTI React app shell + design system per doc 01 §2–3 and doc 03 §5–6.

- Vite + React + TypeScript + Tailwind + shadcn/ui + Tremor. Data layer: a typed API
  client hitting the Wave‑B services (mock adapters where a service isn't built yet).
- Implement the "Calm Authority" tokens as CSS variables for BOTH Ops (dark, default)
  and Desk (light) themes exactly as tabulated in doc 01 §2.1. Inter + Noto Sans
  Kannada, tabular numerals, the 12/13/14/16/20/28/36 scale, 8‑pt grid, 10px card /
  8px control radius.
- The shell: left sidebar (8 destinations, collapsible to icons; 7 for non‑admins),
  top bar (⌘K "Ask DRISHTI" input, global time‑scrubber, theme toggle, 🔔 with count,
  profile/role), breadcrumb bar, workspace grid, and a right‑side PEEK RAIL that opens
  any object reference without navigation (support peek‑within‑peek).
- The universal widget frame (title · context chip · ⓘ · ⋯ · ⤢ · provenance strip)
  as a reusable <Widget> component; the ⌄ provenance strip expands an Evidence Trail
  panel bound to the { confidence, source_record_ids, reasoning_summary, model_version }
  contract.
- The fixed 12‑hue category palette assigned ONCE and exported as tokens; a shared
  chart theme enforcing: no pie>4, no 3D, no dual axes, no rainbow, never colour‑alone.
- A role context/provider (investigator/analyst/supervisor/policymaker/super_admin)
  that the whole shell reads to adapt sidebar + data scope.

Deliver the running shell with themes, sidebar nav, ⌘K, time‑scrubber, peek rail, and
the Widget frame — destinations can be empty states for now.
```

**Definition of Done:** shell runs; both themes work; sidebar/⌘K/peek/time‑scrubber/Widget‑frame all functional; role provider in place.

## Phase 15b–h — The destinations

Give these **one at a time**, each prefixed with the golden block + "read doc 01 §4 and doc 03". Objective per screen is in `01_UX_UI_ARCHITECTURE.md §4`.

```text
[15b] Command Center — role‑adaptive home. Build the four role layouts from doc 01
§4.1 (Investigator caseload+jurisdiction map+KPIs+attention queue; Analyst cohorts+
emerging‑trend feed; Supervisor station/officer performance+review queue; Policymaker
AGGREGATE‑ONLY district KPIs/trends/forecasts — actually swap widgets, don't relabel).
Wire KPI cards, status pipelines, and event lists to the Wave‑B endpoints.
```
```text
[15c] Cases — Case Explorer (filterable dense table + map/table toggle + semantic
"cases like this MO" bar hitting /cases similar) → AWS‑style case file with the full
sub‑nav from doc 01 §4.2. Fully build Overview, Timeline (horizontal typed events),
Network (embedded node‑link), AI Summary (inline numbered citations that scroll to the
cited record), Similar Cases (ranked + similarity bars), Evidence (+ Add evidence
action). Gate write actions to IO; block the whole file for Policymaker with an
explicit "not available for this role" state.
```
```text
[15d] People & Entities — Entity Explorer → profile with sub‑nav (Identity, Criminal
History, Network, Risk (gauge + signed factor bars from CrimeRiskScore.Factors), MO
Cluster, Cases, Financial [permission‑gated], Locations, Evidence Trail). Policymaker
cannot open individual profiles.
```
```text
[15e] Network Analysis — full‑canvas force graph (sigma.js) with mode sub‑nav: Explore
(hop‑by‑hop expand, never a hairball), Communities (Louvain colouring + gang cross‑ref
side list), Hidden Associations (ranked association cards → click draws the proof path
+ evidence trail), Money Trail (Sankey + structuring flags), Path Finder (A→B animated
path). Encoding contract from doc 03 §4 (node size=centrality, colour=type/community,
halo=influence, edge width=strength, style=type). Left filter rail + right peek.
```
```text
[15f] Map & Hotspots — full‑bleed deck.gl/kepler.gl over MapLibre and mappilary for different views, sub‑nav: Live Map
(cluster→point on zoom + 12‑hue legend), Hotspots (KDE/DBSCAN density + time‑of‑day
filter), Forecast (district choropleth by RATE + confidence hatching + horizon
selector 7/14/30), Patrol Planning (beats over forecast + coverage gaps), Red‑Zone
Alerts (pulsing markers — the only looping animation — + ack/assign). Global
time‑scrubber animates hotspots through time. Policymaker capped at district
choropleth, no point pins.
```
```text
[15g] Analytics & Forecasting — Trends (line/area + anomaly band + STL toggle), Crime
Patterns (pattern cards + linked cases), Socio‑Economic (correlation matrix + scatter +
plain‑language narrative WITH the causation disclaimer), Forecasts (fan chart median +
widening confidence band), Model Explainability (model cards + calibration plot).
"Explain this" routes chart context into Ask DRISHTI.
```
```text
[15h] Ask DRISHTI (UI only for now) — focused chat column: composer with 🎙 mic +
language toggle (EN/KN); each answer shows reply, inline numbered citations, a
collapsible read‑only "SQL executed" block, and a confidence chip; sub‑nav Chat /
History / Saved Queries. Also wire ⌘K everywhere to this. Backend comes in Phase 2.
```

**Definition of Done (per screen):** matches its doc‑01 §4 spec; uses the Widget frame + fixed palette + role scoping; interactions from doc 01 §8 present where specified.

---

## Phase 2 — Conversational engine (NL→SQL, read‑only, cited)

**Objective:** turn Ask DRISHTI into a grounded assistant. Read `02 §6`.

```text
Build the NL→SQL conversational engine behind Ask DRISHTI (Phase 2). Non‑negotiable:
- The LLM is given the REAL schema (from the .sql files) and translates a question to
  a single read‑only SELECT. It cannot reference a non‑existent column; ambiguity
  triggers a clarifying question, not a guess.
- A guarded executor: whitelist SELECT only, reject DDL/DML, run under the
  drishti_readonly role (Phase B0), enforce a statement timeout + row cap.
- Results are SCOPED SERVER‑SIDE to the caller's role/permissions — a user must not be
  able to prompt past their access (a policymaker's same question returns aggregate‑
  only). This scoping is NOT in the prompt; it's enforced in SQL/middleware.
- Every answer returns: NL reply, the exact SQL executed, the specific record IDs used
  as citations, and a confidence chip → persist to ChatMessage. Multi‑turn memory
  ("show me HIS other cases") resolves from prior turns via ChatSession/ChatMessage.
- "Explain this" from any chart/hotspot/alert routes its context here for a grounded,
  cited narrative.
Wire it to the Phase‑15h UI. Add tests: injection attempts, DML rejection, and a
permission‑escalation attempt that must fail.
```

**Definition of Done:** NL questions return cited answers with visible SQL; DML/injection/escalation blocked (tested); multi‑turn memory works; scoped per role.

## Phase 3 — Multilingual (Kannada)

```text
Add Kannada support (Phase 3). Auto‑detect EN/KN in the composer; inject a curated
Kannada police/legal glossary (FIR=ಎಫ್‌ಐಆರ್, accused=ಆರೋಪಿ, …) so domain terms
translate correctly; answer in the asked language; test layouts with longer Kannada
strings (Noto Sans Kannada). Kannada is first‑class, not a bolt‑on layer.
```

## Phase 4 — Voice

```text
Add voice (Phase 4) via Web Speech API: 🎙 dictation in EN + KN, TTS reads answers
back in the detected language, stream the text answer while speech synthesizes. Store
transcript + confidence in VoiceTranscript; flag low‑confidence transcriptions.
Gracefully fall back to text where the browser lacks the API.
```

## Phase 5 — PDF export

```text
Add "Export session → PDF" (Phase 5): header with session/case ID, investigator,
timestamp; original + translated query, the answer, and the citations; print‑clean
layout. Also allow exporting a chart/map view. Respect k‑anonymity on any export.
```

---

# WAVE D — Hardening & Delivery

## Phase 14 — Super Admin & Governance console  *(app‑layer RBAC — no RLS yet)*

**Objective:** build the `super_admin` Admin & Governance workspace on top of the RBAC tables from Phase 1.5, gated in the **application layer**. RLS stays **OFF** in this phase (DB‑level enforcement is the deferred Phase 14R below). Read `01 §4.8, §7`.

```text
Build the Admin & Governance destination (Phase 14, super_admin only) per doc 01 §4.8,
using the RBAC tables from Phase 1.5 (roles, users, role_permissions, audit_logs).

IMPORTANT: do NOT enable database RLS, do NOT create/alter DB roles or per‑table
policies in this phase. Access control here is enforced in the APP LAYER only — the
existing permission middleware + role context. The Admin nav item and every admin API
are visible/callable ONLY for super_admin; all other roles keep the existing
"not available for this role" state.

Replace the current /admin placeholder ("Being built in a later Wave‑C phase") with the
real workspace. Sub‑nav:
1. Roles & Permissions — resource×action matrix editor over role_permissions; show a
   clear DIFF before save; creating/editing a custom role takes effect through the
   app‑layer permission checks with no code change.
2. Users — list / create / assign‑role / deactivate; issue credentials with
   must‑reset‑on‑first‑login; filter by unit / role / status.
3. Audit Logs — searchable, filterable view of audit_logs (user, action, resource, time
   range). Every admin write in this console appends an audit_logs row.
4. Model Registry — list ModelVersion; promote / retire (status change) with an audit entry.
5. Data Sources — extension + health readout (postgis, vector, pg_trgm, pgrouting) and
   row counts per major table, from the ML service /health.
6. System Health — service status, last batch‑job run, matview freshness.

Backend: super_admin‑only endpoints for roles/users/permissions/audit CRUD, each writing
an audit_logs row. Enforce the super_admin gate SERVER‑SIDE (not just by hiding the nav).
Tests: every admin endpoint returns 403 for a non‑admin role; a permission change is
reflected in the app‑layer checks; every admin action produced an audit row.
```

**Definition of Done:** `/admin` shows the real Super Admin workspace (6 sub‑pages) for `super_admin` only; roles/users/permissions/audit CRUD work and are audited; non‑admin blocked server‑side (tested); **RLS untouched — still disabled**.

## Phase 14R — Enable RLS & DB‑level enforcement  *(DEFERRED — do before any networked / production deploy)*

**Objective:** harden the access model at the database layer. **Intentionally skipped for now.** Build this only before exposing DRISHTI beyond your local machine. Read `01 §8, §10`.

```text
(DEFERRED — run ONLY before a networked / production deploy.) Turn on database‑level
security. Security‑critical: show the plan and the RLS policy SQL before applying.

1. Re‑enable RLS on all sensitive tables (Victim, Accused, ComplainantDetails,
   FinancialAccount, and intelligence tables that expose PII by inference). Drive
   policies DYNAMICALLY from role_permissions so a new custom role is enforced with NO
   code change. Keep the app‑layer middleware from Phase 14 as a second gate.
2. Ensure Ask DRISHTI runs under the drishti_readonly role and scopes results
   server‑side; require re‑auth for PII‑sensitive queries (victim lookups, financial
   trails); token expiry.
3. Test the matrix: for each role, assert what it can / can't read; assert a policymaker
   cannot reach individual PII by any path (UI, API, or NL query).

Show me the RLS policy SQL and the test matrix results before we call this done.
```

**Definition of Done:** RLS on for all sensitive tables, policy‑driven by `role_permissions`; per‑role access matrix tested (esp. policymaker PII lockout); app‑layer + DB‑layer both enforce.

## Phase 16 — Containerize & deploy

```text
Containerize DRISHTI (Phase 16): Dockerfiles for the web app and the ML service; a
docker‑compose for local (web + ml + reference to Supabase). Prepare deployment to
Catalyst AppSail (or the chosen host) as separate services. Externalize all config +
secrets (no secrets in images). Add a scheduled job runner for nightly batch scoring +
matview refresh. Document env vars and a one‑command local bring‑up.
```

## Phase 17 — Testing, demo script & pitch

```text
Finalize for delivery (Phase 17):
1. Test coverage across the AI contract, RBAC matrix, NL→SQL guards, and the graph/geo
   jobs; a seeded end‑to‑end smoke test.
2. The demo walkthrough from DRISHTI_AI_Studio_Prompt.md §8: (1) Investigator calm
   caseload → (2) open a case + cited AI summary → (3) Network → surface a Hidden
   Association → (4) Map → forecast with honest confidence bands → (5) switch to
   Policymaker → same product becomes aggregate‑only. Make it smooth.
3. A pitch annex: the "how are they doing that?" list (master plan §6) + the research
   bibliography (doc 02 §8) + the responsible‑forecasting stance (docs 02/05).
```

**Definition of Done:** tests green; the 5‑step demo runs end‑to‑end without a hitch; pitch annex assembled.

---

# Fast Track — pitch demo UI in a day (parallel to Wave B)

If you need something to *show* before the backend is done, build the frontend‑only
clickable prototype. **The prompt already exists and is excellent** — use it as‑is:

```text
Open POLICE FILES/DRISHTI_AI_Studio_Prompt.md and build exactly what it specifies:
a single‑page React + Tailwind, mock‑data, role‑adaptive clickable demo of DRISHTI
with Ops/Desk themes, the 8‑item shell, and the five priority screens (Command Center,
Cases, Network Analysis incl. Hidden Associations, Map & Hotspots, Analytics + Ask
DRISHTI). Prioritize the signature interactions (peek panel, time‑scrubber, provenance
→ evidence trail, ⌘K, hop‑by‑hop graph, hidden‑association proof path, role switcher).
No backend. Target the §8 demo walkthrough.
```

Best tools for this fast track: **Google AI Studio "Build"**, **v0.dev**, **bolt.new**, or **Lovable** — paste that prompt, iterate on screens. Then fold the winning screens into the real Phase‑15 shell.

---

# Appendix A — UI inspiration: the shortlist (the "best of" your list)

You collected ~50 sources. For DRISHTI specifically, these **eight** carry 90% of the value — study these, skip the rest:

1. **Palantir Gotham** — the north star: object panels, link analysis, timelines, investigation workspace. → the whole IA.
2. **ArcGIS Operations Dashboard** — interactive map + incidents + heatmaps + filters/layers. → Map & Hotspots.
3. **kepler.gl** — hotspots, hexbins, 3‑D extrusion, time playback. → Hotspots/Live Map (you're using this library anyway).
4. **IBM i2 Analyst's Notebook** — criminal‑network / relationship graphs. → Network Analysis encoding.
5. **Bloomberg Terminal** — dense, dark, information‑rich, tabular numerals (this is the screenshot you saved). → overall Ops‑mode density.
6. **Linear** — density, keyboard‑first feel, calm restraint. → interaction polish + ⌘K.
7. **Perplexity** — inline‑citation pattern. → AI Summary + Ask DRISHTI answers.
8. **Kibana / Grafana / Microsoft Sentinel** (pick one) — SOC alert queue + investigation panels. → Command Center attention queue + Red‑Zone Alerts.

For component/table/form craft when you're stuck: **Ant Design Pro** and **MUI** dashboards. That's it — resist collecting more; you have enough.

---

# Appendix B — Generating reference images of Map & Hotspot sections

I can't render images from here, but you have two good paths:

- **Fastest & most faithful:** run the **Fast‑Track** prompt in **Google AI Studio / v0.dev** — you get *real, interactive* Map and Hotspot screens (better than a static render because you can click them).
- **For static concept renders / mood boards:** paste these into an image model (Midjourney, DAL·E, Google ImageFX, Ideogram). They bake in the DRISHTI design system:

```text
[MAP SECTION]
Dark "operations room" crime‑intelligence map dashboard, full‑bleed map of Karnataka
India with district outlines, clustered incident points resolving to dots, a subtle
red pulsing alert marker, left layer panel, right detail rail, a bottom time‑scrubber,
persistent category legend (12 muted hues), deep navy background #0B1020, panels
#141B2E, indigo‑blue accents #3B82F6, Inter font, tabular numerals, flat 2D, no 3D pie,
serious and precise, Palantir/Bloomberg aesthetic, 16:9 UI screenshot.
```
```text
[HOTSPOT SECTION]
Same dark police dashboard, "Hotspots" view: KDE heat/density surface over Karnataka
with warm gradient blobs on a dark basemap, a time‑of‑day filter, a "Forecast" toggle
showing a district choropleth shaded by risk RATE with diagonal confidence hatching on
low‑confidence districts, horizon selector (7/14/30 days), legend always visible,
navy #0B1020 UI, indigo accents, calm and information‑dense, no rainbow colormap,
flat 2D dashboard screenshot.
```

Reference the collected screenshots in `UI INSPIRATION/` alongside the prompt for style transfer.

---

# Appendix C — One‑line Definition‑of‑Done per phase

| Phase | Done when… |
|---|---|
| 0 | both .sql files applied to Supabase, zero errors |
| 1 | ~100k FIRs + intelligence loaded, no orphan FKs |
| 1.5 | financial + chat + RBAC tables added & seeded |
| B0 | FastAPI up, read‑only role blocks DML, contract + ModelVersion helper work |
| 6 | neighbourhood/communities/path/centrality/hidden‑associations all live; gang precision/recall reported |
| 7 | CrimeHotspot + AlertHistory populated; trends anomaly‑banded |
| 8 | correlation matrix + narrative with causation disclaimer; small‑N suppressed |
| 9 | offenders scored (5 levels) into CrimeRiskScore with Factors + ModelVersion |
| 10 | live similar‑case search; fully‑cited summaries; leads written |
| 11 | multi‑hop money trace + structuring/circular flags; accounts join entity graph |
| 12 | CrimePrediction from TabFM + spatial layers, inspectable fusion, confidence + PAI |
| 13 | every AI endpoint conforms to contract; /explain rebuilds chains; calibration exposed |
| 15a–h | role‑adaptive shell + all destinations per doc 01 §4 |
| 2 | cited NL→SQL, DML/injection/escalation blocked, scoped per role |
| 3 | Kannada first‑class with glossary |
| 4 | voice dictation + TTS, transcripts stored |
| 5 | session/chart → clean PDF, k‑anonymity respected |
| 14 | RLS on & policy‑driven; admin console; per‑role access matrix tested |
| 16 | containerized, deployable, scheduled batch + matview refresh |
| 17 | tests green; 5‑step demo smooth; pitch annex ready |

---

*Build the waves in order. Within a wave, the phases are mostly parallelizable across
people, but 15a (shell) and B0 (service) must land before their siblings. Keep the
golden context block at the top of every session, and keep the six blueprint docs
open — they are the spec these prompts compress.*
