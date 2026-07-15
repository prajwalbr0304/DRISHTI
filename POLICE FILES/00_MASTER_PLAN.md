# DRISHTI — Master Plan & Product Blueprint
### An Intelligence Operating System for the Karnataka State Police

> **DRISHTI** (ದೃಷ್ಟಿ — "vision / sight / insight"). The name is the thesis: give every officer, from a station Sub-Inspector to the DGP, a single pane of glass that turns 100,000+ FIRs and their surrounding intelligence into *decisions*.

---

## 0. How to read this blueprint

This is a suite of six documents. Read them in this order, or jump to what you need.

| # | Document | What it answers |
|---|----------|-----------------|
| **00** | **Master Plan** (this file) | What are we building, why, for whom, and in what order? The vision, the "Palantir-for-KSP" thesis, the system architecture, and the phased roadmap. |
| **01** | [UX / UI Architecture](01_UX_UI_ARCHITECTURE.md) | Exactly where every page, sub-page, panel, and widget lives. The 8-item sidebar, AWS-style sub-navigation, the widget taxonomy, the design system, role-based views, and 10 out-of-the-box interaction patterns. |
| **02** | [Advanced Technology](02_ADVANCED_TECHNOLOGY.md) | The AI/ML brain. TabFM vs. TabPFN v2, TimesFM, the spatio-temporal model stack, research-paper citations, and a production-grade OSS shortlist. |
| **03** | [Data Visualization](03_DATA_VISUALIZATION.md) | How each *type* of data point is drawn so it is instantly understood. A widget catalogue mapped to libraries. |
| **04** | [Network / Graph Analysis](04_NETWORK_GRAPH_ANALYSIS.md) | The "Neo4j-style" link-analysis engine — architecture options, algorithms, query patterns, and how it rides on the existing Supabase schema. |
| **05** | [Geospatial & Crime-Pattern Analytics](05_GEOSPATIAL_CRIME_ANALYTICS.md) | Hotspot detection and spatio-temporal forecasting that *complements* TabFM's tabular predictions. |

A set of clickable **[HTML mockups](mockups/index.html)** accompanies these documents — open them in any browser to walk the actual screens.

---

## 1. The vision in one sentence

> **Do for the Karnataka State Police what Palantir does for the Pentagon, FBI and CIA** — but built on open, auditable, India-hosted infrastructure, with a user experience so clean that a station officer with 20 minutes of training can use it, and an intelligence layer advanced enough that the client's first reaction is *"how are they doing that?"*

Two things must be simultaneously true, and they usually pull against each other:

1. **Radical clarity.** Police officers are not data analysts. The screen must never overwhelm. Seven-to-eight things in the sidebar. One idea per panel. The *type* of data decides how it is drawn.
2. **Radical capability.** Underneath that calm surface sits foundation-model prediction, graph community detection, spatio-temporal forecasting, semantic case search, and a natural-language + voice interface in English and Kannada.

This blueprint is the plan for holding both at once.

---

## 2. What "Palantir for KSP" actually means

