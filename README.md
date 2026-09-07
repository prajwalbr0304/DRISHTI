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
| **GitHub Public Repository** | [https://github.com/prajwalbr0304/DRISHTI](https://github.com/prajwalbr0304/DRISHTI) | ✅ Public repository |
| **Demo Video** | [https://youtu.be/cp27iqfYYyA](https://youtu.be/cp27iqfYYyA) | ✅ Public demo video |

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
14. [Database inventory and data volume](#database-inventory-and-data-volume)
15. [Zoho Catalyst services used](#zoho-catalyst-services-used)
16. [Data, AI and model-governance approach](#data-ai-and-model-governance-approach)
17. [Security, privacy and responsible use](#security-privacy-and-responsible-use)
18. [Prototype snapshots](#prototype-snapshots)
19. [Prototype performance report and benchmarking](#prototype-performance-report-and-benchmarking)
20. [Proposed impact and use cases](#proposed-impact-and-use-cases)
21. [Estimated implementation cost](#estimated-implementation-cost)
22. [Repository structure](#repository-structure)
23. [How to run the project locally](#how-to-run-the-project-locally)
24. [Testing and release validation](#testing-and-release-validation)
25. [Catalyst deployment model](#catalyst-deployment-model)
26. [Future development](#future-development)
27. [Known constraints](#known-constraints)
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

## Database inventory and data volume

### Measured database overview

The database inventory below was measured directly from the authenticated AWS RDS PostgreSQL instance on **26 July 2026**. Row totals use exact `COUNT(*)` queries over every ordinary user table—not PostgreSQL planner estimates. The inspection was read-only and did not run `ANALYZE`, modify data or expose the connection credential.

![DRISHTI database inventory](docs/assets/benchmarks/database-inventory.svg)

| Database measure | Exact/current value |
|---|---:|
| Database | `drishti` |
| Engine | AWS RDS PostgreSQL **17.10** on ARM64 |
| RDS instance class | `db.t4g.medium` |
| RDS status | Available |
| Allocated storage | 30 GiB |
| Storage encryption | Enabled |
| Current database size | **1,024,399,027 bytes—1.02 GB / 0.95 GiB** |
| Ordinary tables | **140** |
| Non-empty tables | **118** |
| Empty/future-state tables | **22** |
| Exact rows across ordinary tables | **3,011,145** |
| Views | **20** |
| Materialized views | **3** |
| Columns | **1,708** |
| Indexes | **503** |
| Constraints | **582** |
| Table-relation storage | 1,008,418,816 bytes |
| Table heap/data storage | 579,411,968 bytes |
| Index storage | 424,673,280 bytes |

> [!IMPORTANT]
> The RDS instance is publicly addressable for the synthetic prototype. Authentication, encryption and server-side access controls still apply, but a production deployment should move the database into private subnets, disable public accessibility and permit traffic only from approved application/network boundaries.

### Exact rows by data domain

| Governed data domain | Tables | Non-empty | Exact rows | Share of all rows | What the domain contains |
|---|---:|---:|---:|---:|---|
| **People, parties and organisations** | 17 | 14 | **1,156,931** | 38.422% | Typed case roles, accused, victims, complainants, canonical people/entities, staff and reference attributes |
| **Core cases and FIR taxonomy** | 14 | 14 | **987,211** | 32.785% | FIR/case master, versions, events, sources, occurrence time, crime heads/sub-heads and workflow taxonomy |
| **Legal, court and lifecycle** | 14 | 14 | **524,821** | 17.429% | Acts/sections, arrests, accused-arrest links, chargesheets, bail, court events, outcomes and statements |
| **Networks and intelligence** | 7 | 7 | **222,407** | 7.386% | Canonical graph, verified network edges, hidden associations, patterns, gangs and location observations |
| **Evidence, property, digital and financial** | 20 | 14 | **104,432** | 3.468% | Evidence objects/versions/links, property, seizures, accounts, transactions, devices and communications |
| **Geospatial and contextual** | 14 | 14 | **12,167** | 0.404% | State/district/unit boundaries, locations, hotspots, weather, social/economic indicators and calendar context |
| **Identity, audit, collaboration and reporting** | 21 | 14 | **1,559** | 0.052% | Users, roles, permissions, audit, alerts, chat, voice, notifications, reports, flags and retention |
| **ML, forecasts and model governance** | 17 | 15 | **1,335** | 0.044% | Predictions, model versions, benchmarks, feature snapshots, requests/results, reviews and backtests |
| **Intake, import and data quality** | 16 | 12 | **282** | 0.009% | Draft FIR activity, ingestion, templates, entity-resolution review, quality issues and synthetic runs |
| **Total** | **140** | **118** | **3,011,145** | **100%** | Synthetic, connected operational and analytical data |

### Highest-volume tables

| Table | Exact rows | Storage | Data represented |
|---|---:|---:|---|
| `CaseEvent` | **386,990** | 94 MB | Append-style case lifecycle and operational events |
| `CasePartyRole` | **374,280** | 81 MB | Typed links between a case and complainant, victim, accused or other party |
| `CanonicalEntity` | **223,161** | 41 MB | Canonical cross-source entity identifiers |
| `CanonicalPerson` | **210,890** | 56 MB | Resolved synthetic person profiles |
| `EntityGraph` | **206,026** | **340 MB** | Governed graph nodes/relationships and graph provenance |
| `CaseSource` | **200,003** | 26 MB | Case-to-source-system mappings |
| `ActSectionAssociation` | **172,374** | 18 MB | Legal act/section associations for cases |
| `Accused` | **164,861** | 21 MB | Synthetic accused-party details |
| `SourceRecord` | **100,068** | 31 MB | Source lineage and content identity |
| `CaseMaster` | **100,003** | 69 MB | Primary FIR/case records |
| `CaseVersion` | **100,003** | 34 MB | Versioned case snapshots |
| `ComplainantDetails` | **100,003** | 17 MB | Synthetic complainant details |
| `Inv_OccuranceTime` | **100,000** | 5.8 MB | Incident/occurrence temporal information |
| `ArrestSurrender` | **72,762** | 13 MB | Arrest and surrender lifecycle records |
| `inv_arrestsurrenderaccused` | **72,762** | 5.8 MB | Arrest-to-accused join records |
| `Victim` | **71,604** | 9.6 MB | Synthetic victim-party details |
| `CourtEvent` | **64,391** | 9.7 MB | Court lifecycle events |
| `ChargesheetDetails` | **37,147** | 4 MB | Chargesheet records |
| `CaseDisposition` | **28,309** | 4.4 MB | Case disposition state |
| `OutcomeObservation` | **28,309** | 5.5 MB | Governed outcome observations for evaluation |
| `BailEvent` | **27,196** | 4.4 MB | Bail lifecycle events |
| `PropertyItem` | **13,766** | 3.2 MB | Stolen, recovered or case-linked property |
| `Seizure` | **13,642** | 2.1 MB | Property/evidence seizure events |
| `Employee` | **12,000** | 2.2 MB | Synthetic police employee records |
| `StatementVersion` | **11,091** | 2.4 MB | Versioned witness/party statements |
| `FinancialTransaction` | **11,049** | 7.8 MB | Synthetic transaction graph facts |
| `Statement` | **9,895** | 2 MB | Governed statements |
| `FinancialAccount` | **9,445** | 3 MB | Synthetic financial accounts |

`EntityGraph` is the largest relation because its 206,026 records carry both graph data and substantial indexing; its 340 MB footprint is split approximately between 167 MB of table data and 173 MB of indexes.

### Operational evidence and analytical tables

| Capability | Supporting tables and measured volume |
|---|---|
| Case lifecycle | `CaseMaster` 100,003; `CaseVersion` 100,003; `CaseEvent` 386,990; `CaseDisposition` 28,309 |
| Parties | `CasePartyRole` 374,280; `Accused` 164,861; `Victim` 71,604; `ComplainantDetails` 100,003 |
| Legal workflow | `ActSectionAssociation` 172,374; `ArrestSurrender` 72,762; `ChargesheetDetails` 37,147; `CourtEvent` 64,391; `BailEvent` 27,196 |
| Evidence | `EvidenceObject` 8,025; `EvidenceItem` 8,021; `EvidenceVersion` 8,009; `EvidenceCaseLink` 8,013; `EvidenceEntityLink` 5,276 |
| Property and seizure | `PropertyItem` 13,766; `Seizure` 13,642 |
| Digital and financial | `FinancialAccount` 9,445; `FinancialTransaction` 11,049; `TransactionLink` 3,120; `Device` 764; `DeviceArtifact` 764; `CommunicationEvent` 6,187 |
| Network intelligence | `EntityGraph` 206,026; `NetworkEdge` 4,739; `drishti_hidden_associations` 2,463; `CrimePatternCase` 889 |
| Geography | `JurisdictionBoundary` 1,263; `Unit` 1,032; `UnitLocation` 1,000; `District` 32; `State` 1; `CrimeHotspot` 41 |
| Forecasting | `CrimePrediction` 278; `FeatureSnapshot` 192; `PredictionRequest` 161; `PredictionResult` 161; `ForecastBacktest` 2 |
| Model governance | `ModelVersion` 21; `ModelBenchmark` 15; `ModelReview` 3; `PredictionReview` 1; `TrainingDatasetSnapshot` 3 |
| Data quality | `DataQualityIssue` 56; `EntityResolutionCandidate` 37; `EntityMergeHistory` 13; `IngestionJob` 20; `IngestionRecord` 24 |
| Audit and collaboration | `audit_logs` 77; `AlertHistory` 320; `ChatSession` 300; `ChatMessage` 592; `VoiceTranscript` 64 |

### Views and materialized projections

| Materialized view | Rows | Purpose |
|---|---:|---|
| `mv_crime_stats` | 831 | Pre-aggregated crime statistics |
| `mv_active_hotspots` | 41 | Current hotspot projection |
| `mv_district_risk_profile` | 0 | Future/refresh-controlled district risk projection |

The 20 ordinary views are:

`geography_columns`, `geometry_columns`, `pg_stat_statements`, `pg_stat_statements_info`, `vw_active_alerts`, `vw_arrest_details`, `vw_audit_events`, `vw_canonical_graph_edge`, `vw_canonical_graph_node`, `vw_case_parties`, `vw_caseversion_containment`, `vw_entity_link_queue`, `vw_evidence_quarantine_queue`, `vw_evidence_retention`, `vw_fir_full`, `vw_intake_inbox`, `vw_location_observation_containment`, `vw_model_review_due`, `vw_related_cases_by_person` and `vw_source_reconciliation`.

### PostgreSQL extensions

| Extension | Version | DRISHTI use |
|---|---:|---|
| PostGIS | 3.5.6 | Geography, boundaries, point-in-polygon and spatial indexing |
| pgRouting | 3.6.3 | Governed path/routing support |
| pgvector | 0.8.2 | Embeddings and semantic similarity |
| `pg_trgm` | 1.6 | Approximate text/entity matching |
| `pgcrypto` | 1.3 | Cryptographic database helpers |
| `uuid-ossp` | 1.1 | Stable UUID generation |
| `pg_stat_statements` | 1.11 | Query-performance observability |

### Empty tables are explicit future-state contracts

The following 22 tables currently have zero rows:

`CaseEvidence`, `CrimeEmbedding`, `CrimeRiskScore`, `DigitalImportBatch`, `ImportBatch`, `ImportStagingRow`, `JurisdictionReassignment`, `LabResult`, `LegalHold`, `MoneyAlert`, `MoneyAlertReview`, `NotificationDelivery`, `NotificationMessage`, `PersonAddress`, `PersonContact`, `PersonIdentifier`, `RagInteraction`, `ReportSnapshot`, `SavedFilter`, `SavedQuery`, `SpatialRepairRun` and `WorkTask`.

Zero rows do not mean an omitted schema. These tables preserve reviewed contracts for future workflows while preventing the prototype from fabricating activity that has not occurred—for example, legal holds, lab results, money-alert reviews or RAG interactions.

<details>
<summary><strong>Complete measured table inventory—140 ordinary tables</strong></summary>

#### Core cases and FIR taxonomy—987,211 rows

`CaseEvent` 386,990 · `CaseSource` 200,003 · `SourceRecord` 100,068 · `CaseMaster` 100,003 · `CaseVersion` 100,003 · `Inv_OccuranceTime` 100,000 · `CrimeHeadActSection` 44 · `CaseCategoryWorkflow` 36 · `CrimeSubHead` 26 · `CaseStatusMaster` 14 · `CrimeHead` 9 · `SourceSystem` 7 · `CaseCategory` 5 · `GravityOffence` 3

#### People, parties and organisations—1,156,931 rows

`CasePartyRole` 374,280 · `CanonicalEntity` 223,161 · `CanonicalPerson` 210,890 · `Accused` 164,861 · `ComplainantDetails` 100,003 · `Victim` 71,604 · `Employee` 12,000 · `CanonicalOrganisation` 60 · `PersonAlias` 20 · `OccupationMaster` 15 · `Rank` 12 · `CasteMaster` 10 · `Designation` 8 · `ReligionMaster` 7 · `PersonAddress` 0 · `PersonContact` 0 · `PersonIdentifier` 0

#### Legal, court and lifecycle—524,821 rows

`ActSectionAssociation` 172,374 · `ArrestSurrender` 72,762 · `inv_arrestsurrenderaccused` 72,762 · `CourtEvent` 64,391 · `ChargesheetDetails` 37,147 · `CaseDisposition` 28,309 · `OutcomeObservation` 28,309 · `BailEvent` 27,196 · `StatementVersion` 11,091 · `Statement` 9,895 · `Court` 500 · `Section` 45 · `OutcomeLabel` 32 · `Act` 8

#### Evidence, property, digital and financial—104,432 rows

`PropertyItem` 13,766 · `Seizure` 13,642 · `FinancialTransaction` 11,049 · `FinancialAccount` 9,445 · `EvidenceActivityEvent` 8,351 · `EvidenceObject` 8,025 · `EvidenceItem` 8,021 · `EvidenceCaseLink` 8,013 · `EvidenceVersion` 8,009 · `CommunicationEvent` 6,187 · `EvidenceEntityLink` 5,276 · `TransactionLink` 3,120 · `Device` 764 · `DeviceArtifact` 764 · `CaseEvidence` 0 · `DigitalImportBatch` 0 · `LabResult` 0 · `LegalHold` 0 · `MoneyAlert` 0 · `MoneyAlertReview` 0

#### Networks and intelligence—222,407 rows

`EntityGraph` 206,026 · `LocationObservation` 7,684 · `NetworkEdge` 4,739 · `drishti_hidden_associations` 2,463 · `CrimePatternCase` 889 · `GangMembership` 524 · `CrimePattern` 82

#### Geospatial and contextual—12,167 rows

`spatial_ref_sys` 8,500 · `JurisdictionBoundary` 1,263 · `Unit` 1,032 · `UnitLocation` 1,000 · `AreaContextObservation` 160 · `CrimeHotspot` 41 · `District` 32 · `EconomicIndicator` 32 · `SocialIndicator` 32 · `WeatherIndicator` 32 · `HolidayCalendar` 30 · `PublicEvent` 6 · `UnitType` 6 · `State` 1

#### ML, forecasts and model governance—1,335 rows

`ModelInference` 467 · `CrimePrediction` 278 · `FeatureSnapshot` 192 · `PredictionRequest` 161 · `PredictionResult` 161 · `ModelVersion` 21 · `FeatureDefinition` 20 · `ModelBenchmark` 15 · `OfficerRecommendation` 6 · `FeatureSchemaVersion` 3 · `ModelReview` 3 · `TrainingDatasetSnapshot` 3 · `AISummary` 2 · `ForecastBacktest` 2 · `PredictionReview` 1 · `CrimeEmbedding` 0 · `CrimeRiskScore` 0

#### Intake, import and data quality—282 rows

`IntakeDraftActivity` 87 · `DataQualityIssue` 56 · `EntityResolutionCandidate` 37 · `IngestionRecord` 24 · `IngestionJob` 20 · `EntityMergeHistory` 13 · `IntakeDraft` 12 · `ImportTemplateVersion` 9 · `ImportTemplate` 8 · `IntakeDraftParty` 8 · `ExternalSourceVersion` 4 · `SyntheticDataRun` 4 · `ImportBatch` 0 · `ImportStagingRow` 0 · `JurisdictionReassignment` 0 · `SpatialRepairRun` 0

#### Identity, audit, collaboration and reporting—1,559 rows

`ChatMessage` 592 · `AlertHistory` 320 · `ChatSession` 300 · `role_permissions` 150 · `audit_logs` 77 · `VoiceTranscript` 64 · `roles` 15 · `users` 12 · `DemoActor` 5 · `FeatureFlag` 5 · `NotificationPreference` 5 · `ReportTemplate` 5 · `synthetic_meta` 5 · `RetentionPolicy` 4 · `NotificationDelivery` 0 · `NotificationMessage` 0 · `RagInteraction` 0 · `ReportSnapshot` 0 · `SavedFilter` 0 · `SavedQuery` 0 · `WorkTask` 0

</details>

### Reproduce the read-only inventory

The inventory can be reproduced using the server-side `DATABASE_URL` from `.env`. Never print that value or add it to a browser environment variable.

```powershell
aws sso login --profile drishti
aws rds describe-db-instances --profile drishti

# Load the server-side URL into this process without printing it.
$dbLine = Get-Content .env |
  Where-Object { $_ -match '^DATABASE_URL=' } |
  Select-Object -First 1
$env:DATABASE_URL = $dbLine.Substring('DATABASE_URL='.Length)

# Read-only catalogue inspection + exact SELECT count(*) per ordinary table.
python scripts/database_inventory.py --exact --format markdown

Remove-Item Env:DATABASE_URL
```

Use `--format json` for machine-readable evidence. Omitting `--exact` uses faster planner estimates. The helper never prints the connection URL and does not modify or analyse database tables.

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
│   └── assets/
│       ├── benchmarks/           # Database and ML benchmark SVG dashboards
│       └── screenshots/          # Submission-safe prototype screenshots
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
├── scripts/
│   ├── database_inventory.py     # Read-only exact PostgreSQL inventory
│   └── ...                       # Validation and release automation
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
- Catalyst billing data are console-only for the current CLI session.
- The protected AWS analytics plane is optional and should be used only where Catalyst-native services cannot meet the compute requirement.
- The main JavaScript bundle is rich and should be code-split before broad production use.
- Development health verification is not equivalent to production load or resilience testing.
- Model outputs have not been validated on real operational data and must not be used for real enforcement decisions.

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
- [x] Make the GitHub repository publicly accessible.
- [x] Publish the three-minute demo video: [https://youtu.be/cp27iqfYYyA](https://youtu.be/cp27iqfYYyA).
- [x] Perform one final incognito walkthrough of the Catalyst URL.

---

## Responsible-use statement

DRISHTI is a synthetic hackathon demonstration of governed decision-support infrastructure. It is not a production policing system, does not determine guilt, and must not be used to make autonomous enforcement decisions. Any future real-world deployment requires legal authority, privacy controls, security review, model validation, community and institutional governance, operator training and continuous human accountability.

---

<p align="center">
  <strong>DRISHTI</strong><br />
  Observe · Understand · Review · Act · Audit
</p>


---

<a id="refined-prototype"></a>

# Refined prototype — September 2026

## Refined prototype demo video

**[Watch the refined prototype demo — Google Drive](https://drive.google.com/drive/folders/1oMSqotqN_BgQuFgE4RjRORn34GmbzdEh)**

This is the new demo video folder for the refined prototype. The submission links above are retained with the previous prototype.

## Previous prototype baseline

**Everything above this section is the preserved previous-prototype README.** Its submission links, ten presentation seats, database inventory, screenshots, benchmarks and infrastructure statements describe the earlier submission snapshot, last updated in commit `7139722` on 26 July 2026. They remain here so the development of DRISHTI can be reviewed without losing the original submission.

This appendix describes the refinement against that baseline. Code was inspected at `3667382`, with existing local dashboard/scope changes also present, on **7 September 2026**. Local screenshots show that working checkout; hosted screenshots show the separately deployed Slate application. A local feature does not establish deployment parity.

The twelve diagrams below are reused unchanged from the requested commit **`01c2b25bd5d1c50cf96c6d80eb31d10aca0a3c38`**. They describe architecture and interaction design, not live service-health evidence.

## Refined prototype contents

- [Executive summary and solution](#refined-summary)
- [Previous prototype → refined prototype](#refined-changes)
- [Users, roles, KPI cards and analytics](#refined-roles)
- [Process flows and use cases](#refined-flows)
- [Architecture, data and request lifecycle](#refined-architecture)
- [Zoho Catalyst additions and integrations](#refined-zoho)
- [AWS additions and integrations](#refined-aws)
- [Wireframes and interaction design](#refined-wireframes)
- [Actual browser screenshots](#refined-screenshots)
- [Validation, deployment and remaining work](#refined-validation)

<a id="refined-summary"></a>

## Executive summary and brief about the refined solution

DRISHTI has evolved from a broad crime-intelligence and emergency-response demonstration into a more explicit operational workspace. The refinement connects a user's posting to their dashboard, adds administration of role surfaces and visibility, extends intake with reviewed form scanning and face enrolment, and adds a CCTV review workspace and continuous conversational assistance.

The underlying problem remains fragmented information: a supervisor needs jurisdiction-level workload and outcomes, while an investigating officer needs assigned cases and the next review action. The refined design makes that distinction visible through scoped seats, role-specific cards, provenance, capability indicators and separate human approval steps.

**Refined USP:** one connected case and entity model, several operational views, and visible review boundaries between a machine suggestion and an officer's decision. Photos, similarity scores, forecasts and correlations are supporting information; none establishes guilt or authorizes enforcement.

### Opportunities and expected impact

| Opportunity | Refinement | Intended benefit |
|---|---|---|
| Reduce navigation between disconnected tools | Case, people, face search, board, map, intake and assistant destinations share the shell | Preserve investigation context |
| Make command reporting relevant | Posting-aware dashboards and comparison widgets | Review the correct jurisdiction and workload |
| Reduce repetitive form entry | Zia OCR proposal → field review → intake draft | Faster entry while preserving corrections and provenance |
| Improve situational review | Camera map, feed panel and alert-review queue | Separate scene detection, confirmation and response |
| Improve explainability | Metric help, data-age labels, model/capability state and correlation context | Make uncertainty and data limitations visible |
| Make operations maintainable | Roles, seat profiles, UI visibility and platform administration | Manage access intent and presentation centrally |

These are intended benefits. No new field-study outcome, accuracy claim or productivity percentage is asserted by this documentation update.

<a id="refined-changes"></a>

## What changed from the previous prototype

| Topic | Previous prototype baseline | Refined implementation / current evidence |
|---|---|---|
| Entry experience | Role-oriented submission login and earlier landing design | Reworked landing page and searchable operational seat picker, grouped by posting type |
| Role model | Ten presentation seats described above | **Six canonical application roles**; role surface is separate from geographic or functional scope |
| Command Center | Earlier generic role home components | Registry-driven KPI cards and boards for state, wing, range, district, commissionerate, station, assigned cases and platform |
| Scope | Earlier role and district controls | Server-resolved posting, scope trail and jurisdiction-aware data hooks; local scope/cache refinements are in progress |
| KPI meaning | Broad dashboard metrics | Explicit workload, ageing, time-to-chargesheet, prosecution/conviction, data freshness, suppression and model-quality concepts |
| Contextual analytics | Earlier socioeconomic presentation | Ranked correlation bars, indicator scatter plots, selected-district context, crime-type selectors and non-causal interpretation |
| Administration | Earlier administration/governance panels | Roles & permissions, seat profiles and UI visibility panels; custom roles reuse a base application surface |
| Written FIR intake | Structured manual draft and approval workflow | Scanned-form route, printable form, proposed-field review and OCR provenance; capability remains flag-gated |
| Face workflow | No equivalent dedicated end-to-end face workflow in the preserved gallery | Camera/upload search, detector/encoder telemetry, ranked candidates, search history and enrolment UI |
| Intake-to-person linkage | Earlier people entry | Captured intake face can be enrolled against the canonical person created by the intake approval path |
| Bulk gallery | No documented bulk enrolment command in the earlier README | `face-enrol-portraits` batch command for indexed reference-photo ingestion |
| CCTV | Earlier map and emergency snapshots | Live Watch Wall with camera estate, clips/feed panels, scene detections, human alert review and responder context |
| Ask DRISHTI | Earlier cited text and browser voice experience | AWS Bedrock text planner integration plus continuous voice UI; Nova 2 Sonic / AgentCore transport implemented separately |
| Shared interface | Earlier shell | Refined navigation, command bar, language controls, profile and support views |
| Documentation | Earlier embedded diagrams and snapshots | Twelve code-oriented diagrams from the requested commit plus a dated browser-evidence gallery |

### Changes after the diagram commit

| Commit | Relevant addition |
|---|---|
| `876d897` | AppSail deployment support for the real face-recognition runtime |
| `80e3adf` | Ignore local face-provisioning scratch directories that can contain database configuration |
| `3667382` | Make an intake face capture searchable for the person created by that intake |

The production dashboard document in [docs/production-role-dashboard-plan.md](docs/production-role-dashboard-plan.md) remains a **design plan**. Its complete KPI selection, layout limits and acceptance criteria must not be read as already delivered merely because the plan exists.

<a id="refined-roles"></a>

## Users, roles, KPI cards and analytics

There are **six core application roles**, defined in [frontend roles](web/src/config/roles.ts) and [backend roles](services/ml/app/roles.py). ADGP/DIG and SP/CP are posting variants, not additional core roles. Administrator-created custom roles are an extension mechanism and are not included in this core count.

| Core role | Seat scope | KPI and analytics emphasis |
|---|---|---|
| DGP / State Command — `dgp_state_command` | State | Incidents and change, open workload, alerts, outcome throughput, ageing, resource balance, forecast quality and data quality; range/district comparisons, trend, forecast and case pipeline |
| Senior Command — `senior_command` | Functional wing or range | Wing crime-head mix or range district comparison; trends, open workload, chargesheet throughput, overdue work, hotspots and forecast; wing-specific financial/traffic cards when applicable |
| District Command — `district_command` | District or commissionerate | Station performance, new FIRs, open cases, overdue reviews, median days to chargesheet, disposal/outcome rates, officer load and forecast |
| SHO — `sho` | Station | Registration/review queue, station workload, ageing, pending evidence, hearings, officer load, station trend and jurisdiction map |
| Investigating Officer — `investigating_officer` | Assigned cases within posting | Own cases, tasks, review deadlines, evidence and leads, with posting context; district socioeconomic comparisons are excluded from this board |
| System Admin — `system_admin` | Platform | Platform status, usage, queues, identity/roles, seat profiles, UI visibility, audit, model review and operational administration |

**Eight valid scope-board types:** state, wing, range, district, commissionerate, station, assigned_case and platform. An unresolved posting is a no-data state, not permission to show the whole state.

Card applicability and ordering are maintained in [KPI registry](web/src/config/kpi/registry.ts) and [role boards](web/src/config/kpi/roleBoards.ts). The table above summarizes their emphasis; it is not a promise that every card is populated in every environment.

### Metric and graph interpretation

- Use the visible date window and data-as-of labels. The synthetic corpus includes historical dates; a dashboard opened today is not automatically a live incident feed.
- “Time to chargesheet” measures a filing milestone. It is distinct from final court disposal.
- Court-outcome rates need explicit denominators and enough observations. The station board intentionally omits conviction and prosecution rates.
- Socioeconomic indicators are district-grain context, even when viewed from a narrower posting. Correlation bars and scatter plots do not support causal or individual-level accusations.
- Missing, unavailable or policy-incompatible artifacts must stay visibly unavailable. An em dash is not a zero.
- State and wing surfaces are designed for aggregate review. Frontend visibility is not an authorization boundary; permission and jurisdiction checks belong on the server.

<a id="refined-flows"></a>

## Process flows and use-case diagrams

The refinement keeps an explicit chain from observation to review and audit.

### Operational process

![Refined operational process](docs/assets/diagrams/png/flow-01-operational-process.png)

Signals and records enter the workspace, are connected to the case/entity model, and support reviewed action. The diagram represents the intended controlled process, not unattended police operations.

### Role and use-case relationships

![Refined use-case diagram](docs/assets/diagrams/png/flow-02-use-case.png)

### Send to Investigation Board

![Send to Board flow](docs/assets/diagrams/png/flow-03-send-to-board.png)

Case and entity references become an investigation workspace with source-backed links and annotations. A link is not proof of wrongdoing.

### Model governance

![Model governance flow](docs/assets/diagrams/png/flow-04-model-governance.png)

### Newly added workflow details

| Workflow | Sequence | Human checkpoint |
|---|---|---|
| Scanned FIR | Form image → Zia text extraction → derived field proposals → reviewed values → draft | Officer confirms fields; normal approval creates the case |
| Face search | Reference enrolment → image acquisition → face detection/alignment → descriptor → candidate search | Similarity result remains a lead requiring confirmation |
| Intake face linkage | Capture in people step → approved canonical person → enrolment | Preserve association to the created record and enrolment result |
| CCTV review | Enabled camera/clip → analysis pass → scene detection → review queue → response context | A machine detection must be reviewed before consequential action |
| Voice Ask | Voice/text query → existing guarded Ask service → cited result cards → spoken response | Read-only grounded answers support the user's review |

<a id="refined-architecture"></a>

## Detailed architecture, tech stack and data boundaries

### System architecture

![Refined system architecture](docs/assets/diagrams/png/arch-01-system.png)

### Request lifecycle

![Refined request lifecycle](docs/assets/diagrams/png/arch-02-request-lifecycle.png)

### Data architecture

![Refined data architecture](docs/assets/diagrams/png/arch-03-data.png)

The diagrams illustrate the **target service allocation**. The synthetic deployment also has an explicitly documented server-to-server AppSail → RDS bridge for domains still awaiting Catalyst Data Store migration. Consequently, the diagrams must not be used to claim that every operational route is Data Store-native or every analytical request already traverses the AWS adapter.

The current boundary inventory is [deployment_boundary.py](services/ml/app/deployment_boundary.py). It records operational migration gaps, analytical dependencies and local-only tooling. Database credentials remain server-side; the browser does not connect directly to RDS.

| Layer | Refinement-relevant technology |
|---|---|
| Interface | React, TypeScript, Vite, role/seat stores, reusable KPI and chart widgets |
| Application runtime | FastAPI on Zoho Catalyst AppSail; Catalyst API Gateway and gateway function context |
| Operational storage | Catalyst Data Store / Stratus repositories, with documented RDS migration gaps |
| Spatial and relational analytics | PostgreSQL/PostGIS/pgRouting on the AWS data plane |
| Face search | SCRFD/ArcFace ONNX encoder family and model-version-compatible pgvector descriptors |
| Grounded language | Bedrock text planner through the configured guarded Ask path |
| Continuous audio | Nova 2 Sonic and a separate AgentCore relay when enabled; browser speech fallback |
| Intake OCR | Catalyst Zia OCR for reviewed intake forms |
| Governance | Audit records, provenance, capability flags and model-policy checks |

Face recognition here is the application's ONNX/ArcFace runtime. It is not an AWS Rekognition or Zoho Zia face-recognition integration. Encoder/model availability is checked independently from the existence of reference images.

<a id="refined-zoho"></a>

## Zoho Catalyst services used in the refinement

Many Zoho services were already part of the previous architecture. The refinement extends the workflows on that foundation; it does not introduce every service in this table for the first time.

| Zoho component | Role in the refined prototype | Evidence and status |
|---|---|---|
| Slate | Hosts the refined web interface | Hosted pages captured below; deployment can lag the local checkout |
| Authentication, API Gateway and gateway function | Resolve application context and forward signed server context to AppSail | [Gateway implementation](infra/catalyst/functions/gateway_api/index.js); demo seat selection is not proof of production identity provisioning |
| AppSail | Hosts API services, face runtime integration and voice ticket/tool endpoints | [AppSail build](services/ml/Dockerfile.appsail), [voice deployment notes](docs/nova-sonic-voice.md) |
| Data Store | Operational repositories including CCTV records and board canvas, with domain-specific migration status | [Boundary inventory](services/ml/app/deployment_boundary.py); complete migration is not claimed |
| Stratus | Deployed object-storage path for supported evidence/export/media operations | [Stratus client](services/ml/app/stratus.py); retain per-domain storage configuration |
| **Zia OCR** | New reviewed written-FIR form-reading lane | [OCR client](services/ml/app/zia_ocr.py), [scan UI](web/src/routes/intake/scan/ScanFir.tsx); **disabled on the local server at capture time** |
| Cache / NoSQL | Existing reusable client integrations for caching and supported persistence | Runtime flag and repository dependent |
| SmartBrowz | Existing report/rendering integration | Presence of client code is not evidence of a successful current export |
| QuickML | Existing alternative planner/RAG integration | Do not describe it as the active planner when the UI reports `aws-bedrock` |
| Jobs, Signals, Mail/Push, Connections and Pipelines | Existing supporting integration/configuration | Enablement and console-managed configuration require separate verification |

Zia OCR supplies document text and a document-level confidence score. DRISHTI derives field proposals and field-level confidence; it must not attribute those derived scores directly to Zia. Scanning a form does not autonomously register an FIR.

The [Catalyst component index](infra/catalyst/COMPONENTS.md) contains earlier phase notes. Its older “primary QuickML” and browser-only voice wording is historical where superseded by the newer Bedrock and Sonic implementation.

<a id="refined-aws"></a>

## AWS services and features added or extended

| AWS capability | Refinement | Verification boundary |
|---|---|---|
| **Amazon Bedrock text planning** | Configured GLM 4.7 Flash planner for grounded Ask; guarded read-only query path remains in place | Local Ask reported `aws-bedrock`; this capture did not submit a new query |
| **Amazon Nova 2 Sonic** | Continuous speech input/output with grounded Ask tool calls and separate structured result cards | Implemented and previously tested in the voice deployment notes; not demonstrated by the browser-speech screenshot below |
| **Bedrock AgentCore runtime** | Separate WebSocket audio relay because the recorded AppSail public WebSocket upgrade failed | Server issues short-lived voice tickets and presigned connection details; relay has a separate deployment lifecycle |
| API Gateway / signed adapter | Bounded server-to-server entry to retained AWS analytical/model capabilities | HMAC timestamp, nonce and result verification in the adapter; this is not a general browser SQL proxy |
| RDS with PostGIS/pgRouting | Retained relational, graph and spatial processing; current synthetic operational bridge | Operational migration gaps remain explicit |
| S3 / custom model infrastructure | Configured staging and retained custom-model workloads where needed | Do not infer that all SageMaker/Batch jobs or GPU endpoints are deployed from configuration alone |
| IAM / ECR / runtime logging | Scoped relay role, container publishing and service diagnostics | Configuration and prior deployment evidence, not a fresh cloud audit |

### Voice request lifecycle

1. The authenticated gateway/AppSail path issues a short-lived voice ticket.
2. The browser connects to the configured AgentCore relay; signing secrets remain server-side.
3. Nova invokes the existing `ask_drishti` tool through an owner/role-bound token.
4. The existing Ask service performs guarded retrieval/querying and returns grounded results.
5. The UI receives structured answer cards and the speech layer presents a spoken response.

The repository's [Nova voice notes](docs/nova-sonic-voice.md), dated 31 August 2026, record successful continuous hosted probes and the use of `us-east-1` for audio. They also distinguish English Nova voices from Kannada browser speech. Those are **previously recorded tests**, not tests rerun during this README update.

### Cost and operations

No new rupee estimate is attached to this refinement: usage volume and a current bill were not measured. Bedrock text/audio, AgentCore runtime, RDS, object storage and optional model workers have separate cost drivers. Track tokens/audio duration, runtime sessions, storage and worker hours; configure budgets and quotas before a larger rollout. The earlier cost section remains a historical estimate.

<a id="refined-wireframes"></a>

## Wireframes and mock diagrams

These are design diagrams from `01c2b25`, separate from the actual screenshots that follow. [Editable SVGs and diagram provenance](docs/assets/diagrams/README.md) are retained.

<details>
<summary>Login and operational seat selection</summary>

![Login wireframe](docs/assets/diagrams/png/wire-01-login.png)

</details>

<details>
<summary>Application shell and scoped navigation</summary>

![Application shell wireframe](docs/assets/diagrams/png/wire-02-app-shell.png)

</details>

<details>
<summary>Map and hotspot investigation</summary>

![Map wireframe](docs/assets/diagrams/png/wire-03-map-hotspots.png)

</details>

<details>
<summary>Investigation Board</summary>

![Investigation Board wireframe](docs/assets/diagrams/png/wire-04-investigation-board.png)

</details>

<details>
<summary>Case file and Ask DRISHTI</summary>

![Case file and Ask wireframe](docs/assets/diagrams/png/wire-05-case-file-and-ask.png)

</details>

<a id="refined-screenshots"></a>

## Refined prototype snapshots — actual browser captures

Captured on **7 September 2026**, using the actual local and hosted application. These are unaltered browser screenshots, not generated mockups. Local captures include existing uncommitted work. Values are synthetic snapshot observations and will change as background enrolment and data updates continue.

### 1. Searchable operational seat selection — local

![Refined seat selection](docs/assets/screenshots/refined/01-seat-selection.png)

Posting categories and named seats replace the earlier presentation-only role catalogue. Screenshot source: `http://localhost:5173/login`.

### 2. District command KPI board — local

![Refined district command](docs/assets/screenshots/refined/05-district-command.png)

The Mysuru district seat loaded workload, new FIR, ageing, outcome and resource metrics. Some downstream hotspot/attention widgets rejected artifacts generated under an older analytics policy; this capture is not evidence that every widget passed. Source: `http://localhost:5173/command`.

### 3. Active face engine and reference gallery — local

![Active face recognition runtime](docs/assets/screenshots/refined/07-local-face-engine.png)

The resolved capability reported **ArcFace buffalo_s**, CPU execution and **15,343 enrolled people/reference photos** at observation time. This is a gallery snapshot, not an accused-person total or an accuracy benchmark. No new photo was uploaded or searched for this documentation. Source: `http://localhost:5173/people/face`.

### 4. Intake review inbox — local

![Intake review inbox](docs/assets/screenshots/refined/06-intake-review.png)

Draft/review states remain separate from approved registration. Source: `http://localhost:5173/intake`.

### 5. Zoho Zia scan capability gate — local

![Zia scanned FIR capability state](docs/assets/screenshots/refined/08-zia-scan-capability.png)

The new scanned-FIR screen explicitly reports that OCR is not switched on in this server configuration. It preserves manual entry. This is evidence of the implemented capability gate, not a successful OCR extraction. Source: `http://localhost:5173/intake/scan`.

### 6. Continuous voice interface with Bedrock text planner — local

![Voice conversation controls](docs/assets/screenshots/refined/09-voice-conversation.png)

The dialog exposes continuous conversation, speaking voice and speed. It reports **browser speech with aws-bedrock**, so this screenshot must not be captioned as a successful Nova Sonic audio session. No answer was generated during the capture; the capture tab was closed afterward. Source: `http://localhost:5173/ask`.

<details>
<summary>Hosted deployment observations — capability and readiness evidence</summary>

#### Live Watch Wall

![Hosted watch wall readiness state](docs/assets/screenshots/refined/02-live-watch-wall.png)

The hosted watch route displayed its map/review interface with **internal server errors**. No analysis pass, seed operation or dispatch was run. Source: `https://drishti-frvfpunc.onslate.in/watch`.

#### Face search resolved capability state

![Hosted face search capability state](docs/assets/screenshots/refined/03-face-search.png)

The initial page load briefly displayed unavailable capability information; the saved screenshot shows the resolved **ArcFace buffalo_s** engine, **15,343** enrolled reference photos and a **72%** configured match threshold. Both local and hosted views therefore reported an active engine. This verifies capability display, not recognition accuracy or a new search. Source: `https://drishti-frvfpunc.onslate.in/people/face`.

#### Ask voice fallback

![Hosted Ask voice fallback](docs/assets/screenshots/refined/04-ask-voice.png)

The captured hosted Ask view exposed browser voice. A current successful Nova session was not verified. Source: `https://drishti-frvfpunc.onslate.in/ask`.

</details>

<a id="refined-validation"></a>

## Performance, validation and release readiness

This update verifies documentation and captures browser states. It does not replace a release test run.

| Check | Result / interpretation |
|---|---|
| Previous README preservation | Original content retained above this appendix |
| Requested diagram provenance | All twelve PNG diagrams reused from `01c2b25`; SVG sources retained |
| Local seat picker | Named district seats loaded |
| Local district dashboard | Populated metrics observed; some analytical artifacts were incompatible with the current policy |
| Local face capability | Active ArcFace runtime and enrolled gallery observed |
| Local OCR | Explicitly disabled; successful form extraction not tested |
| Local Ask | Bedrock planner label and browser-speech continuous UI observed; no fresh answer/audio probe |
| Hosted watch wall | Server errors observed; requires backend investigation before presentation as working |
| Hosted admin | New roles/profile/visibility navigation observed; role list did not resolve during inspection |
| Build, load, security and full regression tests | Not rerun for this documentation-only change |
| Previously recorded voice tests | See dated [voice notes](docs/nova-sonic-voice.md); do not treat as current deployment certification |

### Security, privacy and AI governance

The prototype still uses synthetic demonstration data. Random or synthetic portraits are reference assets for the demo; they do not represent the real identity of a named person. A face candidate is an investigative lead, and a similarity percentage is not the probability that a person committed an offence.

The current boundary inventory explicitly records **RLS disabled for the hackathon** and operational RDS migration gaps. A production-looking interface does not establish production security. Before handling real records, validate server permissions across every endpoint, identity provisioning, jurisdiction denial, audit coverage, retention and model behaviour.

### Repository and local-run pointers

| Area | Current location |
|---|---|
| Role and scope definitions | `web/src/config/roles.ts`, `services/ml/app/roles.py` |
| Command boards | `web/src/config/kpi/`, `web/src/routes/home/` |
| Role administration | `web/src/routes/admin/`, `services/ml/app/admin_console/` |
| Reviewed scanned intake | `web/src/routes/intake/scan/`, `services/ml/app/intake/` |
| Face UI and service | `web/src/routes/face/`, `web/src/components/face/`, `services/ml/app/face/` |
| CCTV UI and service | `web/src/routes/watch/`, `services/ml/app/cctv/` |
| AWS adapter and voice relay | `services/aws-adapter/`, `services/voice-relay/` |
| New screenshots | `docs/assets/screenshots/refined/` |

Use the earlier local setup instructions with the current environment templates and [AppSail deployment guide](infra/catalyst/appsail/README.md). Frontend `npm run build` includes TypeScript validation, Slate post-build handling and bundle secret checking. Use the voice guide for the separate relay deployment; deploying only AppSail does not update AgentCore's image. Do not copy credentials into the README or frontend.

### Future development and submission checklist

- [ ] Align the hosted frontend, AppSail API and voice relay versions.
- [ ] Resolve hosted CCTV errors and verify camera → detection → human review behaviour.
- [ ] Regenerate or migrate analytical artifacts rejected by the current policy.
- [ ] Enable and test Zia OCR in the intended environment with reviewed sample forms.
- [ ] Verify fresh Nova two-turn audio, fallback behaviour and language support in the intended browser.
- [ ] Complete and validate gallery enrolment, model compatibility and intake-to-person linkage.
- [ ] Exercise all six roles and eight scopes, including unresolved and forbidden-jurisdiction cases.
- [ ] Complete the remaining Data Store migration and production authorization work.
- [ ] Apply and validate the separate production dashboard plan before describing it as shipped.
- [x] Add the user-provided refined prototype demo video link above.
- [ ] Record updated benchmarks and deployment evidence once the above checks pass.

The earlier prototype remains available above for comparison; this appendix is the dated record of the refined implementation, its diagrams and the browser states actually observed.
