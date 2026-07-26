# DRISHTI

<p align="center">
  <img src="web/public/drishti.svg" alt="DRISHTI logo" width="96" />
</p>

<h3 align="center">Decision Intelligence for Public Safety</h3>

<p align="center">
  One governed operational picture for crime intelligence and emergency response—turning fragmented signals into explainable, reviewable and auditable action.
</p>

<p align="center">
  <a href="https://drishti-frvfpunc.onslate.in/"><strong>Open the Catalyst deployment</strong></a>
  ·
  <a href="https://github.com/prajwalbr0304/DRISHTI">View the repository</a>
  ·
  <a href="#prototype-snapshots">See the prototype</a>
</p>

<p align="center">
  <img alt="Catalyst" src="https://img.shields.io/badge/Deployed_on-Zoho_Catalyst-0B6CFB?style=flat-square" />
  <img alt="React" src="https://img.shields.io/badge/React-18.3-61DAFB?style=flat-square&logo=react&logoColor=111827" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5.5-3178C6?style=flat-square&logo=typescript&logoColor=white" />
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-PostGIS_%2B_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white" />
  <img alt="Demo data" src="https://img.shields.io/badge/Data-Synthetic_Demo_Only-7C3AED?style=flat-square" />
</p>

---

## Submission links

| Required item | Link | Submission status |
|---|---|---|
| **Deployed Solution Link—Zoho Catalyst** | **[https://drishti-frvfpunc.onslate.in/](https://drishti-frvfpunc.onslate.in/)** | ✅ Official evaluation deployment; HTTP 200 verified on 26 July 2026 |
| **GitHub Public Repository** | [https://github.com/prajwalbr0304/DRISHTI](https://github.com/prajwalbr0304/DRISHTI) | ⚠️ Repository URL is configured, but an anonymous request returned 404 on 26 July 2026. Change repository visibility to **Public** before final submission. |
| **Demo Video—3 minutes** | **TBD—replace this line with the public video URL before submission** | ⏳ The cinematic hero video is part of the product, but a public three-minute walkthrough URL has not yet been added. |

> [!IMPORTANT]
> The evaluation link above is the Zoho Catalyst Slate deployment. DRISHTI must be evaluated using that link. Do not substitute a deployment on another hosting platform.

> [!NOTE]
> The Catalyst project is named `DHRISTI` in the configured Catalyst account, while the product and repository are correctly branded **DRISHTI**.

---

## Table of contents

1. [Executive summary](#executive-summary)
2. [Problem statement addressed](#problem-statement-addressed)
3. [Brief about the solution](#brief-about-the-solution)
4. [Opportunities](#opportunities)
5. [How DRISHTI differs from existing ideas](#how-drishti-differs-from-existing-ideas)
6. [How the solution solves the problem](#how-the-solution-solves-the-problem)
7. [Unique selling proposition](#unique-selling-proposition)
8. [Key features and functionalities](#key-features-and-functionalities)
9. [Users, roles and use cases](#users-roles-and-use-cases)
10. [Process flow and use-case diagrams](#process-flow-and-use-case-diagrams)
11. [Wireframes and mock diagrams](#wireframes-and-mock-diagrams)
12. [Detailed solution architecture](#detailed-solution-architecture)
13. [Technology stack](#technology-stack)
14. [Zoho Catalyst services used](#zoho-catalyst-services-used)
15. [Data, AI and model-governance approach](#data-ai-and-model-governance-approach)
16. [Security, privacy and responsible use](#security-privacy-and-responsible-use)
17. [Prototype snapshots](#prototype-snapshots)
18. [Prototype performance report and benchmarking](#prototype-performance-report-and-benchmarking)
19. [Proposed impact and use cases](#proposed-impact-and-use-cases)
20. [Estimated implementation cost](#estimated-implementation-cost)
21. [Repository structure](#repository-structure)
22. [How to run the project locally](#how-to-run-the-project-locally)
23. [Testing and release validation](#testing-and-release-validation)
24. [Catalyst deployment model](#catalyst-deployment-model)
25. [Future development](#future-development)
26. [Known constraints](#known-constraints)
27. [Three-minute demo script](#three-minute-demo-script)
28. [Final submission checklist](#final-submission-checklist)

---

## Executive summary

Police and emergency-response teams rarely suffer from a total absence of data. Their harder problem is that data arrives through disconnected case systems, spreadsheets, evidence stores, maps, station records, financial trails, alerts and human reports. Each system exposes only a partial picture, while the officer responsible for a decision must reconstruct the full context under time pressure.

**DRISHTI is an evidence-backed decision-intelligence platform for public safety.** It connects crime records, people, property, digital and financial evidence, geography, operational events and predictive signals into one governed interface. It does not replace an officer's judgement. It prepares the evidence, exposes relationships, quantifies uncertainty, records provenance and keeps a human accountable for the final decision.

The prototype provides two connected workspaces:

- **Crime Intelligence:** case exploration, entity resolution, network analysis, geospatial hotspots, forecasting, investigation boards, evidence trails and natural-language analysis.
- **Emergency Response:** a multi-hazard operational picture for live situation awareness, forecast risk, resources and response plans.

The deployment is designed around **Zoho Catalyst**:

- Catalyst **Slate** serves the React application.
- Catalyst **Authentication** establishes identity.
- Catalyst **API Gateway** and a `gateway_api` function establish the trusted request boundary.
- Catalyst **AppSail** runs the FastAPI service.
- Catalyst **Data Store**, **Stratus**, **Cache**, **Signals**, **Cron**, **QuickML**, **Pipelines** and **Workflows** support the operational plane.
- A protected server-to-server adapter can use AWS PostgreSQL/PostGIS and temporary GPU inference only for workloads that require capabilities not available in the selected Catalyst runtime. No browser receives a database credential or talks directly to AWS.

Every demo record is synthetic. Predictions are decision support, not automatic enforcement. Every material output is designed to remain attributable, reproducible and reviewable.

---

## Problem statement addressed

### Core problem

Public-safety operations are fragmented across organisational, geographic and technical boundaries. A single incident may involve:

- an FIR or complaint;
- multiple victims, complainants, witnesses and accused persons;
- phone numbers, vehicles, bank accounts, devices and property;
- legal sections, arrests, chargesheets, court events and statements;
- CCTV or digital evidence;
- multiple stations, districts and supervisory jurisdictions;
- historical incidents with similar modus operandi;
- hotspots, patrol coverage and time-sensitive operational alerts.

These facts are usually reviewed in different screens or systems. The resulting operational gaps are:

| Gap | Operational consequence |
|---|---|
| **Siloed records** | Officers repeat searches and miss cross-case relationships. |
| **Weak entity resolution** | The same person, phone, account or vehicle appears as separate records. |
| **Poor geographic context** | Case lists do not reveal spatial concentration, jurisdiction gaps or patrol implications. |
| **Opaque analytics** | A risk score without evidence, version and confidence is difficult to trust or challenge. |
| **Manual collaboration** | Investigation reasoning is scattered across screenshots, notes and informal messages. |
| **Delayed escalation** | Supervisors receive information after the operational window has passed. |
| **Limited accountability** | It is difficult to establish who saw, changed, approved or acted on an insight. |
| **Rigid role access** | A state commander, station officer, analyst and investigator need different scopes and workflows. |
| **Disconnected disaster response** | Hazard, resource and crime-intelligence workflows cannot share one governed operating model. |

### Problem statement

> How might Karnataka's public-safety teams transform fragmented operational data into a common, explainable and human-controlled decision picture—without creating an opaque automated policing system?

### Design constraints

DRISHTI treats the following as non-negotiable:

1. **Human authority remains primary.** The system recommends, explains and records; it does not autonomously dispatch, arrest, accuse or alter a case.
2. **Evidence before score.** Every analytic result should expose its inputs, time window, confidence, model/version and source.
3. **Jurisdiction is part of correctness.** A fact outside a user's authorised scope must not be disclosed merely because it is technically retrievable.
4. **Operational and analytical data are separated.** The user-facing serving layer is curated for predictable latency and governance.
5. **Synthetic demonstration data only.** The hackathon prototype must not be interpreted as a production criminal-information system.

---

## Brief about the solution

DRISHTI is a modular command-and-investigation platform that creates a governed ontology over public-safety data. The ontology describes not only records, but the relationships between them:

```text
Case ↔ Person ↔ Role ↔ Phone ↔ Device ↔ Account ↔ Transaction
  ↕       ↕        ↕       ↕       ↕         ↕
Station  Vehicle  Evidence  Place  Statement  Court event
```

The platform turns that connected data into five operational capabilities:

1. **Observe:** unify cases, live events, alerts, resources and maps.
2. **Understand:** resolve entities, expose networks, find similar cases and identify spatial-temporal patterns.
3. **Investigate:** assemble a case's governed network on an interactive board with notes, frames, paths and evidence provenance.
4. **Decide:** present explainable forecasts, alternatives, uncertainty and required human approval.
5. **Audit:** preserve source references, model versions, snapshots, user actions and append-only evidence trails.

The experience begins with a cinematic India-to-Karnataka geospatial landing page, continues through a role-scoped operational view, and leads into connected case, map, graph, analytics and emergency-response workspaces.

---

## Opportunities

### Immediate operational opportunities

- **Reduce search time:** one search surface across cases, people, devices, accounts, vehicles and evidence.
- **Improve case linkage:** reveal shared identifiers, co-occurrence, financial transfers, repeat locations and similar modus operandi.
- **Strengthen supervisory awareness:** show case freshness, workload, alerts and jurisdiction-wide patterns in one command view.
- **Support patrol planning:** translate spatial concentration and time windows into reviewable patrol recommendations.
- **Accelerate investigation hand-off:** send a complete case network—not merely a case number—to an investigation board.
- **Improve audit quality:** preserve where a fact came from and when an analytic result was generated.
- **Unify emergency operations:** apply the same governed, human-controlled architecture to hazards, resources and response plans.

### Strategic opportunities

- State-wide ontology and interoperability standards.
- Kannada and multilingual natural-language access.
- Cross-district collaboration with strict purpose- and role-based controls.
- Privacy-preserving federated analytics across agencies.
- Institution-level model monitoring, backtesting and approval.
- Evidence-integrity integrations using immutable object versions and signed manifests.
- Offline-first field applications for low-connectivity environments.

---

## How DRISHTI differs from existing ideas

DRISHTI is not another dashboard, map, chatbot or isolated prediction model. Its differentiation comes from connecting operational workflows and governance end to end.

| Typical existing approach | Limitation | DRISHTI approach |
|---|---|---|
| **Static BI dashboard** | Aggregates metrics but cannot explain an individual case relationship or support investigation work. | Every metric can lead into cases, entities, sources, geography and governed evidence. |
| **Standalone crime map** | Shows where incidents occurred but not the case network, status, jurisdiction or accountable action. | Map markers open case context; hotspots connect to forecast, patrol planning and red-zone review. |
| **Black-box risk score** | Encourages automation bias and is difficult to contest. | Exposes model/version, inputs, confidence, time window and provenance; requires human review. |
| **Generic graph tool** | Requires manual data preparation and loses the source-of-truth relationship. | “Send to Board” expands a governed case network and pins live references with snapshots. |
| **Case-management system** | Records procedural facts but rarely provides cross-case spatial, network or forecast intelligence. | Combines lifecycle records with graphs, maps, similarity search, analytics and evidence trails. |
| **General-purpose chatbot** | Can hallucinate, over-disclose data or provide untraceable answers. | Ask DRISHTI uses a scoped semantic planner, deterministic query contracts, citations and fail-closed controls. |
| **Automated predictive policing** | Can create feedback loops and transfer authority to an opaque model. | Predictions are limited to decision support; no person re-scoring or auto-dispatch is allowed. |
| **Separate crime and disaster apps** | Duplicates identity, governance, mapping and command workflows. | Two workspaces operate over one governed platform and shared human-control principles. |

### Architectural differentiation

- **Catalyst-first deployment:** the evaluation application is hosted on Zoho Catalyst, with Catalyst as the authentication and operational edge.
- **Ontology-driven interface:** screens are projections of connected objects, not independent pages with copied data.
- **Live reference + pinned snapshot:** investigation-board objects remain linked to governed sources while preserving what the investigator saw.
- **Dual-plane data design:** Catalyst provides the operational serving plane; protected analytical infrastructure is isolated behind the API.
- **Deliberate ML placement:** each model is placed by latency, governance and compute requirement rather than by vendor preference.
- **Reproducible forecasts:** model, feature snapshot, horizon and input lineage are recorded.

---

## How the solution solves the problem

### 1. It unifies fragmented records without flattening their meaning

DRISHTI maps source records into typed objects—case, person, party role, station, evidence, transaction, property, statement and lifecycle event. Relationships retain their meaning, direction and source instead of becoming an unlabelled collection of search results.

### 2. It adapts the experience to operational responsibility

The login gate exposes ten synthetic operational roles. The server derives the real role from the authenticated session and applies a scope such as state, range, district, subdivision, station, assigned cases, cyber cases or administrative access.

### 3. It makes relationships explorable

Users can move from a case to its people, phones, accounts, property, evidence and events; search around an entity; find shortest paths; identify communities; review money trails; and place selected objects on an investigation board.

### 4. It connects maps to case work

The geospatial workspace supports state/district/station boundaries, incident filters, clickable case markers, hotspots, forecasts, patrol planning and red-zone alerts. A point on the map is not a decorative marker—it opens a traceable operational record.

### 5. It turns models into governed evidence

A forecast is stored with its model identity, version, feature snapshot, horizon, timestamp, confidence and provenance. Backtesting and human review are first-class workflows.

### 6. It keeps reasoning collaborative

The investigation board supports:

- governed case-network expansion;
- typed nodes and verified links;
- flow and network layouts;
- sticky notes, frames and text annotations;
- path finding and search-around operations;
- timeline and evidence-trail views;
- history, statistics, sharing, locking and export;
- source inspection without copying or detaching records.

### 7. It preserves accountability

Material transitions are designed to create append-only evidence events. The UI identifies synthetic data, model sources and human-control boundaries. Client-supplied identity headers are removed at the gateway and replaced with signed server context.

---

## Unique selling proposition

> **DRISHTI is a human-controlled public-safety operating system that connects every insight to governed evidence, every model to reproducible provenance, and every decision to an accountable user.**

The USP has four parts:

1. **One operational picture:** cases, entities, maps, networks, forecasts, resources and response plans are connected.
2. **Evidence-backed intelligence:** users can inspect the records and links behind a conclusion.
3. **Human-in-the-loop control:** the system never converts a model output directly into coercive action.
4. **Auditability by design:** identity, source snapshots, mutations, model versions and approvals can be reconstructed.

---

## Key features and functionalities

### Feature matrix

| Module | Key functionality | Operational value |
|---|---|---|
| **Public landing** | Cinematic India/Karnataka operational map, platform narrative and entry point | Communicates the product's purpose and geographic focus immediately |
| **Role selection** | Ten operational roles with scope, officer identity and access description | Demonstrates role-aware views without exposing real credentials |
| **Command Center** | Workload, alerts, urgent events, hotspots, jurisdiction trends, data freshness and recent activity | Gives each role a concise operational briefing |
| **Case Explorer** | Multi-filter FIR search, free-text search, table/map modes and modus-operandi similarity | Reduces time required to find relevant cases |
| **Case File** | Overview, timeline, parties, legal sections, arrests, chargesheet, evidence, statements, property, digital/financial records, court lifecycle and network | Reconstructs the complete governed record |
| **Intake** | FIR creation, staged wizard, import review, quality checks and jurisdiction repair | Improves data quality before operational use |
| **People & Entities** | Entity search, canonical profiles and controlled entity-resolution review | Reduces duplicates and identity fragmentation |
| **Network Analysis** | Explore, communities, hidden associations, money trail, path finder and graph expansion | Reveals non-obvious cross-record relationships |
| **Investigation Board** | Governed network expansion, typed objects, annotations, frames, layouts, evidence trail, timeline, history, statistics, sharing, lock and export | Supports collaborative, explainable investigation reasoning |
| **Map & Hotspots** | Live incident map, point popups, boundary layers, filters, hotspot analysis, forecasts, patrol planning, alerts and fullscreen | Converts spatial patterns into reviewable operations |
| **Analytics & Forecasting** | Trend views, backtesting, model registry, forecast provenance and human review | Makes analytic performance visible and contestable |
| **Ask DRISHTI** | Scoped natural-language questions, deterministic query planning, citations, visual answers and voice confidence gate | Makes complex analysis accessible without bypassing controls |
| **Emergency Response** | Situation overview, live situation, forecast risk, resources and plans | Extends the governed operating picture to multi-hazard response |
| **Admin & Governance** | Roles, model registry, imports, quality, notifications, reports and governance controls | Enables safe operation and institutional oversight |

### Role catalogue

| Role | Default scope | Primary focus |
|---|---|---|
| DGP / State Command | State; all districts | State-wide priorities, trends and readiness |
| ADGP / IGP Range | Range; multiple districts | Cross-district coordination |
| SP / District Command | District; all stations | District workload, alerts and supervision |
| DySP / ACP | Subdivision; circle stations | Subdivision coordination |
| SHO | Station; station cases | Station operations and case management |
| Investigating Officer | Assigned cases; own station | Investigation, evidence and case progression |
| Crime Analyst | State read-across | Patterns, networks, similarity and forecasting |
| Cyber Cell | Cyber cases; state-wide | Devices, accounts, money trails and cyber cases |
| Traffic Command | Traffic corridors | Traffic events, spatial concentration and response |
| System Admin | Governed administrative scope | Identity, imports, models, quality and system controls |

---

## Users, roles and use cases

### Primary users

- State, range, district, subdivision and station command.
- Investigating officers and specialist crime analysts.
- Cybercrime and financial-intelligence teams.
- Traffic and emergency-response command.
- Data-quality, model-governance and system administrators.

### Representative use cases

#### Use case A—motorcycle-theft investigation

1. An officer searches for case `100239`.
2. The case file shows the complainant, victim, accused, legal section, property, station, location, evidence and lifecycle events.
3. “Send to Board” expands the governed case network.
4. The board receives the case and all verified related objects—not only four illustrative nodes.
5. The investigator groups evidence in frames, adds notes, explores associations and inspects source snapshots.
6. Findings are exported or shared while the original records remain governed.

#### Use case B—district hotspot review

1. A district commander opens Map & Hotspots.
2. The role's jurisdiction and date window are applied.
3. The commander filters crime categories and inspects a hotspot.
4. Clicking a point opens case number, gravity, status, location, registration date and a link to the case file.
5. Forecast and patrol-planning views present recommendations with evidence and confidence.
6. A human accepts, modifies or rejects an operational plan.

#### Use case C—cyber money trail

1. Cyber Cell opens a case or account.
2. Network Analysis expands devices, phones, accounts and transactions.
3. Money Trail highlights circular or high-risk flows.
4. Path Finder explains how two entities are connected.
5. Relevant objects are sent to a board with sources and snapshots.

#### Use case D—multi-hazard response

1. Emergency command opens Situation Overview.
2. Live and recorded signals are combined with resources and vulnerable locations.
3. Forecast Risk shows probability, horizon and provenance.
4. Response Plans compare available resources and readiness.
5. The incident commander makes and records the final decision.

---

## Process flow and use-case diagrams

### End-to-end operational process

```mermaid
flowchart LR
    A["Complaint, FIR, import or live event"] --> B["Validate schema, quality and jurisdiction"]
    B --> C["Create or update governed operational objects"]
    C --> D["Resolve people, places, devices, accounts and property"]
    D --> E["Build verified relationships and feature snapshots"]
    E --> F{"Operational question"}
    F -->|Case| G["Case file and lifecycle"]
    F -->|Relationship| H["Network analysis / Investigation board"]
    F -->|Location| I["Map, hotspots and patrol planning"]
    F -->|Trend| J["Analytics, forecast and backtest"]
    F -->|Natural language| K["Ask DRISHTI scoped planner"]
    G --> L["Human review"]
    H --> L
    I --> L
    J --> L
    K --> L
    L --> M{"Officer decision"}
    M -->|Approve or act| N["Controlled operational action"]
    M -->|Modify| O["Record rationale and revised plan"]
    M -->|Reject| P["Record rejection and feedback"]
    N --> Q["Append-only audit and evidence trail"]
    O --> Q
    P --> Q
```

### Use-case diagram

```mermaid
flowchart TB
    DGP["State / Range / District Command"]
    IO["Investigating Officer / SHO"]
    ANALYST["Crime Analyst / Cyber Cell"]
    ER["Emergency / Traffic Command"]
    ADMIN["System and Governance Admin"]

    COMMAND(("Command Center"))
    CASES(("Case Explorer and Case File"))
    MAP(("Map, Hotspots and Patrol Planning"))
    NET(("Network Analysis"))
    BOARD(("Investigation Board"))
    ASK(("Ask DRISHTI"))
    FORECAST(("Analytics and Forecasting"))
    RESPONSE(("Emergency Response"))
    GOVERN(("Identity, Quality and Model Governance"))

    DGP --> COMMAND
    DGP --> MAP
    DGP --> FORECAST
    IO --> CASES
    IO --> BOARD
    IO --> MAP
    ANALYST --> NET
    ANALYST --> BOARD
    ANALYST --> ASK
    ANALYST --> FORECAST
    ER --> MAP
    ER --> RESPONSE
    ADMIN --> GOVERN
    ADMIN --> COMMAND
```

### Investigation-board expansion flow

```mermaid
sequenceDiagram
    actor Officer
    participant Case as Case File
    participant API as FastAPI / Board Service
    participant Store as Governed Data Stores
    participant Board as Investigation Board
    participant Audit as Evidence Trail

    Officer->>Case: Open case 100239
    Officer->>Case: Select "Send to Board"
    Case->>API: Request governed case-network expansion
    API->>Store: Load case, parties, evidence, property, legal and lifecycle links
    Store-->>API: Typed objects + verified relationships + source versions
    API-->>Case: Preview node and link count
    Officer->>Case: Create board and pin
    Case->>API: Persist board objects, links and snapshots
    API->>Audit: Append board creation and pin events
    API-->>Board: Board ID and hydrated graph
    Board-->>Officer: Interactive canvas, inspector and source provenance
```

---

## Wireframes and mock diagrams

The following low-fidelity wireframes describe the information architecture. The [prototype snapshots](#prototype-snapshots) show the implemented high-fidelity interface.

### Role-selection screen

```text
┌──────────────────────────────────────┬──────────────────────────────────────┐
│ DRISHTI                              │ Choose your operational view         │
│ Decision intelligence               │                                      │
│                                      │ ┌──────────────┐ ┌──────────────┐   │
│ ONE OPERATIONAL PICTURE              │ │ State Command│ │ Range Command│   │
│ From first signal to reviewed action │ │ officer/scope│ │ officer/scope│   │
│                                      │ └──────────────┘ └──────────────┘   │
│ ┌────────────────┐ ┌───────────────┐ │ ┌──────────────┐ ┌──────────────┐   │
│ │Crime Intelligence│Emergency Resp.│ │ │ District     │ │ DySP / ACP   │   │
│ └────────────────┘ └───────────────┘ │ └──────────────┘ └──────────────┘   │
│ Evidence-backed · Human-controlled   │ ...six additional role cards...     │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

### Main application shell

```text
┌───────────────┬─────────────────────────────────────────────────────────────┐
│ DRISHTI       │ Search        Time window      Alerts      Role / Scope     │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ Crime / ER    │ Breadcrumbs                                                 │
│               ├─────────────────────────────────────────────────────────────┤
│ Command       │                                                             │
│ Cases         │                  Active workspace                           │
│ Intake        │                                                             │
│ People        │      Cards · Tables · Maps · Graphs · Evidence              │
│ Network       │                                                             │
│ Board         │                                                             │
│ Map           │                                                             │
│ Analytics     │                                                             │
│ Ask DRISHTI   │                                                             │
└───────────────┴─────────────────────────────────────────────────────────────┘
```

### Map & Hotspots

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Live Map | Hotspots | Forecast | Patrol Planning | Red-Zone Alerts | ⛶     │
├────────────────┬────────────────────────────────────────────────────────────┤
│ Map view       │                                                            │
│ Theme / tilt   │     District boundaries                                    │
│ Boundaries     │        • incident markers                                  │
│ Jurisdiction   │              [selected case popup]                         │
│ Crime filters  │                                                            │
│ Time window    │                        Hotspot / station markers            │
│ Severity       │                                                            │
├────────────────┴────────────────────────────────────────────────────────────┤
│ Legend: property · body · cyber · women · traffic · drugs · police station │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Investigation Board

```text
┌──────────────┬──────────────────────────────────────────┬───────────────────┐
│ Filter       │ Flow / Network canvas                    │ Source inspector  │
│ Object types │  ┌──────┐     verified link    ┌──────┐  │ Properties        │
│ Pin object   │  │ Case │──────────────────────│Person│  │ Pinned snapshot   │
│ Add sticky   │  └──────┘                      └──────┘  │ Related records   │
│ Add frame    │       ┌──────── Investigation frame ──┐  │ Provenance        │
│ Add text     │       │ notes, evidence and entities  │  │                   │
│ Path finder  │       └───────────────────────────────┘  │                   │
├──────────────┴──────────────────────────────────────────┴───────────────────┤
│ Table | History | Statistics          Timeline | Evidence Trail | Export    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed solution architecture

### System architecture

```mermaid
flowchart TB
    subgraph Users["Public-safety users"]
        U1["Command roles"]
        U2["Investigators and analysts"]
        U3["Cyber, traffic and emergency teams"]
        U4["System and model administrators"]
    end

    subgraph CatalystEdge["Zoho Catalyst—trusted operational edge"]
        SLATE["Slate\nReact + TypeScript SPA"]
        AUTH["Catalyst Authentication\nIdentity and session"]
        APIGW["API Gateway\n/api routes, CORS and edge policy"]
        GATEWAY["gateway_api function\nStrip client identity headers\nCreate signed role/scope context"]
        APPSAIL["AppSail—drishti-api\nFastAPI application"]
    end

    subgraph CatalystServices["Zoho Catalyst—operational services"]
        DS["Data Store\nCurated serving tables"]
        STRATUS["Stratus\nArtifacts, reports and governed objects"]
        CACHE["Cache\nShort-lived operational acceleration"]
        SIGNALS["Signals / Event functions\nPrediction, evidence, data and report events"]
        JOBS["Cron and Job Scheduling\nForecast and reconciliation"]
        QUICKML["QuickML\nRAG, LLM serving and no-code baseline"]
        WORKFLOWS["Workflows\nHuman-review and lifecycle orchestration"]
        PIPELINES["Pipelines\nValidate, build, secure, deploy and smoke test"]
    end

    subgraph ProtectedAnalytics["Protected analytical plane—server-to-server only"]
        ADAPTER["Governed AWS adapter\nNo browser access"]
        PG["PostgreSQL + PostGIS + pgvector\nHistorical and analytical store"]
        S3["Private S3 evidence objects\nShort-lived exact-object URLs"]
        GPU["Temporary GPU inference\nTabFM, TimesFM and ST-GNN"]
    end

    subgraph Governance["Cross-cutting governance"]
        AUDIT["Append-only evidence and audit trail"]
        MODELS["Model registry, provenance and backtests"]
        GUARDS["Jurisdiction, purpose, rate and payload guards"]
        SYNTH["Synthetic-data and human-control policy"]
    end

    U1 --> SLATE
    U2 --> SLATE
    U3 --> SLATE
    U4 --> SLATE
    SLATE <--> AUTH
    SLATE --> APIGW
    APIGW --> GATEWAY
    GATEWAY --> APPSAIL

    APPSAIL <--> DS
    APPSAIL <--> STRATUS
    APPSAIL <--> CACHE
    SIGNALS --> APPSAIL
    JOBS --> APPSAIL
    APPSAIL <--> QUICKML
    APPSAIL <--> WORKFLOWS
    PIPELINES -.deploys.-> SLATE
    PIPELINES -.deploys.-> APPSAIL

    APPSAIL --> ADAPTER
    ADAPTER <--> PG
    ADAPTER <--> S3
    ADAPTER <--> GPU

    APPSAIL --> AUDIT
    APPSAIL --> MODELS
    APPSAIL --> GUARDS
    APPSAIL --> SYNTH
```

### Trust boundaries

| Boundary | Rule |
|---|---|
| Browser → Catalyst | The browser uses public configuration only. No database URL, AWS credential, signing secret or service credential may enter a `VITE_*` variable or compiled bundle. |
| Catalyst Auth → API Gateway | The authenticated session establishes identity. API Gateway is the supported public API origin. |
| Gateway function → AppSail | The gateway removes client-supplied role/identity headers and issues signed, short-lived server context. |
| AppSail → Catalyst services | Server-side SDK access is least-privileged and environment-specific. |
| AppSail → protected analytics | Only the backend adapter may reach PostgreSQL, private object storage or GPU inference. |
| Model → operational action | No model may directly dispatch, accuse, arrest, close a case or modify a protected record. Human review is mandatory. |

### Data architecture

```mermaid
flowchart LR
    SRC["Synthetic source datasets\nFIR, parties, evidence, property,\ntransactions, stations, hazards"] --> VALIDATE["Validation and data-quality rules"]
    VALIDATE --> ONTOLOGY["Canonical ontology and relationship mapping"]
    ONTOLOGY --> HISTORY["Historical analytics store\nPostgreSQL / PostGIS / pgvector"]
    ONTOLOGY --> EXPORT["Curated serving-subset exporter"]
    EXPORT --> CATALYST["Catalyst Data Store\n106 idempotent import configurations"]
    CATALYST --> API["FastAPI domain services\n31 router groups"]
    HISTORY --> API
    API --> WEB["Role-scoped React application\n33 declared routes"]
    API --> PROV["Audit, snapshots, model provenance and evidence trail"]
```

### Request lifecycle

1. A user opens the Catalyst Slate application.
2. Catalyst Authentication establishes the session.
3. The SPA sends `/api/*` requests to the Catalyst API Gateway origin.
4. API Gateway invokes `gateway_api`.
5. The gateway discards untrusted identity headers, derives a signed role/scope context and forwards the request.
6. AppSail verifies the context before serving any non-health request.
7. The domain service enforces role, jurisdiction, purpose, rate and payload policies.
8. Reads are served from Catalyst's curated operational layer and, where authorised, the protected analytical plane.
9. Material writes and model outputs create provenance or audit evidence.
10. The UI renders the result with scope, freshness, confidence and source indicators.

---

## Technology stack

### Frontend

| Technology | Version / role |
|---|---|
| React | `18.3` component application |
| TypeScript | `5.5` static type safety |
| Vite | `5.4` development and production build |
| Tailwind CSS | `3.4` design tokens and responsive layout |
| React Router | `6` route composition and guarded workspaces |
| TanStack Query | `5` server-state, caching and request lifecycle |
| Radix UI | Accessible UI primitives |
| Zustand | Local interaction and workspace state |
| MapLibre GL / react-map-gl | Interactive geospatial rendering |
| deck.gl | High-volume geospatial layers |
| Mapillary JS | Optional street-level imagery |
| React Flow | Investigation-board canvas |
| Sigma.js + Graphology | Large graph exploration and algorithms |
| Recharts / Tremor | Operational charts and analytics |
| Vitest + Testing Library | Frontend tests |
| Playwright | End-to-end and responsive browser validation |

### Backend and data

| Technology | Role |
|---|---|
| Python | Data generation, API, analytics and infrastructure automation |
| FastAPI `0.115.6` | Typed asynchronous API |
| Uvicorn | ASGI runtime |
| Pydantic `2.10` | Request, response and configuration validation |
| PostgreSQL | Relational source of truth for analytical workloads |
| PostGIS | Spatial indexing and geography |
| pgvector | Embedding and semantic retrieval support |
| `pg_trgm` | Approximate text/entity matching |
| psycopg2 | PostgreSQL access and data generation |
| NumPy / SciPy / scikit-learn | Statistical and baseline ML |
| NetworkX | Network algorithms and graph features |
| Shapely | Spatial geometry processing |
| HTTPX / Requests | Governed outbound service calls |
| Catalyst Python SDK | Catalyst service integration |
| boto3 | Protected AWS adapter and private evidence storage |
| pytest | Backend and contract tests |

### Platform and operations

| Technology | Role |
|---|---|
| Zoho Catalyst Slate | Production frontend hosting |
| Zoho Catalyst Authentication | User identity |
| Zoho Catalyst API Gateway | Public API boundary |
| Zoho Catalyst AppSail | Containerised FastAPI runtime |
| Zoho Catalyst Data Store | Curated operational serving data |
| Zoho Catalyst Stratus | Governed object and artifact storage |
| Zoho Catalyst QuickML | RAG, LLM serving and baseline ML |
| Zoho Catalyst Signals / Cron / Workflows | Events, schedules and human-review orchestration |
| Zoho Catalyst Pipelines | CI/CD lifecycle |
| Docker | Reproducible AppSail image |
| AWS RDS PostgreSQL | Protected historical/analytical store where required |
| AWS S3 | Private digital-evidence objects |
| AWS SageMaker asynchronous endpoint | Temporary scale-to-zero GPU workloads |

---

## Zoho Catalyst services used

| Catalyst service | How DRISHTI uses it | Current repository evidence |
|---|---|---|
| **Slate** | Hosts the Vite/React single-page application and SPA redirects | `infra/catalyst/client/slate-config.toml` |
| **Authentication** | Establishes user identity and session for deployed mode | Catalyst Web SDK configuration in `web/.env.example` |
| **API Gateway** | Exposes `/api/*` and routes requests to the gateway function | `infra/catalyst/api-gateway/` |
| **Serverless Functions** | Gateway, token, data/evidence/prediction/report events, notification dispatch and scheduled handlers | Nine deployable functions plus `_shared` in `infra/catalyst/functions/` |
| **AppSail** | Runs the lightweight FastAPI API as `drishti-api` | `infra/catalyst/appsail/` |
| **Data Store** | Serves the curated operational subset with idempotent external IDs | 106 import configurations in `infra/catalyst/ds-import/configs/` |
| **Stratus** | Stores reports, artifacts and governed object payloads | `infra/catalyst/stratus/` |
| **Cache** | Caches safe short-lived operational lookups | `infra/catalyst/cache/` |
| **Signals** | Handles prediction-requested and optional domain events | `infra/catalyst/jobs/signals/` and event functions |
| **Cron / Job Scheduling** | Daily forecast and optional reconciliation | `cron_forecast`, `cron_reconcile`, `infra/catalyst/jobs/` |
| **QuickML No-code ML** | Provides a governed baseline model | `infra/catalyst/quickml/no-code/` |
| **QuickML LLM Serving** | Primary semantic-planner target for Ask DRISHTI when configured | `infra/catalyst/quickml/llm-serving/` |
| **QuickML RAG** | Grounds policy and SOP answers | `infra/catalyst/quickml/rag/` |
| **Workflows** | Encodes controlled transitions, approvals and operational fixtures | `infra/catalyst/workflows/` |
| **Pipelines** | Validates, builds, scans, deploys and smoke-tests releases | `infra/catalyst/pipelines/` |
| **Connections / Secrets** | Keeps service credentials and connections out of source code | `infra/catalyst/connections/`, `infra/catalyst/secrets/` |
| **Billing / Budget controls** | Defines credit checks, alert thresholds, duplicate prevention and cleanup | `infra/catalyst/billing/budget.json` |

### Catalyst component philosophy

The prototype intentionally keeps the active event footprint small:

- one primary `prediction-requested` Signal;
- one daily forecast cron;
- one AppSail application;
- feature flags defaulting optional background work to off;
- development imports capped at 5,000 rows per table;
- no duplicate service creation.

This reduces cost and operational complexity while preserving a clear path to production scale.

---

## Data, AI and model-governance approach

### Model placement

| Capability | Placement | Reason |
|---|---|---|
| Policy/SOP retrieval | Catalyst QuickML RAG | Grounded document answers and Catalyst-native governance |
| Ask DRISHTI semantic planner | Catalyst QuickML LLM Serving when configured; deterministic planner fallback | Provider-neutral contract and fail-closed behaviour |
| Baseline classification/forecast | Catalyst QuickML No-code ML | Accessible governed baseline |
| Statistical hotspot and fusion models | Catalyst AppSail CPU | Low-latency, explainable and inexpensive |
| Hawkes/KDE spatial-temporal analysis | Catalyst AppSail CPU | Appropriate for moderate synthetic workloads |
| TabFM, TimesFM, ST-GNN | Temporary AWS GPU endpoint | Custom foundation/GPU workloads not suited to the lightweight AppSail image |

### TabFM and TimesFM in DRISHTI

DRISHTI does not use “AI” as a single undifferentiated score. TabFM and TimesFM have separate, aggregate public-safety tasks:

| Foundation model | DRISHTI task | Why it is used | Execution and governance |
|---|---|---|---|
| **Google TabFM v1** | Classifies an area's next-quarter workload band and contributes a next-period district risk class | Designed for small-to-medium tabular problems and can use in-context examples without updating the published foundation weights | Real weights are loaded only in the protected GPU worker; licence marker and artifact digest are verified; a requested TabFM job fails closed if CUDA or weights are unavailable |
| **Google TimesFM 2.5—200M** | Forecasts a per-district crime-count trajectory and uncertainty band | Provides a foundation-model time-series layer without training a district-specific neural network from scratch | Runs behind the same governed forecast contract, locally when explicitly available or through the protected asynchronous CUDA endpoint; a non-TimesFM fallback cannot be labelled as real TimesFM |

The current forecast inventory reports:

- **TabFM:** 32 district predictions with a 30-day layer.
- **TimesFM 2.5:** 32 district predictions with a 92-day layer.
- **Near-repeat:** 150 event predictions with a 14-day layer.
- **ST-GNN:** 32 district predictions with a 30-day layer.
- **Fusion:** 32 district predictions with a 30-day layer.

![DRISHTI governed multi-model forecast stack](docs/assets/benchmarks/model-stack-overview.svg)

TabFM and TimesFM weights are never fine-tuned automatically from a newly uploaded FIR or a single case. Model promotion requires leakage checks, baseline comparison, provenance and human approval.

### Reproducible prediction envelope

Every governed prediction is designed to include:

```json
{
  "prediction_id": "stable identifier",
  "model_id": "registered model",
  "model_version": "immutable version",
  "feature_snapshot_id": "immutable input snapshot",
  "jurisdiction": "authorised geographic scope",
  "as_of": "source cutoff timestamp",
  "horizon": "forecast window",
  "confidence": 0.0,
  "explanation": "human-readable drivers",
  "source_hash": "content/provenance hash",
  "review_status": "pending | accepted | modified | rejected"
}
```

### Governance lifecycle

```mermaid
flowchart LR
    DATA["Validated synthetic data"] --> SNAP["Immutable feature snapshot"]
    SNAP --> TRAIN["Train / configure candidate"]
    TRAIN --> BACKTEST["Temporal and geographic backtest"]
    BACKTEST --> REVIEW["Model review and approval"]
    REVIEW --> REG["Versioned model registry"]
    REG --> SERVE["Scoped inference"]
    SERVE --> EXPLAIN["Confidence, drivers and provenance"]
    EXPLAIN --> HUMAN["Human accept / modify / reject"]
    HUMAN --> MONITOR["Drift, feedback and performance monitoring"]
    MONITOR --> BACKTEST
```

### Ask DRISHTI guardrails

- Natural language is converted into a constrained query plan, not arbitrary SQL.
- Role and jurisdiction filters are applied independently of the language model.
- The planner cannot grant itself more scope.
- Answers expose citations or record references.
- An unconfigured LLM does not break the feature; a labelled deterministic planner remains available.
- Voice questions below the configured confidence threshold require confirmation.
- Evidence extraction, face recognition and automatic document interpretation are disabled for this submission.

---

## Security, privacy and responsible use

### Security controls

- No secret is allowed in browser environment variables.
- Production builds run a bundle secret scan.
- The gateway removes spoofable identity and role headers.
- AppSail rejects unsigned direct non-health requests.
- CORS uses explicit origins rather than wildcard access.
- Request rate and payload-size limits are configurable.
- Private evidence objects use exact-object, short-lived pre-signed URLs.
- AWS credentials are supplied by IAM roles or local SSO, never committed keys.
- Intake write endpoints can remain localhost-only unless a trusted HTTPS edge is configured.
- Synthetic-mode startup checks fail closed if the database environment marker is absent.
- Release validation includes static checks, dependency audit and secret scanning.

### Responsible-use principles

1. **No automated coercive action.**
2. **No person-level predictive re-scoring.**
3. **No automatic dispatch from a hotspot or forecast.**
4. **No hidden evidence extraction.**
5. **No claim that synthetic benchmark results represent production policing outcomes.**
6. **Human review and contestability for every operational recommendation.**
7. **Purpose, role and jurisdiction are part of every data-access decision.**
8. **Model uncertainty and provenance must remain visible.**

### Production hardening required before real data

- Complete a legal, privacy and human-rights impact assessment.
- Replace synthetic demo identities with institution-managed identity and least-privilege roles.
- Apply field- and row-level controls appropriate to each source.
- Define retention, legal hold, redaction and disclosure policies.
- Conduct threat modelling, penetration testing and independent security review.
- Validate model fairness, error distribution and feedback-loop risk.
- Establish incident response, audit review and operator training.

---

## Prototype snapshots

All screenshots below are stored inside the repository so they remain visible in the public GitHub submission.

### 1. Catalyst landing experience

The deployed hero establishes Karnataka as the area of operations and presents evidence-backed, human-controlled intelligence.

![DRISHTI Catalyst landing page](docs/assets/screenshots/01-landing-hero.png)

### 2. Role-scoped login

The split-screen login preserves the enterprise visual hierarchy while presenting all ten roles, officers and scopes without clipping.

![DRISHTI role selection](docs/assets/screenshots/02-login-role-selection.png)

### 3. Command Center

The role-aware command surface combines live updates, workload, alerts, hotspots, jurisdiction metrics and recent activity.

![DRISHTI Command Center](docs/assets/screenshots/03-command-center.png)

### 4. Case Explorer

Case Explorer supports structured filters, free-text search, modus-operandi similarity and table/map modes without horizontal page scrolling.

![DRISHTI Case Explorer](docs/assets/screenshots/04-case-explorer.png)

### 5. Map & Hotspots

The map supports state, district, taluk and station boundaries; incident categories; hotspot layers; forecasts; patrol planning; alerts and fullscreen operation.

![DRISHTI Map and Hotspots](docs/assets/screenshots/05-map-hotspots.png)

Selecting an incident opens a concise operational popup with case identity, severity, status, location, registration date, legal section and a direct case-file action.

![DRISHTI map case popup](docs/assets/screenshots/05b-map-case-popup.png)

### 6. Complete case file

The case view connects core facts with timeline, parties, acts, arrests, chargesheet, evidence, statements, property, digital/financial records, court lifecycle and network.

![DRISHTI case file](docs/assets/screenshots/06-case-file.png)

### 7. Investigation Board

“Send to Board” expands the complete governed case network. The implemented example shows typed case, victim, complainant, accused, note and lifecycle objects with verified links and source-aware inspection.

![DRISHTI Investigation Board](docs/assets/screenshots/07-investigation-board.png)

### 8. Network Analysis

The network workspace provides entity exploration, communities, hidden associations, money trail and path finding.

![DRISHTI Network Analysis](docs/assets/screenshots/08-network-analysis.png)

### 9. Analytics & Forecasting

The analytics workspace combines trends, model provenance, confidence, backtesting and review.

![DRISHTI Analytics and Forecasting](docs/assets/screenshots/09-analytics-forecasting.png)

### 10. Ask DRISHTI

The assistant provides scoped, evidence-backed operational analysis with deterministic fallback and citation-aware answers.

![Ask DRISHTI](docs/assets/screenshots/10-ask-drishti.png)

### 11. Emergency Response

The emergency workspace presents multi-hazard situation awareness, forecast risk, resources and response planning.

![DRISHTI Emergency Response](docs/assets/screenshots/11-emergency-response.png)

---

## Prototype performance report and benchmarking

### Visual ML benchmark dashboard

The following charts use measured prototype outputs captured on 26 July 2026. They intentionally distinguish three states:

- **measured serving result:** a model was evaluated on the recorded split;
- **registered/used layer:** the layer has governed forecast records in the current inventory;
- **GPU acceptance pending:** real weights are wired and fail closed, but no comparable GPU metric is claimed until that acceptance run is recorded.

#### TabFM workload task compared with conventional ML baselines

The aggregate workload-band dataset contains 576 district-quarter rows, ten non-protected features and a time-based split of 352 training, 96 validation and 128 test rows. The chart shows the measured held-out scores for the current serving contract and transparent baselines. It also makes the real TabFM GPU status explicit instead of inventing a bar.

![TabFM workload model comparison](docs/assets/benchmarks/workload-model-comparison.svg)

| Evaluated model | Accuracy | Macro-F1 | QWK | ECE | Interpretation |
|---|---:|---:|---:|---:|---|
| Prior-period baseline | **0.6484** | **0.5998** | **0.5639** | 0.1516 | Strong transparent comparator on this persistent synthetic series |
| Histogram Gradient Boosting | 0.4922 | 0.4856 | 0.3891 | 0.4487 | Conventional trained tabular model |
| Current in-context serving model | 0.4141 | 0.4003 | 0.3317 | **0.1469** | Deterministic CPU fallback used when foundation weights are unavailable |
| Majority-class baseline | 0.1016 | 0.0461 | 0.0000 | 0.1541 | Minimum sanity baseline |
| **Google TabFM v1** | — | — | — | — | Real GPU path is implemented and used for governed jobs; recorded CPU benchmark deferred the 3.3 GB weights, so comparable accuracy remains an explicit acceptance gate |

**What this result means:** the current fallback does not beat the strong prior-period baseline. DRISHTI therefore does not auto-promote it. TabFM must be evaluated on the identical time/geo split on the real CUDA path before the model registry can mark it active. This is the intended governance behaviour, not a hidden failure.

#### TimesFM trajectory layer compared with forecasting baselines

The leakage-safe rolling-origin benchmark evaluates six walk-forward origins across 32 districts, producing 192 held-out district-month predictions. Lower MAE, RMSE and WAPE are better.

![TimesFM trajectory backtest comparison](docs/assets/benchmarks/timesfm-backtest-comparison.svg)

| Forecast candidate | MAE ↓ | RMSE ↓ | WAPE ↓ | sMAPE ↓ | 80% interval coverage |
|---|---:|---:|---:|---:|---:|
| **TimesFM-compatible serving forecaster** | **6.327** | **8.406** | **0.1132** | **14.49%** | 0.6094 |
| Moving average—3 periods | 6.813 | 9.415 | 0.1219 | 14.60% | **0.8333** |
| Seasonal naive | 7.698 | 10.018 | 0.1377 | 17.51% | 0.7760 |

Measured skill:

- **+17.81% MAE skill**, **+16.09% RMSE skill** and **+17.79% WAPE skill** versus seasonal naive.
- **+7.13% MAE skill**, **+10.72% RMSE skill** and **+7.14% WAPE skill** versus moving average.
- `beats_all_baselines = true` for point-error metrics.

> [!CAUTION]
> The measured backtest above currently executes `drishti-timesfm-seasonal`, the fast TimesFM-compatible statistical serving forecaster. The real `drishti-timesfm-2.5-200m` layer is separately registered and currently contains 32 district predictions over a 92-day horizon. DRISHTI does not present the fallback benchmark as proof of the real foundation model; TimesFM 2.5 must retain its own model-version and backtest provenance.

#### Why the model stack is stronger than choosing one model

| Model/layer | Best at | Known limitation | How DRISHTI uses it safely |
|---|---|---|---|
| TabFM | Aggregate tabular workload/risk bands with limited labelled context | Heavy real weights and GPU requirement; still needs identical-split acceptance score | Protected GPU path, artifact verification, no silent fallback, human promotion |
| TimesFM | Longer-horizon univariate count trajectories | Temporal model alone cannot capture street-level spatial diffusion | Produces district trajectory and uncertainty; kept separate from spatial layers |
| ST-GNN | Spatial-temporal influence between adjacent districts | More complex, graph-sensitive and harder to explain alone | Adds neighbour structure as one inspectable layer |
| Near-repeat | Short-horizon local recurrence after an event | Narrow time/space mechanism, not a general trend model | Produces fast 14-day event alerts |
| KDE/Hawkes/statistical baselines | Transparent hotspot and recurrence structure | Lower representational capacity | Remain visible comparators and safe CPU fallbacks |
| Fusion | Combines validated evidence from multiple layers | Can amplify a bad layer if governance is weak | Includes only validated layers and records why a layer was excluded |

**Reproduce the read-only benchmark evidence:**

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/workload/evaluation?foundation_kind=served&refresh=false"
Invoke-RestMethod "http://127.0.0.1:8000/workload/benchmarks"
Invoke-RestMethod "http://127.0.0.1:8000/forecast/backtest?horizon=1&n_origins=6&per_head=false&persist=false"
Invoke-RestMethod "http://127.0.0.1:8000/forecast/layers"
```

### Validation dashboard

| Quality gate | Measured result | Status |
|---|---:|:---:|
| Frontend unit/component suite | **65 tests passed across 21 executed test files** | ✅ |
| Investigation-board backend suite | **27 tests passed** | ✅ |
| TypeScript production check | `tsc --noEmit` passed | ✅ |
| Vite production build | **3,829 modules transformed** | ✅ |
| Production bundle secret scan | Passed; no blocked credential pattern in `dist/` | ✅ |
| Catalyst main deployment | HTTP 200 on 26 July 2026 | ✅ |
| Catalyst API Gateway health | HTTP 200 during verification | ✅ |
| Catalyst AppSail health | HTTP 200 during verification | ✅ |
| Desktop responsive width—1,536 px | document width = viewport width; no horizontal page overflow | ✅ |
| Laptop responsive width—900 px | document width = viewport width; no horizontal page overflow | ✅ |
| Board inspector stability | **0 blank inspector states across 12 rapid alternating node selections** | ✅ |
| Board frame interaction | 4 resize handles exposed and exercised | ✅ |
| Case-network expansion example | **14 nodes and 13 verified links** for case `100239` | ✅ |

### Production bundle profile

The following values were measured from a production build. They are build-artifact sizes, not network measurements from a controlled CDN test.

| Artifact | Raw size | Gzip size | Interpretation |
|---|---:|---:|---|
| `index.html` | 1.04 kB | 0.54 kB | Minimal application shell |
| Main CSS | 262.53 kB | 54.34 kB | Enterprise UI and map/graph styling |
| MapLibre chunk | 1,053.93 kB | 284.94 kB | Dedicated map renderer dependency |
| Main JavaScript | 3,836.01 kB | 1,044.41 kB | Rich case, board, graph, map and analytics application |

**Measured build time:** approximately **71 seconds** on the development workstation used for validation.

### Functional flow coverage

| Flow | Coverage performed |
|---|---|
| Landing → role selection | Catalyst landing, entry action and role screen visually checked |
| Role → workspace | Role click and scoped operational route verified in the local prototype |
| Case Explorer → Case File | Case search/navigation and complete case details checked |
| Case File → Investigation Board | Board creation and governed network expansion checked |
| Map marker → case popup → Case File | Marker selection, popup visibility and action checked |
| Map tabs | Live Map, Hotspots, Forecast, Patrol Planning and Red-Zone Alerts reviewed |
| Board authoring | Sticky, frame, text, node selection, inspector and responsive drawers reviewed |
| Responsive shell | 900 px and 1,536 px desktop/laptop widths checked for page-level horizontal overflow |

### Benchmark methodology

1. Start the local FastAPI and Vite applications with synthetic data.
2. Run targeted Vitest and pytest suites.
3. Run the release build, which includes TypeScript validation, Slate post-processing and bundle secret scanning.
4. Exercise the main journey in a real Chromium browser.
5. Record viewport and document widths at representative laptop and desktop sizes.
6. Stress the investigation-board inspector with rapid alternating selections.
7. Inspect generated screenshots for clipping, overflow, loading/error states and information visibility.
8. Verify public and service health endpoints separately.

### Interpretation and limitations

- These results demonstrate **prototype correctness and interaction stability**, not a production service-level agreement.
- The rich initial JavaScript bundle is acceptable for a hackathon prototype but is the largest performance opportunity. Route-level code splitting, deferred graph/map loading and dependency trimming should be implemented before large-scale use.
- A production benchmark must add p50/p95/p99 API latency, Web Vitals, concurrency, database plans, map point volume, board graph scale, error rate and recovery testing.
- All data are synthetic; no operational-effectiveness claim should be made from this benchmark.

### Production performance targets

| Metric | Prototype-to-production target |
|---|---:|
| Largest Contentful Paint on standard office broadband | `< 2.5 s` |
| Cumulative Layout Shift | `< 0.1` |
| Interaction to Next Paint | `< 200 ms` for ordinary UI actions |
| Read API p95 | `< 500 ms` for curated operational queries |
| Search API p95 | `< 1,000 ms` with authorised scope filters |
| Map interaction | 60 fps target with level-of-detail aggregation |
| Board interaction | Smooth pan/zoom at 500 visible nodes; progressive expansion above that |
| Availability | Define only after production architecture and support ownership are approved |

---

## Proposed impact and use cases

### Expected impact

| Impact area | Current friction | Proposed DRISHTI effect | Suggested measurement |
|---|---|---|---|
| Investigation preparation | Manual search across systems | One governed case and relationship picture | Median time from case open to usable investigation board |
| Cross-case detection | Relationships discovered informally | Entity, network, path and similarity tools | Verified cross-case links discovered per reviewed case |
| Supervisory awareness | Delayed aggregated reports | Role-scoped command view with freshness | Time from source update to supervisor visibility |
| Geospatial operations | Map disconnected from case details | Click-through incident context and reviewable plans | Time from hotspot detection to reviewed patrol plan |
| Evidence accountability | Screenshots and detached notes | Live references plus pinned snapshots | Percentage of board objects with source and version |
| Model trust | Unexplained scores | Backtests, confidence, provenance and review | Percentage of recommendations with completed human disposition |
| Emergency readiness | Hazard, resource and plan silos | Shared situation and response workspace | Time to produce an approved response picture |

### Proposed use cases

- Repeat-property-crime pattern discovery.
- Cybercrime account/device linkage and money-trail review.
- Cross-district vehicle and phone association.
- Case-ageing, workload and investigation bottleneck supervision.
- District hotspot and near-repeat analysis.
- Human-reviewed patrol allocation.
- Evidence completeness and chargesheet readiness.
- Disaster/hazard situation awareness and resource planning.
- Policy/SOP retrieval with grounded responses.
- Data-quality and jurisdiction repair before operational publication.

### Non-goals

DRISHTI is not intended to:

- predict whether a named person will commit a crime;
- autonomously dispatch officers;
- replace legal or supervisory judgement;
- establish guilt from a graph relationship;
- ingest real protected data without institutional governance;
- expose raw database or model infrastructure to the browser.

---

## Estimated implementation cost

### Hackathon operating envelope

The committed cost-safety descriptor defines the following planning baseline:

| Item | Planned value |
|---|---:|
| Catalyst free credit | ₹300 |
| Catalyst basic-plan baseline | ₹1,500 |
| Catalyst planning envelope | **₹1,800** |
| AWS monthly budget alarm | **US$25** |
| AppSail instances | 1–2 |
| Active Signals | 1 primary rule |
| Active forecast cron | 1 daily job |
| GPU endpoint | One asynchronous endpoint, scale-to-zero, deleted after testing |

### Catalyst budget thresholds

| Threshold | Amount | Action |
|---|---:|---|
| 50% | ₹900 | Review usage report |
| 75% | ₹1,350 | Pause non-essential feature flags |
| 90% | ₹1,620 | Stop temporary GPU workloads and freeze new deployments |

These thresholds are an implementation plan, not a current invoice. Catalyst usage and billing must be confirmed in the Catalyst Console because the authenticated CLI session does not expose billing usage.

### Indicative production cost drivers

- Number and size of AppSail instances.
- Data Store rows, indexes and request volume.
- Stratus object storage and transfer.
- Signal, Cron and Workflow executions.
- QuickML training/serving usage.
- Historical PostgreSQL size, IOPS, backup and high availability.
- Private evidence volume and retention.
- GPU inference duration and concurrency.
- Observability, security testing and support staffing.

### Cost controls implemented in the design

- No duplicate AppSail apps, Signals, crons or GPU endpoints.
- Optional event, RAG and notification scaffolds disabled by default.
- Development Data Store imports capped.
- Scale-to-zero GPU inference.
- Temporary object lifecycle rules.
- Explicit cleanup and teardown runbooks.
- Budget alarms and manual Catalyst credit checks.

---

## Repository structure

```text
DRISHTI/
├── README.md
├── .env.example                  # Server-side configuration template
├── datagen/                      # Deterministic synthetic-data generation
├── docs/
│   └── assets/screenshots/       # Submission-safe prototype screenshots
├── infra/
│   ├── catalyst/
│   │   ├── api-gateway/          # Public route definitions
│   │   ├── appsail/              # FastAPI container and deployment descriptors
│   │   ├── billing/              # Cost controls and cleanup
│   │   ├── cache/                # Cache configuration
│   │   ├── client/               # Slate SPA configuration
│   │   ├── connections/          # External connection declarations
│   │   ├── ds-import/            # Curated serving export/import
│   │   ├── ds-schema/            # Data Store schema/provisioning
│   │   ├── functions/            # Gateway, event and scheduled functions
│   │   ├── jobs/                 # Signals and Cron definitions
│   │   ├── pipelines/            # Catalyst CI/CD pipeline
│   │   ├── quickml/              # No-code, LLM and RAG configuration
│   │   ├── stratus/              # Object-storage configuration
│   │   ├── verification/         # Acceptance and smoke validation
│   │   └── workflows/            # Controlled operational workflows
│   ├── aws/                      # Protected analytical/GPU adapters
│   └── db/                       # Database infrastructure helpers
├── scripts/                      # Validation and release automation
├── services/
│   └── ml/
│       ├── app/                  # FastAPI application and 31 router groups
│       ├── sql/                  # Base schema plus ordered migrations
│       ├── tests/                # API, governance and domain tests
│       ├── requirements.txt      # Full analytical environment
│       └── requirements.appsail.txt
└── web/
    ├── public/                   # Public assets and landing media
    ├── scripts/                  # Slate post-build and secret scan
    ├── src/                      # React application and tests
    ├── .env.example              # Browser-safe configuration template
    └── package.json
```

Repository inventory at documentation time:

- **33** declared frontend routes.
- **31** FastAPI router groups.
- **26** SQL schema/migration files.
- **106** Catalyst Data Store import configurations.
- **Nine** deployable Catalyst functions plus one shared package.

---

## How to run the project locally

### 1. Prerequisites

- Git
- Node.js 18 or newer and npm
- Python 3.11 or 3.12
- PostgreSQL 15 or newer
- PostgreSQL extensions: PostGIS, pgvector and `pg_trgm`
- Optional: Docker
- Optional for Catalyst operations: Catalyst CLI `1.27.0` or compatible
- Optional for private evidence/GPU paths: AWS CLI with an SSO profile or IAM role

### 2. Clone the repository

```powershell
git clone https://github.com/prajwalbr0304/DRISHTI.git
Set-Location DRISHTI
```

### 3. Create backend configuration

Copy `.env.example` to `.env` and replace placeholders. Never commit `.env`.

```powershell
Copy-Item .env.example .env
```

Minimum local values:

```dotenv
DATABASE_URL=postgresql://drishti_app:YOUR_PASSWORD@localhost:5432/drishti
READONLY_ROLE=drishti_readonly
HACKATHON_MODE=true
DEMO_DATA_ONLY=true
SYNTHETIC_ENV_EXPECTED=synthetic_hackathon
INTAKE_WRITES_LOCALHOST_ONLY=true
```

Optional S3, QuickML, voice and live-feed settings are documented directly in `.env.example`.

### 4. Create the database

Create a PostgreSQL database and enable extensions:

```sql
CREATE DATABASE drishti;
\c drishti
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Apply the three base SQL files, then numbered migrations in ascending order:

```powershell
$env:PGPASSWORD = "YOUR_PASSWORD"

psql -h localhost -U drishti_app -d drishti -f services/ml/sql/police_fir_schema.sql
psql -h localhost -U drishti_app -d drishti -f services/ml/sql/police_fir_extensions.sql
psql -h localhost -U drishti_app -d drishti -f services/ml/sql/police_fir_intelligence.sql

Get-ChildItem services/ml/sql -Filter '[0-9][0-9][0-9]_*.sql' |
  Sort-Object Name |
  ForEach-Object {
    psql -h localhost -U drishti_app -d drishti -f $_.FullName
  }
```

Do not paste real passwords into shell history on a shared workstation. Prefer `.pgpass`, Windows Credential Manager or another secure local secret mechanism.

### 5. Generate synthetic data

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Inspect available generator options:

```powershell
python -m datagen --help
```

Run the documented synthetic dataset generation profile for your local database. Keep `HACKATHON_MODE=true` and verify the `synthetic_hackathon` environment marker before starting the API.

### 6. Start the FastAPI backend

For the complete analytical environment:

```powershell
pip install -r services/ml/requirements.txt
Set-Location services/ml
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For the lightweight AppSail-compatible environment:

```powershell
pip install -r services/ml/requirements.appsail.txt
Set-Location services/ml
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 7. Configure and start the web application

Open another PowerShell terminal:

```powershell
Set-Location web
Copy-Item .env.example .env.local
npm ci
npm run dev
```

For local mode, confirm:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_AUTH_MODE=offline
VITE_DEMO_BADGE=Synthetic Hackathon Demo
```

Open [http://localhost:5173/](http://localhost:5173/) and select **Enter platform**. In offline mode, choose a synthetic role to open its scoped workspace.

### 8. Build a production bundle locally

```powershell
Set-Location web
npm run build
npm run preview
```

`npm run build` performs:

1. TypeScript validation.
2. Vite production build.
3. Slate post-build processing.
4. Compiled-bundle secret scanning.

### 9. Run tests

Frontend:

```powershell
Set-Location web
npm test
npm run typecheck
npm run lint
```

End-to-end:

```powershell
npm run test:e2e:install
npm run test:e2e
```

Backend:

```powershell
Set-Location services/ml
pytest -q
```

### Local troubleshooting

| Symptom | Check |
|---|---|
| UI remains in skeleton state | Confirm the API is listening on port 8000 and `VITE_API_BASE_URL` is correct. |
| “Synthetic environment” startup failure | Apply migrations and ensure the database carries the expected synthetic environment marker. |
| 401/403 in local mode | Confirm `VITE_AUTH_MODE=offline`; restart Vite after changing environment variables. |
| Map loads without street view | `VITE_MAPILLARY_TOKEN` is optional; base map features should still work. |
| Evidence upload unavailable | Set the private S3 bucket configuration or use metadata-only mode. |
| Board unavailable after role change | The board is access-controlled; use a role with board permission or create a new board from a case. |
| Horizontal page scroll | Verify the browser is at a common desktop width; nested tables/canvases should scroll internally, not the document. |

---

## Testing and release validation

### Frontend quality gates

```powershell
Set-Location web
npm run typecheck
npm test
npm run build:release
```

### Backend quality gates

```powershell
Set-Location services/ml
pytest -q
```

### Security and infrastructure checks

The Catalyst pipeline includes:

```mermaid
flowchart LR
    VALIDATE["Validate\nlint + tests"] --> BUILD["Build\nfrontend + AppSail + artifacts"]
    BUILD --> SECURITY["Security\nsecret scan + dependency audit + static checks"]
    SECURITY --> PREFLIGHT["Mandatory preflight\nproject + environment + synthetic + duplicates"]
    PREFLIGHT --> DEPLOY["Deploy development\nimmutable tested artifacts"]
    DEPLOY --> SMOKE["Smoke test\nSlate + Gateway + AppSail health"]
```

Important release rules:

- Never deploy an untested working tree.
- Never put a database or AWS endpoint into `VITE_API_BASE_URL`.
- Production web traffic must use the Catalyst API Gateway origin.
- Promote the same immutable artifact that passed tests and smoke validation.
- Confirm there is only one intended AppSail app, Signal rule and forecast cron.
- Confirm Catalyst credit balance before and after enabling paid capabilities.

---

## Catalyst deployment model

### Production entry point

**[https://drishti-frvfpunc.onslate.in/](https://drishti-frvfpunc.onslate.in/)**

### Configured Catalyst project

| Property | Value |
|---|---|
| Catalyst project name | `DHRISTI` |
| Product name | `DRISHTI` |
| Project ID | `48361000000030003` |
| Organisation/environment identifier | `60075362708` |
| Main frontend | Catalyst Slate |
| API runtime | Catalyst AppSail `drishti-api` |
| Public API contract | Catalyst API Gateway `/api/*` |

### Verified development service endpoints

These endpoints are operational diagnostics, not substitutes for the official Slate evaluation link:

- API Gateway: `https://dhristi-60075362708.development.catalystserverless.in/api`
- AppSail: `https://drishti-api-50044118953.development.catalystappsail.in`

Both health paths returned HTTP 200 during repository verification.

### Deployment commands

Read `infra/catalyst/README.md` and the deployment runbooks before making changes. A typical controlled sequence is:

```powershell
Set-Location infra/catalyst
catalyst project:list
catalyst status

# Build frontend with the exact Catalyst API Gateway origin.
$env:VITE_API_BASE_URL = "https://YOUR-CATALYST-GATEWAY/api"
npm --prefix ../../web run build:release

# Deploy only after tests, scans, preflight and explicit cost review.
catalyst deploy
```

The repository includes separate AppSail build/deploy and Data Store import runbooks. Data imports that spend credits should not be run casually.

---

## Future development

### Near term—prototype hardening

- Split the main JavaScript bundle by route and defer map/graph libraries.
- Add automated visual-regression baselines for all ten roles.
- Add Web Vitals and p50/p95/p99 API telemetry.
- Complete keyboard-only and screen-reader audits.
- Add larger graph/map stress datasets and recovery tests.
- Publish the repository and three-minute demo link.
- Add an in-product build/version panel for evaluation traceability.

### Medium term—operational readiness

- Institution-managed SSO, lifecycle provisioning and fine-grained entitlements.
- Row/field/purpose-based policies for real data.
- Encryption key management, evidence legal hold and redaction workflow.
- Kannada and multilingual search, dictation and explanation.
- Offline-first mobile/PWA mode for field officers.
- Cross-district collaboration with explicit disclosure approval.
- Formal model registry approval, drift monitoring and rollback.
- Structured feedback capture for accepted, modified and rejected recommendations.
- Resilient queues, retries, idempotency and disaster recovery.

### Long term—public-safety ecosystem

- Standards-based exchange with police, court, forensic and emergency systems.
- Privacy-preserving federated analytics.
- Advanced multimodal evidence support after explicit legal approval.
- Resource-optimisation simulations for emergency response.
- Causal evaluation of operational interventions rather than correlation-only scoring.
- Independent auditing tools for model, access and decision histories.

---

## Known constraints

- The prototype uses synthetic records and synthetic role identities.
- Anonymous access to the configured GitHub URL returned 404 at documentation time; repository visibility must be corrected.
- A public three-minute demo-video URL is still required.
- Catalyst billing data are console-only for the current CLI session.
- The protected AWS analytics plane is optional and should be used only where Catalyst-native services cannot meet the compute requirement.
- The main JavaScript bundle is rich and should be code-split before broad production use.
- Development health verification is not equivalent to production load or resilience testing.
- Model outputs have not been validated on real operational data and must not be used for real enforcement decisions.

---

## Three-minute demo script

Use this sequence to record the required public demo:

| Time | Scene | Narration focus |
|---:|---|---|
| 0:00–0:20 | Catalyst landing hero | Karnataka operational picture; evidence-backed and human-controlled |
| 0:20–0:40 | Role selection | Ten roles; identity, jurisdiction and scope |
| 0:40–1:00 | Command Center | Workload, alerts, hotspots, freshness and role relevance |
| 1:00–1:25 | Case Explorer → case `100239` | Search, complete case file and connected records |
| 1:25–1:55 | Send to Investigation Board | Governed expansion, 14 nodes/13 links, source snapshot, sticky/frame/text |
| 1:55–2:20 | Map & Hotspots | Karnataka incidents, point popup, hotspot/forecast/patrol/fullscreen |
| 2:20–2:40 | Network / Ask DRISHTI | Explain a connection and show cited, scoped analysis |
| 2:40–2:55 | Emergency Response | Shared human-controlled operational model |
| 2:55–3:00 | Closing | Catalyst deployment link, USP and responsible-use boundary |

Before publishing, remove browser bookmarks, personal extensions, private account details and local-only URLs from the recording.

---

## Final submission checklist

- [x] Problem statement addressed in depth.
- [x] Brief about the solution.
- [x] Opportunities.
- [x] Differentiation from existing ideas.
- [x] Explanation of how the solution solves the problem.
- [x] USP.
- [x] Detailed feature list.
- [x] Process-flow and use-case diagrams.
- [x] Wireframes/mock diagrams.
- [x] Detailed architecture and trust-boundary diagram.
- [x] Technology stack.
- [x] Catalyst services inventory.
- [x] Estimated implementation cost and cost controls.
- [x] Complete prototype snapshot gallery.
- [x] Prototype performance report and benchmarking.
- [x] Proposed impact and use cases.
- [x] Future development.
- [x] Local run, test and build instructions.
- [x] Official Catalyst deployed solution link.
- [ ] Make the GitHub repository publicly accessible and verify from an incognito window.
- [ ] Upload the three-minute demo and replace the placeholder link.
- [ ] Perform one final incognito walkthrough of the Catalyst URL.

---

## Responsible-use statement

DRISHTI is a synthetic hackathon demonstration of governed decision-support infrastructure. It is not a production policing system, does not determine guilt, and must not be used to make autonomous enforcement decisions. Any future real-world deployment requires legal authority, privacy controls, security review, model validation, community and institutional governance, operator training and continuous human accountability.

---

<p align="center">
  <strong>DRISHTI</strong><br />
  Observe · Understand · Review · Act · Audit
</p>