Palantir's real product is not a prettier dashboard. Three ideas make it what it is, and DRISHTI adopts all three, adapted to policing. (Palantir's own engineering writing describes the Ontology as representing *decisions, not just data* — a shared layer that unites data, logic and actions; content rephrased here for compliance.  Source: [Palantir — Ontology-Oriented Software Development](https://blog.palantir.com/ontology-oriented-software-development-68d7353fdb12).)

### 2.1 An object-centric Ontology, not a table browser
The officer never thinks in tables. They think in **objects**: *this person, this case, this vehicle, this gang, this bank account, this location*. Every one of those is a first-class object in DRISHTI with a stable identity, a profile, and a set of relationships. You investigate by **navigating the object graph** — click an accused, see their cases; click a case, see the co-accused; click the co-accused, see the shared address — never by writing a join.

Our Supabase schema already contains the raw material for this ontology:

| Ontology Object | Backed by |
|---|---|
| **Case / FIR** | `CaseMaster` (+ `ComplainantDetails`, `Victim`, `Accused`, `ArrestSurrender`, `ChargesheetDetails`, `ActSectionAssociation`) |
| **Person** (accused / victim / complainant / officer) | `Accused`, `Victim`, `ComplainantDetails`, `Employee`, unified as nodes in `EntityGraph` |
| **Gang / Organized group** | `GangMembership` + `EntityGraph` |
| **Location / Jurisdiction** | `Unit`, `District`, `State`, `CaseMaster.geom` |
| **Financial account** | `FinancialAccount`, `FinancialTransaction`, `TransactionLink` |
| **Relationship / edge** | `NetworkEdge` (pgRouting-shaped: `source / target / cost / reverse_cost`) |
| **Derived intelligence** | `CrimeRiskScore`, `CrimePrediction`, `CrimeHotspot`, `CrimePattern`, `CrimeEmbedding`, `AISummary`, `AlertHistory`, `OfficerRecommendation` |

### 2.2 Decisions and actions live *inside* the objects
Palantir's second idea: the platform is not read-only intelligence. You *act* from it. In DRISHTI, the Investigating Officer viewing a case doesn't switch to another system to add evidence — the **Evidence sub-page has an "Add Evidence" action right there**. The analyst who spots a hidden association can **promote it into an alert**. The supervisor can **assign a lead**. Data-in and intelligence-out share one surface.

### 2.3 The AI is grounded in the Ontology (no hallucinations)
Palantir calls their pattern *Ontology-Augmented Generation* — grounding the language model in the organization's real objects and logic rather than free text (concept rephrased for compliance; source: [Palantir — Logic Tools for RAG/OAG](https://blog.palantir.com/building-with-palantir-aip-logic-tools-for-rag-oag-fdaf8938d02e)). DRISHTI's "Ask DRISHTI" assistant does the same: it translates natural language into **read-only SQL against the real schema**, and every answer carries the exact SQL and the specific record IDs it used as evidence. The assistant cannot invent a column that does not exist, and it cannot state a fact it cannot cite. That is the difference between a demo chatbot and an investigative tool.

---

## 3. Who we are building for (and the one screen that changes per person)

DRISHTI has five built-in roles plus the ability for a Super Admin to mint **custom roles** with per-resource permissions. The genius move for UX is that **the navigation and the Command Center reshape themselves per role** — the same product, five different first impressions.

| Role | Their job | What DRISHTI opens to | Data they must *never* see by default |
|---|---|---|---|
| **Investigator (IO)** | Solve *my* cases | My caseload, my alerts, quick FIR search, "add evidence" | Other jurisdictions' active-investigation detail |
| **Analyst** | Find patterns across cases | Network canvas, forecasting, hotspots, cohorts | (broad read; PII on a need basis) |
| **Supervisor (SHO/SP)** | Oversight & review | Station/district performance, review queue, officer workload | — |
| **Policymaker (senior/govt)** | Strategy & resourcing | Aggregate, **anonymized** trends, forecasts, socio-economic overlays | Any individual PII, any single case/entity detail |
| **Super Admin** | Run the platform | Governance, roles, users, audit, model registry | (full, but every action is audited) |

> **Design rule:** a policymaker and an investigator can stand at the same screen and neither feels the product was built for someone else. See [01 §7 — Role-Adaptive Shell](01_UX_UI_ARCHITECTURE.md).

---

## 4. The information architecture at a glance

Eight top-level destinations (seven for non-admins). Each opens an **AWS-console-style landing page with its own left sub-navigation** for deep detail — never a wall of nested menus. Full detail, per-page layouts, and the widget system are in [Document 01](01_UX_UI_ARCHITECTURE.md).

```
DRISHTI
├── ⌘K  Ask DRISHTI ............ omnipresent command bar (summon from anywhere)
│
├── 1  Command Center .......... role-adaptive home: live map, alerts, my work, KPIs
├── 2  Cases .................... FIR search + object-centric case file
│        └─ Overview · Timeline · Complainant · Victims · Accused · Acts&Sections
│           · Arrests · Chargesheet · Evidence [+add] · Network · Similar · AI Summary
│           · Leads · Evidence Trail
├── 3  People & Entities ........ accused / victim / officer / gang / account profiles
│        └─ Identity · Criminal History · Network · Risk (TabFM) · MO Cluster
│           · Cases · Financial · Locations · Evidence Trail
├── 4  Network Analysis ......... the link-analysis canvas
│        └─ Explore · Communities · Hidden Associations · Money Trail · Path Finder
├── 5  Map & Hotspots ........... geospatial operations
│        └─ Live Map · Hotspots · Forecast · Patrol Planning · Red-Zone Alerts
├── 6  Analytics & Forecasting .. the intelligence dashboards
│        └─ Trends · Crime Patterns · Socio-Economic · Forecasts · Model Explainability
├── 7  Ask DRISHTI .............. full chat + voice workspace, history, saved queries
│
└── 8  Admin & Governance ....... [super_admin only] Roles · Users · Audit · Models · Health
```

Every phase from the project's prompt library maps cleanly onto this structure — nothing is orphaned:

| Feature phase | Lives in |
|---|---|
| 2–5 Conversational NL→SQL, Kannada, voice, PDF export | **7 Ask DRISHTI** (+ ⌘K everywhere) |
| 6 Criminal network, community detection, hidden associations | **4 Network Analysis** |
| 7 Hotspots, trends, seasonal, emerging alerts | **5 Map & Hotspots** + **6 Analytics** |
| 8 Socio-economic correlation | **6 Analytics → Socio-Economic** |
| 9 Offender profiling + TabFM risk scoring | **3 People & Entities → Risk / MO Cluster** |
| 10 Case summary, similar cases, leads | **2 Cases → AI Summary / Similar / Leads** |
| 11 Financial money-trail | **4 Network Analysis → Money Trail** |
| 12 Forecasting + early warning | **5 Map → Forecast / Red-Zone** + **6 Forecasts** |
| 13 Explainable AI / evidence trails | **Cross-cutting** — an "Evidence Trail" surface on every object |
| 14 RBAC + Super Admin | **8 Admin & Governance** |
| 15 Frontend | The whole shell |

---

## 5. System architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLIENT  (React SPA — role-adaptive shell)                                 │
│  shadcn/ui + Tremor · deck.gl/kepler.gl (maps) · sigma.js/Cytoscape (graph)│
│  Web Speech API (voice) · ⌘K command bar · global time-scrubber            │
└───────────────┬───────────────────────────────────────────┬──────────────┘
                │ REST/JSON + WebSocket (live alerts)         │
┌───────────────▼───────────────────────────────────────────▼──────────────┐
│  APPLICATION / API LAYER  (containerized → Catalyst AppSail)               │
│  ┌────────────┐ ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ Auth &     │ │ Conversational │ │ Analytics &  │ │ Explainability   │  │
│  │ RBAC guard │ │ engine NL→SQL  │ │ graph/geo svc│ │ evidence-trail   │  │
│  │ (role_perm)│ │ (read-only)    │ │              │ │ formatter        │  │
│  └────────────┘ └───────┬────────┘ └──────┬───────┘ └──────────────────┘  │
└──────────────────────────┼────────────────┼───────────────────────────────┘
          ┌────────────────┼────────────────┼─────────────────┐
┌─────────▼─────────┐ ┌────▼─────────┐ ┌────▼──────────┐ ┌────▼──────────────┐
│ Supabase Postgres │ │ ML SERVING   │ │ GRAPH ANALYTICS│ │ LLM PROVIDER      │
│ + PostGIS         │ │ TabFM (zero- │ │ Postgres CTE / │ │ (NL understanding,│
│ + pgvector (HNSW) │ │ shot tabular)│ │ Apache AGE /   │ │  summaries) +     │
│ + pg_trgm (FTS)   │ │ TimesFM (ts) │ │ Neo4j mirror   │ │  Kannada support  │
│ + pgRouting       │ │ ST-GNN/Hawkes│ │ (GDS: Louvain, │ │                   │
│ base+intel+chat   │ │ (hotspots)   │ │  PageRank…)    │ │                   │
│ +financial tables │ │              │ │                │ │                   │
└───────────────────┘ └──────────────┘ └────────────────┘ └───────────────────┘
```

Design principles baked into this architecture:

- **Supabase Postgres is the single source of truth.** Everything else is a read-replica, a cache, or a compute layer that writes derived intelligence *back* into typed tables (`CrimeRiskScore`, `CrimePrediction`, `AlertHistory`, …). This keeps the whole system auditable.
- **The graph engine is a tiered choice, not a religion.** Start Postgres-native (recursive CTEs + pgRouting) — it is already in your schema. Add **Apache AGE** (openCypher *inside* Postgres) or a **Neo4j/Memgraph analytics mirror** only when traversal depth demands it. The decision, with benchmarks, is in [Document 04](04_NETWORK_GRAPH_ANALYSIS.md).
- **Prediction is two complementary engines, not one.** TabFM answers *"which districts/offenders are high-risk next period"* (tabular, in-context). A spatio-temporal layer answers *"where exactly will the next hotspot bloom"* (spatial, self-exciting). Why you need both is in [Documents 02 & 05](05_GEOSPATIAL_CRIME_ANALYTICS.md).
- **Every AI output is a typed row with a `ModelVersion` and an input snapshot.** Explainability is not a feature you bolt on; it is the shape of the data.
- **Security is not optional and not silent.** The base schema currently ships with RLS disabled for development speed. Before any networked deployment, RLS must be re-enabled and driven by `role_permissions`. This is flagged again, loudly, in [01 §8](01_UX_UI_ARCHITECTURE.md) and Phase 14.

---

## 6. The technology differentiators (the "how are they doing that?" list)

This is the slide the client remembers. Each item is detailed in the linked document.

1. **Zero-shot foundation-model prediction (TabFM).** No per-district training, no hyperparameter tuning. New data in, calibrated risk out, in a single forward pass. → [02](02_ADVANCED_TECHNOLOGY.md)
2. **A second, spatial brain (self-exciting + ST-GNN hotspot forecasting).** Crime "echoes" — a burglary raises the odds of another nearby within days. We model that near-repeat physics explicitly. → [05](05_GEOSPATIAL_CRIME_ANALYTICS.md)
3. **The hidden-association detector.** Two people who never appear in the same FIR but share an address *and* a bank account get surfaced automatically. This is the "impossible-to-spot-in-Excel" moment. → [04](04_NETWORK_GRAPH_ANALYSIS.md)
4. **Semantic case search.** "Find cases with an MO like this one" via pgvector similarity over `CrimeEmbedding`, not keyword matching. → [02](02_ADVANCED_TECHNOLOGY.md) / [03](03_DATA_VISUALIZATION.md)
5. **Natural-language + voice, in Kannada.** Ask a question by speaking, get a cited answer, export it as a case document. → [01](01_UX_UI_ARCHITECTURE.md)
6. **Provenance on every number.** Click any figure, see the records and the model version behind it. → [01](01_UX_UI_ARCHITECTURE.md) / [03](03_DATA_VISUALIZATION.md)
7. **A global time-scrubber.** Drag a single timeline and the map, the network, and the stats all move together through time. → [01](01_UX_UI_ARCHITECTURE.md)

---

## 7. Phased delivery roadmap

The build phases (0–17) from the prompt library are grouped here into four delivery waves aligned to demonstrable value. TabFM ships in Phase 1 of the AI wave; AI chat/voice agents are explicitly a later phase, matching the client's stated sequencing.

### Wave A — Foundation ✅ (done)
- **Schema** (base FIR + 17 intelligence tables + chat + financial).
- **Synthetic data engine** (100k FIRs, statistically realistic).
- *Status: complete and validated offline.*

### Wave B — The Intelligence Core (the differentiators)
- **Network analysis** (Phase 6): graph build, Louvain communities, N-hop subgraph, hidden-association detector.
- **Geospatial analytics** (Phase 7): DBSCAN/KDE hotspots, trends, emerging-trend alerts.
- **Offender profiling + TabFM #1** (Phase 9): risk scores written to `CrimeRiskScore`.
- **Crime forecasting + TabFM #2** (Phase 12): predictions to `CrimePrediction`, alerts to `AlertHistory`.
- **Spatio-temporal hotspot forecasting** (complement to TabFM — see [05](05_GEOSPATIAL_CRIME_ANALYTICS.md)).
- **Socio-economic correlation** (Phase 8) and **decision support** (Phase 10: summaries, similar cases, leads).
- **Financial money-trail** (Phase 11).
- **Explainability** (Phase 13) threaded through all of the above.

### Wave C — The Human Interface
- **Frontend shell** (Phase 15): the role-adaptive 8-item app in [01](01_UX_UI_ARCHITECTURE.md).
- **Conversational engine** (Phase 2): NL→SQL, read-only, cited.
- **Multilingual** (Phase 3) and **Voice** (Phase 4) and **PDF export** (Phase 5).

### Wave D — Hardening & Delivery
- **RBAC + Super Admin governance** (Phase 14) — re-enable RLS, dynamic role permissions.
- **Dockerize + Catalyst AppSail** (Phase 16).
- **Testing, demo script, pitch** (Phase 17).

> **Later phase (roadmap, not this cycle):** autonomous AI chat & voice *agents* that don't just answer but act — draft a case note, propose a patrol allocation, open an alert — always behind human confirmation and the same evidence-trail contract.

---

## 8. What success looks like

- A station officer finds any FIR and its full object graph in **under 15 seconds**, by typing or speaking, in Kannada or English.
- An analyst surfaces a hidden association across two districts that **no keyword search would ever find**.
- A supervisor sees next week's forecasted hotspots on a map and **moves a patrol**, with the model's confidence and reasoning visible.
- A policymaker reads a socio-economic correlation as **plain-language insight**, never touching a row of PII.
- The Super Admin can **create a new role and restrict a data type in two minutes**, and every one of those clicks is in the audit log.
- At no point does anyone feel the screen is fighting them.

That is DRISHTI: calm on the surface, formidable underneath.

---

*Next: [01 — UX / UI Architecture →](01_UX_UI_ARCHITECTURE.md)*
