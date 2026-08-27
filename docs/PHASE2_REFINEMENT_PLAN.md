# DRISHTI — Phase 2 Prototype Refinement Plan

**Status:** Proposal for review
**Prepared:** 26 August 2026
**Scope:** Prototype refinement phase following Phase 1 selection
**Baseline audited:** `web/` (~200 files, ~28k LOC, 30 routes), `services/ml/` (31 routers, ~330 endpoints), `datagen/` (40 modules), 140-table PostgreSQL corpus (3,011,145 rows)

---

## Table of contents

1. [The honest starting position](#1-the-honest-starting-position)
2. [What "5x better" actually means here](#2-what-5x-better-actually-means-here)
3. [Competitive benchmark: what world-class platforms do](#3-competitive-benchmark-what-world-class-platforms-do)
4. [The three strategic pivots](#4-the-three-strategic-pivots)
5. [Workstream 1 — Statutory Compliance & Case Clock Engine](#5-workstream-1--statutory-compliance--case-clock-engine)
6. [Workstream 2 — Crime Linkage & Serial Offender Engine](#6-workstream-2--crime-linkage--serial-offender-engine)
7. [Workstream 3 — Closed-Loop Tasking & Outcome Feedback](#7-workstream-3--closed-loop-tasking--outcome-feedback)
8. [Workstream 4 — Real-Time Operations & Deconfliction](#8-workstream-4--real-time-operations--deconfliction)
9. [Workstream 5 — Make the AI Genuinely Real](#9-workstream-5--make-the-ai-genuinely-real)
10. [Workstream 6 — Temporal Fusion & Chronology](#10-workstream-6--temporal-fusion--chronology)
11. [Workstream 7 — Real RBAC, Purpose-Based Access & Redaction](#11-workstream-7--real-rbac-purpose-based-access--redaction)
12. [Workstream 8 — Field Mobility & Chain of Custody](#12-workstream-8--field-mobility--chain-of-custody)
13. [Workstream 9 — Command & Supervisory Intelligence](#13-workstream-9--command--supervisory-intelligence)
14. [Workstream 10 — Foundation, Performance & Craft](#14-workstream-10--foundation-performance--craft)
15. [Prioritisation and sequencing](#15-prioritisation-and-sequencing)
16. [The golden-thread demo](#16-the-golden-thread-demo)
17. [What NOT to build](#17-what-not-to-build)
18. [Risks and mitigations](#18-risks-and-mitigations)
19. [Measurable success criteria](#19-measurable-success-criteria)
20. [Sources](#20-sources)

---

## 1. The honest starting position

Before deciding what to add, it is worth being precise about what Phase 1 actually delivered. I audited the code rather than the README, and the gap between the two is the most important input to this plan.

### 1.1 What is genuinely strong

These are real and should be protected in Phase 2:

| Capability | Evidence in code |
|---|---|
| **Breadth of governed surface** | 30 routes, ~330 endpoints, 27 typed API modules, `web/src/api/types.ts` is 2,618 lines of hand-mirrored schemas. There is **no mock data layer** — every screen hits a live service. |
| **Investigation Board** | The deepest feature in the app: ~2.6k LOC across `BoardWorkspace.tsx` + `components/board/*`, ~36 endpoints including branch, diff, promote-edge, search-around, presence, export. This is the closest thing to a genuine analyst tool in the build. |
| **Audit trail** | Real, not aspirational. `app/audit.py:127-149` writes rows to `audit_logs`; passing `conn` makes the audit row **transactional with the action** (`:152-163`), so a rolled-back action rolls back its audit. `_SENSITIVE_KEY_PARTS` (`:53-64`) strips passwords, narratives, DOB, phone, Aadhaar, lat/lon before storage. |
| **NL→SQL safety architecture** | Genuinely well-designed. `nlsql/scope.py:enforce_scope()` re-checks the *final* SQL after the planner, independently of it, on top of `SET ROLE drishti_readonly` + read-only transaction (`db.py:86-103`). The planner is never trusted. Replies are built from actual rows (`engine.py:302-357`), not templated. |
| **Model provenance discipline** | `ModelVersion` + `ModelInference` written on every ML path. `nlsql/engine.py:459-465` logs the question, planner source, SHA-256 of executed SQL, row/citation counts and refusal flag. |
| **Fail-closed GPU contract** | `forecast/timesfm.py:192-195` refuses a result that isn't TimesFM-on-CUDA. `gpu-worker/backends.py:66-73` `_require_cuda()`. The system will not return a CPU stat model labelled as a foundation model. |
| **Real pgvector ANN** | `cases/similar.py:157-166` — genuine `ORDER BY ce."Embedding" <=> %s::vector` HNSW cosine search, with query and corpus forced into the same embedding space via `embedder_for_model_name()`. |
| **Data corpus** | 3.01M rows across 140 tables with real referential depth: 386,990 `CaseEvent`, 374,280 `CasePartyRole`, 172,374 `ActSectionAssociation`, 72,762 `ArrestSurrender`, 64,391 `CourtEvent`, 37,147 `ChargesheetDetails`, 28,309 `CaseDisposition` + `OutcomeObservation`. |

### 1.2 What is decorative, stubbed, or running on a fallback

This is the part a Phase 2 jury will probe. Every item below is a specific, fixable finding:

**The headline AI is running on fallbacks with shipped defaults.**

| Marquee claim | What actually executes by default | Where |
|---|---|---|
| Ask DRISHTI NL→SQL | `FallbackPlanner` — a **regex intent matcher** with keyword cue sets | `nlsql/planner.py:236-320`, selected at `:427-443` because `semantic_planner_provider = ""` (`config.py:73`) |
| TimesFM forecasting | `SeasonalForecaster` — deseasonalised level+trend, numpy only | `forecast/timesfm.py:52-73`, selected at `:220-229` |
| Similar-case search | `HashingEmbedder` — signed feature hashing over word tokens + char trigrams | `cases/embeddings.py:56-92`, selected at `:122-136` |
| Offender risk (TabFM) | `InContextFoundationModel` — distance-weighted kNN | `risk/models_iface.py:49-79`, selected at `:262-291` |

To the team's credit, this is disclosed (`config.py:245-257` `primary_planner_name()` returns `"deterministic-fallback"` honestly, and the API surfaces `planner_degraded`). But the measured benchmark in the README is blunt about the consequence: the in-context serving model scores **0.4141 accuracy vs 0.6484 for a prior-period baseline**. The system correctly refuses to auto-promote it. That is good governance and a weak headline.

**RBAC is decorative on both sides of the wire.**

- `web/src/config/roles.ts:170-172` — `roleCan()` unconditionally `return true`. Every `Lock` / `EmptyState` gate in the app is unreachable dead UI: `CaseExplorer.tsx:65-76`, `CaseFile.tsx:113-125`, `EntityExplorer.tsx:70-81`, `NetworkAnalysis.tsx:41-52`, `Analytics.tsx:34-36`, `IntakeInbox.tsx:56-64`, `MapHotspots.tsx:113-115`.
- `services/ml/app/roles.py:14-24` states the interim model outright: *every role currently holds every capability*. `org/scope.py` `can_view_aggregate_dashboard` (`:196`), `can_export` (`:201`), `can_use_investigation_board` (`:206`) all reduce to `return scope.role in ALL_ROLES`.
- Worse, geographic narrowing is inert in the default path: `org/scope.py:127-135` — a district or station seat with no trusted district assignment gets `districts, units = None, None`, i.e. **no narrowing at all**.
- `X-Role` is trusted by default. `GatewayContextEnforcementMiddleware` is a **no-op unless `DRISHTI_REQUIRE_GATEWAY_CONTEXT` is set** (`main.py:99-101`). Any client can send `X-Role: dgp_state_command`.

**There is no real-time layer.** Zero WebSocket, zero EventSource anywhere in `web/src`. Everything is interval polling: board activity 4s (`useBoard.ts:87-130`), presence 5s (`:47-80`), alerts 120s, health 60s. The SSE channel exists (`stream/router.py:122`) but is flag-gated off and is **single-instance only, no cross-instance broker** (`:77-80`).

**Hard stubs shipping in the product surface.**

- `zia_voice.py:102`, `:105`, `:108` — `transcribe` / `synthesize` / `translate` all raise `NotImplementedError`.
- `smartbrowz.py:47-56` — report PDF export returns literal `PNGSTUB DRISHTI [...]` bytes.
- `quickml.py:55-77` `OfflineRag` — refuses by default; it is the default from `get_rag()`.
- `routes/map/MapHotspots.tsx:121` — red-zone alert acknowledgement is `useState<Set<number>>`, never POSTed. Acknowledging an alert does nothing.
- Saved queries, saved cohorts, recents and dashboard layouts are **localStorage only** (`stores/useSavedQueriesStore.ts:26` and siblings) — lost across devices, invisible to supervisors.
- `routes/Placeholder.tsx` — orphaned "Being built in a later Wave-C phase" screen, not imported anywhere.
- `components/ask/Composer.tsx:17` — hardcoded UI chip reading `"NL→SQL · Phase 2"`.
- `routes/intake/IntakeInbox.tsx:49-50`, `FirWizard.tsx:64-65` — user-visible copy reading *"disabled until Prompt 3 finalises hackathon mode"*. Internal prompt numbering is leaking into the product.
- `routes/emergency/SituationOverview.tsx:38-49` — "Seed demo scenario" and "Fetch live feed" buttons are demo scaffolding sitting in the operational UI.

**Engineering debt that will bite under evaluation load.**

- `db.py:12-14` — **no connection pooling, by design.** A fresh psycopg2 connect per context-manager entry. This is the first thing that falls over if a jury clicks around concurrently.
- Main JS bundle is **3,836 kB raw / 1,044 kB gzip**, plus a 1,054 kB MapLibre chunk. No route-level code splitting.
- No virtualization despite 12k-point maps and long tables. No error boundary. No toast system. No i18n framework — Kannada has font support (`tailwind.config.js:113-118`) and script detection (`lib/lang.ts`, 19 lines) but the entire UI chrome is English-only.

**A live ethical inconsistency worth resolving.** The README states *"no person re-scoring"*, but `risk/router.py:21` exposes `GET /risk/entity/{id}?rescore=true` and `:29` exposes `GET /risk/{accused_id}` — person-level risk scores with on-demand rescoring. Phase 2 must either defend this coherently (investigative prioritisation, strict controls, no coercive use) or remove it. Leaving the contradiction in place is the single easiest thing for an evaluator to attack.

### 1.3 The one-sentence diagnosis

> DRISHTI Phase 1 is an unusually broad, well-governed **reference implementation** in which the headline intelligence runs on statistical fallbacks, access control is presentational, nothing happens in real time, and no insight ever closes the loop back into a measured outcome.

Phase 2 should not make it wider. It should make it *true*.

---

## 2. What "5x better" actually means here

The instinct in a refinement phase is to add screens. That would be the wrong move: at 30 routes and ~330 endpoints, DRISHTI already has more surface than any competitor is likely to show, and adding an 11th destination dilutes rather than deepens.

Five multipliers that actually compound:

| Multiplier | From | To |
|---|---|---|
| **1. Depth over breadth** | Four marquee models running on fallbacks | Each headline capability either genuinely real, or explicitly labelled and benchmarked against a baseline it beats |
| **2. Closed loop** | Observe → Understand → Recommend → *(nothing)* | Observe → Understand → Recommend → **Task → Act → Outcome → Measure → Re-rank** |
| **3. Statutory reality** | Generic crime-intelligence platform | A platform that understands BNS/BNSS/BSA obligations, clocks and forensic mandates — something no generic product does |
| **4. Liveness** | Polling a database | A real-time operational picture with cross-agency deconfliction and officer-safety alerting |
| **5. Trustworthiness** | `roleCan() { return true }` | Enforced RBAC, purpose-of-access, statutory redaction, access-anomaly detection |

Notice what these have in common: **every one is achievable on the existing schema and existing infrastructure.** The 3.01M-row corpus already contains 172,374 section associations, 72,762 arrests, 37,147 chargesheets, 64,391 court events and 28,309 outcome observations. Most of the plan below is about finally *using* data that is already sitting there.

---

## 3. Competitive benchmark: what world-class platforms do

I looked at what the reference platforms actually provide, then mapped each capability against DRISHTI's current state. Content below is summarised from vendor and public-sector sources; see [Sources](#20-sources).

### 3.1 Palantir Gotham

Gotham is described as the archetypal "data operating system" for intelligence and high-stakes investigation. Independent analysis identifies its strengths as deep integration of heterogeneous data, analyst-centric workflows combining **graph + map + timeline**, and disciplined provenance and access control ([Golding Research](https://goldingresearch.substack.com/i/173524962/weaknesses-and-gaps)). Its Case Management module lets users manage, investigate and track cases without leaving the investigative platform, with data-entry forms and configurable report templates ([Palantir](http://www.palantir.com/solutions/case-management/)).

**DRISHTI vs Gotham:** graph ✅ (sigma + reactflow), map ✅ (deck.gl + maplibre), **timeline ❌** — `BoardTimeline.tsx` is 69 lines and `TimelinePage.tsx` is 77. The third leg of the analyst tripod is missing. Provenance discipline ✅ (arguably stronger than expected at this stage). Access control ❌ (decorative).

### 3.2 Axon Fusus (Real-Time Crime Center)

The RTCC pattern centres on a centralised video, data and sensor hub. Axon describes ingesting from CCTV, body-worn cameras, geolocation, ALPR, alert sources such as shot detection or alarms, and CAD ([Axon RTCC guide](https://www.axon.com/resources/real-time-crime-center)). Their published customer metric is striking as a design target: Peoria PD reports a **24.6-second virtual on-scene time** ([Axon](https://www.axon.com/resources/how-peoria-pd-built-an-award-winning-rtcc)).

**DRISHTI vs Fusus:** DRISHTI has no live sensor ingest and should not attempt video (see [What NOT to build](#17-what-not-to-build)). But the *operational tempo* concept — a live event feed, units, assignments, and time-to-awareness as a first-class metric — is directly portable and currently absent.

### 3.3 IBM i2 Analyst's Notebook

i2 provides connected network visualisation, **social network analysis**, and **geospatial and temporal views** to surface hidden connections ([IBM](https://www.ibm.com/id-en/products/i2-analysts-notebook)). Its data model is the POLE method — People, Objects, Locations, Events ([i2 Group](https://i2group.com/articles/what-is-link-analysis-and-link-visualization)). Version 9.3 added a **chart store** so charts can be stored, searched and shared to unlock intelligence held in individual analysts' charts ([IBM announcement](https://www.ibm.com/common/ssi/ShowDoc.wss?docURL=/common/ssi/rep_ca/5/899/ENUSLP21-0365/index.html)).

**DRISHTI vs i2:** SNA ✅ (Louvain + PageRank + betweenness in `graph/algorithms.py`). Chart store ✅ (`MyBoards.tsx` + board sharing/locking). Temporal analysis ❌. The ontology is effectively POLE-compatible already — `Case ↔ Person ↔ Phone ↔ Device ↔ Account ↔ Vehicle ↔ Place ↔ Event`.

### 3.4 ViCLAS / behavioural crime linkage

Computerised crime linkage systems determine whether a set of crimes was committed by the same offender ([Bennell et al.](http://eprints.lancs.ac.uk/53598/4/Bennell_et_al_ViCLAS_Final_Nov_21.pdf)). ViCLAS does this through structured collection and **binary encoding of behavioural (modus operandi), contextual and geographic-temporal data** ([overview](https://www.emergentmind.com/topics/violent-crime-linkage-analysis-system-viclas)). The statistical literature uses Bayes factors to express the strength of evidence that two crimes are linked, and stresses that the probability depends on both **similarity and distinctiveness** — a rare MO feature carries far more weight than a common one ([Researchgate](https://www.researchgate.net/publication/266748053_A_Statistical_Approach_to_Crime_Linkage), [Bayesian networks](https://www.researchgate.net/publication/271080746_Modelling_crime_linkage_with_Bayesian_networks)).

**DRISHTI vs ViCLAS:** `/cases/{id}/similar` does *narrative semantic* similarity via pgvector. That is not behavioural crime linkage: there is no structured MO encoding, no distinctiveness weighting, no series detection, no spatio-temporal linkage term. This is the biggest analytical gap and the highest-craft opportunity in the plan.

### 3.5 RISSafe / event deconfliction

Deconfliction identifies when law enforcement personnel are conducting events in close proximity at the same time ([BJA](https://bja.ojp.gov/sites/g/files/xyckuh186/files/media/document/event_deconfliction_call_to_action1-2.pdf)). RISSafe stores planned events — raids, controlled buys, surveillance — to identify and alert affected agencies of conflicts that could disrupt operations or, worse, cause officers to be unintentionally hurt ([DOJ](https://www.justice.gov/file/440496/dl?inline)). Critically, the architecture is a **pointer index**: on a match the system does not share case information, investigative detail or narrative — it simply alerts both agencies that a possible match exists ([Chicago HIDTA](https://www.chicago-hidta.org/deconfliction)).

**DRISHTI vs RISSafe:** completely absent, and it is close to free to build. DRISHTI already has entity resolution, a canonical graph and jurisdiction scoping — the three ingredients. The pointer-index design is also a *privacy-preserving* pattern, which fits DRISHTI's governance thesis perfectly. High impact, low effort, strong ethical story.

### 3.6 Indian statutory context — the differentiator nobody else will have

This is the most under-exploited opportunity in the entire project.

- **CCTNS** is live in all **17,798 police stations** nationally ([MHA, 2026](https://www.mha.gov.in/MHA1/Par2017/pdfs/par2026-pdfs/RS11032026/2154.pdf)). **ICJS** integrates Police (CCTNS), Courts (e-Courts), Jails (e-Prisons), Forensic Lab (e-Forensic) and Prosecution (e-Prosecution) ([MHA](https://www.mha.gov.in/en/commoncontent/inter-operable-criminal-justice-system-icjs)).
- **BNSS s.176(3)** transforms forensic investigation from a discretionary tool into a **procedural obligation** for offences punishable by seven years or more ([analysis](https://3fdef50c-add3-4615-a675-a91741bcb5c0.usrfiles.com/ugd/3fdef5_7ba4e649b4a1492084db8062fe6505d0.pdf)). Videography of the crime scene is mandatory for those offences ([TOI](https://timesofindia.indiatimes.com/city/delhi/body-cameras-the-key-to-simplifying-police-procedures-in-delhi/articleshow/111415070.cms)).
- **BNSS s.105** requires audio-video recording of search and seizure. The Allahabad High Court has already flagged police **non-compliance** with this mandate ([LiveLaw, Feb 2026](https://www.livelaw.in/high-court/allahabad-high-court/allahabad-high-court-police-non-compliance-section-105-bnss-videography-search-seizure-547230)).
- **BNSS s.193(8)** — the Supreme Court Observer records a case where a chargesheet was filed within 90 days but **without accompanying document copies**, and default bail was sought on that basis ([SCO](https://www.scobserver.in/supreme-court-observer-law-reports-scolr/eligibility-for-default-bail/)). Procedural incompleteness, not lateness, created the bail exposure.
- **BNSS s.536** provides the first statutory foundation for evidence via audio-visual electronic means, underpinning the **e-Sakshya** framework ([analysis](https://www.granthaalayahpublication.org/Arts-Journal/ShodhKosh/article/download/8559/7770/46199)).
- Karnataka is a credible venue: KSP states it has led on CCTNS, a dedicated cyber crime police station, an in-house police data centre and AFIS ([KSP](https://bangaloreurbanpolice.karnataka.gov.in/english)). The Karnataka High Court has directed the Police Computer Wing to build a **centralised state-level IT system for real-time monitoring** of police-station CCTV ([The Hindu, 2026](https://www.thehindu.com/news/national/karnataka/karnataka-high-court-orders-cctv-audit-at-all-police-stations-across-state/article71369726.ece)).

**DRISHTI vs statutory reality:** the corpus has `ActSectionAssociation` (172,374 rows), `ChargesheetDetails` (37,147), `ArrestSurrender` (72,762), `Seizure` (13,642), `CourtEvent` (64,391), `BailEvent` (27,196), lab results and `CaseDisposition`. **Every input needed to compute statutory compliance already exists and is doing nothing.** Not one line of code reasons about a deadline.

### 3.7 Predictive-policing evaluation rigour

The literature standardises on four evaluation metrics: **PAI** (prediction accuracy index), **RRI**, **PEI** and **PEI\*** ([Springer](https://link.springer.com/10.1057/s41284-023-00367-4)). There is a real, documented tension: smaller grid cells raise PAI (localised accuracy) but perform poorly on PEI\* and F1 because they cover fewer events; larger cells improve PEI\*/F1 at the cost of spatial specificity ([Springer, 2026](https://link.springer.com/article/10.1007/s12061-026-09888-y)). Ensemble models tend to be the most consistent performers across near-repeat, ML and RTM approaches ([Springer](https://link.springer.com/article/10.1007/s12061-020-09339-2)).

**DRISHTI vs the literature:** PAI and hit-rate exist (`forecast/validation.py`), and the multi-layer fusion design (`forecast/fusion.py`) matches the ensemble finding. Missing: **PEI\***, the grid-resolution sensitivity analysis, and — most importantly — any link from a prediction to whether a *tasking* based on it worked.

### 3.8 Consolidated gap matrix

| Capability | Gotham | Fusus | i2 | ViCLAS | RISSafe | DRISHTI now | Phase 2 |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Entity-resolved ontology | ● | ◐ | ● | ○ | ○ | ● | ● |
| Link / network analysis | ● | ○ | ● | ○ | ○ | ● | ● |
| Geospatial hotspots + forecast | ● | ● | ◐ | ○ | ○ | ● | ● |
| **Temporal fusion / chronology** | ● | ◐ | ● | ◐ | ○ | ○ | **●** |
| Collaborative analytical canvas | ● | ○ | ● | ○ | ○ | ● | ● |
| **Behavioural crime linkage / series** | ◐ | ○ | ◐ | ● | ○ | ○ | **●** |
| **Real-time operational picture** | ◐ | ● | ○ | ○ | ○ | ○ | **◐** |
| **Event / target deconfliction** | ◐ | ◐ | ○ | ○ | ● | ○ | **●** |
| **Statutory compliance clocks** | ○ | ○ | ○ | ○ | ○ | ○ | **●** |
| **Outcome feedback → model** | ◐ | ◐ | ○ | ○ | ○ | ○ | **●** |
| Enforced RBAC + purpose-of-access | ● | ● | ● | ● | ● | ○ | **●** |
| Provenance / audit | ● | ◐ | ● | ◐ | ● | ● | ● |
| Field mobility | ◐ | ● | ○ | ○ | ○ | ○ | **◐** |
| Multilingual (Kannada) | ○ | ○ | ○ | ○ | ○ | ◐ | **●** |

● full · ◐ partial · ○ absent

The three columns where DRISHTI can be **better than all of them** are statutory compliance, outcome feedback and Kannada-first operation. Those are not gaps in the reference platforms because those platforms were not built for an Indian state police force. That is the entire opportunity.

---

## 4. The three strategic pivots

Everything below reduces to three decisions.

### Pivot 1 — Stop being a viewer, become a system of action

Phase 1 answers "what happened and what might happen". It cannot answer "what did we do about it, and did it work". The `OutcomeObservation` table has 28,309 rows and nothing reads them for evaluation. Phase 2 wires **tasking → acknowledgement → outcome → measurement → re-ranking** as a first-class loop. This single change turns every recommendation in the product from an opinion into a testable claim.

### Pivot 2 — Become statutorily literate

A generic crime platform tells an SHO that a case is 76 days old. A statutorily literate platform tells them: *this case carries a section punishable by 10 years, the accused has been in custody since day 4, the chargesheet deadline under BNSS 193 is day 90, s.176(3) forensic examination is mandatory and no FSL record exists, and s.105 audio-video record of the seizure is missing — default bail exposure in 14 days.* The second one changes behaviour. The data for it is already in the database.

### Pivot 3 — Convert the honesty into the product

The fallback situation is currently a footnote in a README. Turn it into a visible governance feature: a live **Model Assurance** surface that reads `/predict/enablement` and states, per capability, which backend is serving, what it scored against which baseline, and whether it is approved for operational use. Then make the important ones real. A jury that sees a system openly refusing to promote a model that lost to a baseline will trust everything else it says.

---

## 5. Workstream 1 — Statutory Compliance & Case Clock Engine

**Priority: P0 · Effort: 12–15 engineer-days · The single highest-value item in this plan.**

### 5.1 Why this first

No competitor will have it, and no commercial platform has it, because BNS/BNSS/BSA compliance is India-specific and roughly two years old. Every input already exists in the corpus. And it speaks directly to the person who decides whether a system gets adopted: the supervisor who is personally accountable when a chargesheet slips and an accused walks out on default bail.

It also reframes DRISHTI's category. "Crime analytics dashboard" is a crowded space. "The system that keeps a state police force compliant with the new criminal codes" is not.

### 5.2 What it computes

**A. Statutory clocks per case.** Derived, never hand-entered:

| Obligation | Trigger | Deadline basis |
|---|---|---|
| Chargesheet filing (custody) | First arrest where accused remains in custody | 60 days for offences under 10 years; 90 days for offences ≥10 years / life / death |
| Investigation progress intimation to complainant | FIR registration | 90 days |
| Further-investigation completion | Supplementary investigation start | 90 days, court-extendable |
| Committal to sessions | Cognizance | 90 days, extendable to 180 |
| Statement / witness list completion | FIR registration | Station SOP window (configurable) |

Each obligation resolves to `due_date`, `days_remaining`, `state ∈ {ok, due_soon, at_risk, breached, satisfied, extended}`, plus the record that *would* satisfy it and the record that *did*.

**B. The forensic mandate (BNSS s.176(3)).** For every case, take `max(punishment_years)` across its `ActSectionAssociation` rows. If ≥ 7 and there is no linked `LabResult` or FSL referral, raise a `ComplianceGap` of kind `forensic_mandate_unmet`. This is a real, currently-invisible legal exposure, and it is one join away from data you already have.

**C. The videography mandate (BNSS s.105 / s.176(3)).** For every `Seizure` and crime-scene visit on a qualifying case, check for a linked evidence artifact with a video MIME type. Absent → `av_record_missing`. The Allahabad High Court has already flagged police non-compliance with exactly this mandate, so surfacing it pre-emptively is defensible and topical.

**D. Default-bail exposure.** The metric supervisors will open the app for. Per accused in custody: `days_in_custody`, `chargesheet_deadline`, `exposure_days`, escalating at T-21 / T-14 / T-7. Critically, include the s.193(8) **completeness** dimension, not just timeliness — a chargesheet filed without accompanying document copies has been litigated as grounds for default bail, so filed-but-incomplete must not clear the flag.

**E. Chargesheet quality gate.** Before a chargesheet is marked filed, run a checklist: every accused has arrest or absconder status; every section has supporting evidence links; statements recorded for all listed witnesses; FSL results attached where mandated; property and seizure records reconciled; s.193(8) document set complete. Output a readiness percentage and a blocking list.

### 5.3 Implementation

**Schema — `services/ml/sql/024_statutory_compliance.sql`** (following the existing numbered-migration convention):

```sql
-- Versioned statutory obligations, so a rule change is itself auditable.
CREATE TABLE "StatutoryRule" (
  "RuleID"            serial PRIMARY KEY,
  "Code"              text NOT NULL,               -- 'BNSS_193_CHARGESHEET_90'
  "Statute"           text NOT NULL,               -- 'BNSS'
  "SectionRef"        text NOT NULL,               -- '193(1)'
  "ObligationKind"    text NOT NULL,               -- deadline | artifact | procedure
  "TriggerEvent"      text NOT NULL,               -- fir_registered | first_arrest | cognizance
  "DurationDays"      integer,                     -- NULL for artifact obligations
  "AppliesWhen"       jsonb NOT NULL DEFAULT '{}', -- {"min_punishment_years": 7}
  "SatisfiedBy"       jsonb NOT NULL DEFAULT '{}', -- {"table": "ChargesheetDetails"}
  "Severity"          text NOT NULL,               -- advisory | material | critical
  "EffectiveFrom"     date NOT NULL,
  "EffectiveTo"       date,
  "Citation"          text NOT NULL,
  "CreatedAt"         timestamptz NOT NULL DEFAULT now()
);

-- One row per (case, rule, accused). Recomputed idempotently.
CREATE TABLE "CaseObligation" (
  "ObligationID"      bigserial PRIMARY KEY,
  "CaseMasterID"      integer NOT NULL REFERENCES "CaseMaster"("CaseMasterID"),
  "RuleID"            integer NOT NULL REFERENCES "StatutoryRule"("RuleID"),
  "AccusedMasterID"   integer,                     -- custody-scoped obligations
  "TriggerAt"         timestamptz NOT NULL,
  "DueAt"             timestamptz,
  "State"             text NOT NULL,               -- ok|due_soon|at_risk|breached|satisfied|extended
  "SatisfiedAt"       timestamptz,
  "SatisfiedByRef"    text,                        -- 'ChargesheetDetails:37021'
  "ExtensionRef"      text,                        -- court order reference
  "ComputedAt"        timestamptz NOT NULL DEFAULT now(),
  "ComputeVersion"    text NOT NULL,               -- rule-engine version, for reproducibility
  UNIQUE ("CaseMasterID", "RuleID", "AccusedMasterID")
);

CREATE TABLE "ComplianceGap" (
  "GapID"             bigserial PRIMARY KEY,
  "CaseMasterID"      integer NOT NULL REFERENCES "CaseMaster"("CaseMasterID"),
  "GapKind"           text NOT NULL,               -- forensic_mandate_unmet|av_record_missing|...
  "RuleID"            integer REFERENCES "StatutoryRule"("RuleID"),
  "Detail"            jsonb NOT NULL DEFAULT '{}',
  "Severity"          text NOT NULL,
  "DetectedAt"        timestamptz NOT NULL DEFAULT now(),
  "ResolvedAt"        timestamptz,
  "ResolvedByRef"     text,
  "DisputedBy"        text,                        -- an officer may contest a false positive
  "DisputeRationale"  text
);

CREATE INDEX ON "CaseObligation" ("State", "DueAt");
CREATE INDEX ON "CaseObligation" ("CaseMasterID");
CREATE INDEX ON "ComplianceGap" ("GapKind") WHERE "ResolvedAt" IS NULL;

CREATE MATERIALIZED VIEW mv_compliance_by_unit AS
  SELECT u."UnitID", u."DistrictID",
         COUNT(*) FILTER (WHERE co."State" = 'at_risk')  AS at_risk,
         COUNT(*) FILTER (WHERE co."State" = 'breached') AS breached,
         COUNT(*) FILTER (WHERE co."State" = 'due_soon') AS due_soon
  FROM "CaseObligation" co
  JOIN "CaseMaster" cm ON cm."CaseMasterID" = co."CaseMasterID"
  JOIN "Unit" u        ON u."UnitID" = cm."PoliceStationID"
  GROUP BY u."UnitID", u."DistrictID";
```

**Service — `services/ml/app/compliance/`:**

```
compliance/
  __init__.py
  rules.py      # rule catalogue + AppliesWhen predicate evaluation
  engine.py     # compute_for_case(conn, case_id) -> [Obligation]; recompute_batch()
  gaps.py       # forensic_mandate, av_record, chargesheet_completeness detectors
  service.py    # scoped reads (uses org/scope.enforce_geo_request)
  schemas.py
  router.py
```

Design constraints, consistent with the existing codebase:

- **Deterministic and reproducible.** No model anywhere in this workstream. Every obligation records `ComputeVersion` and cites `StatutoryRule.Citation`. A supervisor can always ask "why day 90" and get a section reference.
- **Punishment-years lookup.** Add `PunishmentYears` to the acts/sections reference (or a side table if that reference is treated as immutable) and seed it for the BNS sections present in the corpus. This is the one genuine data-authoring task here — budget 2 days and cite a source per value.
- **Advisory, never blocking.** A gap raises a flag and an escalation; it never prevents an officer from acting, and it is always disputable, hence `DisputedBy` / `DisputeRationale`. This matters: a compliance engine that cannot be contested becomes a tool for punishing officers rather than helping them.
- **Audited.** Every recompute writes an audit row. Add `COMPLIANCE_RECOMPUTE` to the action vocabulary at `audit.py:33-50`.

**Endpoints — `/compliance/*`:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/compliance/rules` | Versioned rule catalogue with citations |
| GET | `/compliance/case/{case_id}` | Obligations + gaps for one case, with satisfying records |
| GET | `/compliance/queue` | Scoped work queue: `?state=at_risk&unit_id=&district_id=&kind=` |
| GET | `/compliance/default-bail-exposure` | Accused in custody ranked by exposure days |
| GET | `/compliance/summary` | Rollup by unit/district for command views |
| POST | `/compliance/recompute` | Idempotent recompute for a case or scope (guarded write) |
| POST | `/compliance/gaps/{gap_id}/dispute` | Officer contests a detection, with rationale |
| POST | `/compliance/gaps/{gap_id}/resolve` | Mark satisfied, linking the satisfying record |
| GET | `/compliance/chargesheet-readiness/{case_id}` | Pre-filing checklist + blocking list |

**Batch and cron.** Extend `app/batch.py` with `compliance-recompute` (nightly sweep) and add `POST /internal/compliance/recompute` as a Catalyst Cron target, mirroring the existing `cron_forecast` pattern at `internal/router.py:72`. Catalyst Job Scheduling supports intervals as short as one minute with both pre-defined and dynamic crons, which is more than sufficient.

**Frontend:**

| Surface | File | What it shows |
|---|---|---|
| New destination `/compliance` | `routes/compliance/ComplianceWorkspace.tsx` + 4 modes | Clocks · Gaps · Default-bail exposure · Chargesheet readiness |
| Case File subpage | `routes/cases/subpages/CompliancePage.tsx` | Per-case obligation timeline with statutory citations |
| Case File header strip | modify `routes/cases/CaseFile.tsx` | Persistent clock chip: `Day 76 / 90 · at risk` |
| Command Center widget | `routes/home/widgets/StatutoryClocksWidget.tsx` | Scoped at-risk / breached counts with drill-through |
| Escalations | extend `notifications/service.py` | T-21 / T-14 / T-7 default-bail notifications |

The header chip is the detail that sells this. A compliance clock visible on every case view, always, is what makes it feel like infrastructure rather than a report.

### 5.4 Demo moment

Open case 100239. A red chip reads `Day 76 / 90 — default bail exposure in 14 days`. Click it: three obligations — one satisfied (progress intimation, day 88), one at risk (chargesheet, BNSS 193, cited), one breached (s.176(3) forensic examination: offence carries 10 years, no FSL record exists). Then open `/compliance/queue` scoped to the district: 41 cases at risk, ranked, with responsible IO and station. That is a screen a real SP would ask for by name.

---

## 6. Workstream 2 — Crime Linkage & Serial Offender Engine

**Priority: P0 · Effort: 10–13 engineer-days**

### 6.1 The gap

`/cases/{id}/similar` embeds the case narrative and runs pgvector cosine ANN. That finds cases *described* similarly. Behavioural crime linkage asks a different question: were these committed by the same offender? The research literature is explicit that this depends on similarity weighted by **distinctiveness** — two burglaries both entered "through a door" is worthless; two both entered by "removing a window grille with a pipe wrench between 02:00 and 04:00" is a strong signal. Nothing in the current build models distinctiveness.

### 6.2 Design

**A. Structured MO encoding.** A facet vector per case, extracted from `CrimeHead` / `CrimeSubHead`, narrative and property records:

| Facet group | Example values |
|---|---|
| Entry method | grille removal, lock picking, key duplication, wall breach, no forced entry |
| Target type | ground-floor flat, locked shop, two-wheeler on street, ATM, temple |
| Tool / instrument | pipe wrench, gas cutter, duplicate key, screwdriver, none |
| Time band | 6 × 4-hour buckets |
| Day type | weekday / weekend / festival (the corpus has calendar context) |
| Approach | distraction, impersonation, surveillance-then-strike, opportunistic |
| Property class | gold, two-wheeler, cash, electronics, livestock, documents |
| Victim profile | lone elderly, woman alone, shopkeeper, commuter, tourist |
| Escape | two-wheeler, on foot, vehicle, public transport |
| Signature | anything distinctive — note left, specific damage, verbal phrase |

Store as `CaseMoProfile` with a `jsonb` facet map plus an array encoding for fast comparison. Populate via a batch extractor: deterministic rules over structured fields first, narrative pattern-matching second, and where a semantic model is available, LLM-assisted facet extraction whose output is written as **reviewable data, never consumed unreviewed**. Store per-facet extraction confidence.

**B. Distinctiveness-weighted linkage score.** For a candidate pair `(a, b)`:

```
behavioural = Σ_f  w_f · match(a_f, b_f)      where w_f = log(N / df_f)   # IDF over the corpus
spatial     = exp(-d(a, b) / λ_s)              # λ_s ≈ 800 m, tunable
temporal    = exp(-|t_a - t_b| / λ_t)          # λ_t ≈ 21 days
diurnal     = circular_similarity(hour_a, hour_b)
narrative   = pgvector cosine                  # reuse CrimeEmbedding, do not discard it

score = σ( β₀ + β₁·behavioural + β₂·spatial + β₃·temporal + β₄·diurnal + β₅·narrative )
```

Report the result **as a likelihood ratio, not a probability of guilt**, always alongside per-facet contributions. Calibrate `β` on the subset of the corpus where cases share a confirmed accused — that is your ground truth and it exists in quantity: 164,861 `Accused` rows across 100,003 cases yields ample co-offender-linked pairs.

**C. Series detection.** Build a candidate-pair graph thresholded at the calibrated operating point, run connected components then Louvain refinement (`graph/algorithms.py` already has Louvain), and emit `CaseSeries` candidates. Each carries member cases, confidence, driver facets, spatial envelope, temporal span, and a plain-language driver statement: *"7 cases, driver: identical grille-removal entry + 02:00–04:00 window + 600 m radius, over 34 days."*

Series are a **review queue, not a conclusion**. An analyst confirms, splits, merges or rejects — and that confirmation is exactly what feeds calibration, which connects this workstream to Workstream 3.

**D. Suspect prioritisation — handle with care.** For an unsolved case, rank known offenders whose *historical* MO profile matches and whose availability window (not in custody) is consistent. Hard guardrails, non-negotiable:

- Output is an **investigative lead list**, explicitly captioned as not constituting suspicion, probable cause, or grounds for any coercive action.
- Every entry shows the specific prior cases and facets driving the match, reachable in one click.
- **No score is ever stored as an attribute of a person.** This is a query result, not a person attribute — which is precisely how it stays consistent with the "no person re-scoring" commitment.
- Mandatory rationale capture when an officer acts on a lead, feeding Workstream 3.
- Protected-characteristic features excluded by construction, with the exclusion asserted in a test.

### 6.3 Implementation

**Schema — `025_crime_linkage.sql`:** `CaseMoProfile`, `CaseLinkCandidate` (pair, score, component breakdown jsonb, model version, review state), `CaseSeries`, `CaseSeriesMember`, `SeriesReview`.

**Service — `services/ml/app/linkage/`:** `facets.py` (taxonomy + extractor), `scoring.py` (IDF weights, kernels, calibration), `series.py` (clustering + driver statements), `suspects.py` (prioritisation with guardrails), `service.py`, `router.py`.

**Endpoints:** `GET /linkage/case/{id}/links` · `GET /linkage/series` · `GET /linkage/series/{id}` · `POST /linkage/series/{id}/review` · `GET /linkage/case/{id}/mo-profile` · `POST /linkage/case/{id}/mo-profile` (analyst correction) · `GET /linkage/case/{id}/suspect-leads` · `POST /linkage/detect` · `GET /linkage/calibration`.

**Batch:** `linkage-extract` (MO facets), `linkage-detect` (pairs + series), `linkage-calibrate`.

**Frontend:**
- New `/network?mode=linkage` mode, fitting the existing mode-router pattern at `NetworkAnalysis.tsx:17-23`.
- New `/linkage/series` review-queue workspace.
- Upgrade `routes/cases/subpages/SimilarPage.tsx` (currently 107 lines) into two tabs: *Semantic similarity* (existing) and *Behavioural linkage* (new, with facet contribution breakdown).
- **Series map + timeline overlay** — plot a series spatially and temporally at once. This is the visual that makes the feature land.
- Send-to-Board integration: pin an entire series with member cases and driver facets.

### 6.4 Demo moment

Open the series queue. `S-2026-041` — seven two-wheeler thefts, confidence 0.81. The driver panel: identical ignition-bypass method (IDF weight 4.2, present in 0.7% of the corpus), all between 02:00 and 04:00, all within 600 m of Rajajinagar market, spanning 34 days. Toggle the map overlay: seven pins and a time slider. Open suspect leads: three known offenders with matching historical MO, each showing the prior cases that justify the match, under a banner stating this is a lead list and not grounds for action. Pin the series to a board, hand it to the IO.

---

## 7. Workstream 3 — Closed-Loop Tasking & Outcome Feedback

**Priority: P0 · Effort: 9–12 engineer-days · The biggest conceptual upgrade in the plan.**

### 7.1 The gap

DRISHTI produces recommendations — patrol plans, leads, hotspot forecasts, entity merges, series candidates — and nothing comes back. There is no record of whether a recommendation was accepted, no record of what happened next, and therefore no way to know whether any of it works. `OutcomeObservation` holds 28,309 rows that no evaluation path reads.

Every reference platform treats this as table stakes and most implement it shallowly. Doing it properly is a real differentiator, and it is the natural completion of DRISHTI's own thesis: a platform that insists every model expose its provenance should also insist every recommendation expose its result.

### 7.2 The loop

```
Recommendation → Tasking → Acknowledgement → Execution → Outcome → Measurement → Re-ranking
   (model)        (human      (officer,        (field)    (observed,  (PAI / precision  (weights,
                   decides +    time-stamped)              attributed) / hit rate)       thresholds)
                   rationale)
```

Four recommendation classes on one shared spine:

| Class | Recommendation | Tasking | Outcome signal | Metric |
|---|---|---|---|---|
| **Spatial** | Hotspot / near-repeat forecast cell | Patrol beat assignment for a window | Incidents in cell during window + 7 days after | PAI, PEI\*, hit rate, dosage–response |
| **Investigative** | Case lead (`/cases/{id}/leads`) | Assigned to IO with due date | Productive / unproductive / inconclusive, plus what it produced | Lead precision @ k, time-to-productive-lead |
| **Identity** | Entity-resolution candidate | Review queue item | Merged / rejected, and later reversed | Merge precision, reversal rate |
| **Analytical** | Series candidate, hidden association | Analyst review | Confirmed / split / rejected | Series precision, analyst agreement rate |

### 7.3 Implementation

**Schema — `026_tasking_outcomes.sql`:**

```sql
CREATE TABLE "Recommendation" (
  "RecommendationID"  bigserial PRIMARY KEY,
  "Kind"              text NOT NULL,        -- patrol_cell|case_lead|entity_merge|case_series
  "SourceModelVersionID" integer REFERENCES "ModelVersion"("ModelVersionID"),
  "SubjectRef"         text NOT NULL,       -- 'GridCell:8412' | 'CaseMaster:100239'
  "Payload"            jsonb NOT NULL,      -- the recommendation as issued (immutable)
  "Score"              numeric,
  "Confidence"         numeric,
  "FeatureSnapshotID"  integer,             -- reuse existing snapshot immutability
  "IssuedAt"           timestamptz NOT NULL DEFAULT now(),
  "ValidUntil"         timestamptz
);

CREATE TABLE "TaskingDecision" (
  "DecisionID"        bigserial PRIMARY KEY,
  "RecommendationID"  bigint NOT NULL REFERENCES "Recommendation"("RecommendationID"),
  "Decision"          text NOT NULL,        -- accepted|modified|rejected|deferred
  "DecidedBy"         text NOT NULL,        -- server-derived actor, never client-supplied
  "DecidedAt"         timestamptz NOT NULL DEFAULT now(),
  "Rationale"         text NOT NULL,        -- mandatory; this is the training signal
  "ModifiedPayload"   jsonb,                -- what the human changed it to
  "ScopeUnitID"       integer,
  "ScopeDistrictID"   integer
);

CREATE TABLE "TaskAssignment" (
  "AssignmentID"      bigserial PRIMARY KEY,
  "DecisionID"        bigint NOT NULL REFERENCES "TaskingDecision"("DecisionID"),
  "AssignedTo"        text NOT NULL,
  "WindowStart"       timestamptz NOT NULL,
  "WindowEnd"         timestamptz NOT NULL,
  "State"             text NOT NULL,        -- assigned|acknowledged|in_progress|completed|lapsed
  "AcknowledgedAt"    timestamptz,
  "CompletedAt"       timestamptz
);

CREATE TABLE "TaskOutcome" (
  "OutcomeID"         bigserial PRIMARY KEY,
  "AssignmentID"      bigint NOT NULL REFERENCES "TaskAssignment"("AssignmentID"),
  "OutcomeClass"      text NOT NULL,        -- productive|unproductive|inconclusive|not_executed
  "ObservedAt"        timestamptz NOT NULL DEFAULT now(),
  "ObservedBy"        text NOT NULL,
  "EvidenceRefs"      jsonb NOT NULL DEFAULT '[]',  -- arrests/recoveries/cases produced
  "Narrative"         text,
  "AutoDerived"       boolean NOT NULL DEFAULT false -- true when computed from incident data
);

CREATE TABLE "RecommendationScorecard" (
  "ScorecardID"       bigserial PRIMARY KEY,
  "Kind"              text NOT NULL,
  "ModelVersionID"    integer REFERENCES "ModelVersion"("ModelVersionID"),
  "PeriodStart"       date NOT NULL,
  "PeriodEnd"         date NOT NULL,
  "Metrics"           jsonb NOT NULL,       -- {"pai":3.1,"pei_star":0.42,"hit_rate":0.28,"n":412}
  "AcceptanceRate"    numeric,
  "ComputedAt"        timestamptz NOT NULL DEFAULT now()
);
```

Three properties worth calling out:

1. **`Rationale` is mandatory on every decision.** Free-text rationale on accept/modify/reject is the highest-value training signal in the entire system and costs one text column. It is also the accountability record.
2. **`Recommendation.Payload` is immutable.** The recommendation as issued is preserved even when the human modifies it, so you can measure human-vs-model divergence rather than losing it.
3. **Outcomes can be auto-derived.** For spatial taskings, `AutoDerived = true` outcomes are computed nightly by counting incidents in the tasked cell during and after the window. No officer data entry needed for the metric that matters most.

**Service — `services/ml/app/tasking/`:** `recommend.py` (registry of recommendation producers), `decisions.py`, `assignments.py`, `outcomes.py` (incl. the auto-derivation sweep), `scorecard.py` (PAI, PEI\*, hit rate, precision @ k, acceptance rate, dosage–response), `router.py`.

**Endpoints:** `GET /tasking/recommendations` · `POST /tasking/{rec_id}/decide` · `GET /tasking/assignments` · `POST /tasking/assignments/{id}/acknowledge` · `POST /tasking/assignments/{id}/outcome` · `GET /tasking/scorecard` · `GET /tasking/scorecard/{kind}/history` · `POST /tasking/outcomes/derive` (batch/cron).

**Wiring into existing surfaces:**

- `MapHotspots.tsx` patrol-planning mode gains a real **Accept / Modify / Reject** control with a rationale dialog. Today the patrol plan is display-only.
- `MapHotspots.tsx:121` — fix the fake alert acknowledgement. The `ackIds` React `Set` becomes a real `POST`, which is a natural fit for this spine.
- `LeadsPage.tsx` gains assignment and outcome capture.
- `EntityResolution.tsx` merge/reject decisions already exist — route them through `TaskingDecision` so precision and reversal rate become measurable.
- New `/analytics?mode=scorecard` — the **Recommendation Scorecard**: per model, per period, acceptance rate, PAI, PEI\*, hit rate, precision @ k, and the dosage–response curve.

**Metrics, done properly.** Implement PAI, hit rate (both already partially present in `forecast/validation.py`) *plus* **PEI\***, which is currently missing. The literature is clear that PAI and PEI\* trade off against grid resolution — smaller cells raise PAI but hurt PEI\* and F1 because they capture fewer events. So also ship a **grid-resolution sensitivity panel** showing the metric surface across cell sizes. That single chart demonstrates more forecasting maturity than any accuracy number.

### 7.4 Demo moment

Open `/analytics?mode=scorecard`. A table: *near-repeat layer, last 90 days, 412 taskings issued, 71% accepted, 12% modified, 17% rejected. PAI 3.14, PEI\* 0.42, hit rate 28%.* Below it, the grid-resolution sensitivity curve showing PAI rising and PEI\* falling as cells shrink, with the chosen operating point marked. Beside it, the top five rejection rationales in officers' own words — *"beat already saturated"*, *"festival deployment conflict"* — which is precisely the feedback that improves the next model.

Then the closing line: **no other submission in this competition can tell you whether its predictions actually worked.**

---

## 8. Workstream 4 — Real-Time Operations & Deconfliction

**Priority: P1 · Effort: 8–11 engineer-days**

### 8.1 Two separable pieces

**Piece A — a genuine real-time transport.** Today there is none: zero WebSocket, zero EventSource in `web/src`. Board collaboration polls every 4 s (`useBoard.ts:87-130`), presence every 5 s, alerts every 120 s. The SSE channel at `stream/router.py:122` exists but is flag-gated off and single-instance only, with in-process fan-out at `:77-80` and no cross-instance broker.

Fixes, in order of value:

1. **Turn on the SSE channel** (`DRISHTI_STREAM_CHANNEL_ENABLED`) and extend it beyond predictions to a general scoped event bus: new FIR committed, alert raised, board activity, tasking assigned, compliance breach, deconfliction hit.
2. **Add a cross-instance broker.** Two options given the deployment: Catalyst Cache as a lightweight pub/sub with a short-TTL fan-out segment, or a Data Store event table polled by each instance with a cursor. Neither is elegant; both are honest and both work behind one AppSail. Document the choice and its limits rather than claiming distributed real time.
3. **Keep polling as the correctness path.** The existing reconnect-with-`after_id` replay design in `useBoard.ts` is genuinely good. SSE becomes the low-latency path; polling remains the guarantee. Do not remove it.
4. **Frontend transport abstraction:** `web/src/realtime/` with `useRealtimeChannel(topic)` that prefers SSE and silently degrades to the existing poll. One hook, so every consumer gets both paths for free.

**Piece B — the Live Operations picture.** Build on `livefeed/router.py`, which already has an idempotent committed-FIR projection and freshness tracking. Add a `/ops` destination: a live incident feed with time-to-awareness per event, active taskings and their state, unit availability, open compliance breaches, and a *virtual on-scene time* style metric. Axon publishes customer figures like a 24.6-second virtual on-scene time; having an equivalent instrumented metric — even on synthetic data — shows you understand what operational tempo means.

### 8.2 Piece C — Deconfliction (the standout)

This is the highest ratio of impact to effort in the entire plan, and it is the feature most likely to make an evaluator sit up, because it is a genuine officer-safety capability that no student project ships.

**The problem it solves.** Two officers unknowingly investigating the same person, phone or location. In the mildest case they duplicate work and tip off a suspect. In the worst case, per the BJA and DOJ material, investigative efforts get disrupted or officers are unintentionally hurt.

**The architecture that makes it safe: a pointer index.** On a match the system must **not** disclose case details, investigative narrative or evidence. It discloses only that an overlap exists and who to contact. This is how RISSafe works, and it is a perfect fit for DRISHTI's governance thesis — it is a *privacy-preserving* information-sharing primitive, not a surveillance expansion.

**Three deconfliction types:**

| Type | Trigger | Match condition |
|---|---|---|
| **Subject** | New case party, new board pin, new entity link | Same canonical person / phone / vehicle / account active in another open investigation |
| **Location + time** | Planned operation registered, or FIR committed | Overlapping geofence and time window with another registered operation |
| **Target** | Analyst runs a network expansion on an entity | Another unit has that entity flagged as a subject of interest |

DRISHTI already has all three ingredients: canonical entity resolution (`identity/service.py`), the governed graph (`EntityGraph`, 206,026 rows), and jurisdiction scoping (`org/scope.py`).

**Schema — `027_deconfliction.sql`:**

```sql
CREATE TABLE "OperationRegistration" (
  "OperationID"     bigserial PRIMARY KEY,
  "OperationKind"   text NOT NULL,      -- raid|surveillance|controlled_buy|search|cordon
  "RegisteredBy"    text NOT NULL,
  "UnitID"          integer NOT NULL,
  "Geofence"        geography(Polygon, 4326),
  "WindowStart"     timestamptz NOT NULL,
  "WindowEnd"       timestamptz NOT NULL,
  "SubjectRefs"     jsonb NOT NULL DEFAULT '[]',  -- canonical entity ids only
  "Sensitivity"     text NOT NULL,      -- routine|sensitive|restricted
  "CreatedAt"       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE "DeconflictionHit" (
  "HitID"           bigserial PRIMARY KEY,
  "HitKind"         text NOT NULL,      -- subject|location_time|target
  "LeftRef"         text NOT NULL,      -- 'OperationRegistration:14' | 'CaseMaster:100239'
  "RightRef"        text NOT NULL,
  "LeftUnitID"      integer NOT NULL,
  "RightUnitID"     integer NOT NULL,
  "MatchBasis"      jsonb NOT NULL,     -- {"canonical_person_id": 88213} — the pointer, no detail
  "Confidence"      numeric NOT NULL,
  "DetectedAt"      timestamptz NOT NULL DEFAULT now(),
  "NotifiedAt"      timestamptz,
  "State"           text NOT NULL,      -- open|contacted|resolved|false_positive
  "ResolutionNote"  text
);

CREATE INDEX ON "OperationRegistration" USING GIST ("Geofence");
CREATE INDEX ON "OperationRegistration" ("WindowStart", "WindowEnd");
CREATE INDEX ON "DeconflictionHit" ("State") WHERE "State" = 'open';
```

PostGIS is already a required extension (`main.py:58`), so the geofence overlap query is a `ST_Intersects` plus a `tstzrange &&` overlap — cheap and index-backed.

**Service — `services/ml/app/deconfliction/`:** `detect.py` (three matchers), `notify.py` (routes to both units' supervisors via the existing notifications service), `service.py`, `router.py`.

**Endpoints:** `POST /deconfliction/operations` (register) · `GET /deconfliction/operations` · `POST /deconfliction/check` (pre-flight, before committing an operation) · `GET /deconfliction/hits` · `POST /deconfliction/hits/{id}/resolve`.

**The critical implementation rule.** The hit response must be constructed so that it *cannot* leak detail even by accident. Return only: hit kind, match basis (a canonical id), the other unit's name, the contact officer's designation and a case-reference token. Never join to `CaseMaster` narrative, party names or evidence in this code path. Add a test asserting the response schema contains no narrative or PII field. This is exactly the kind of constraint that reads as professional judgement.

**Frontend:** a `/deconfliction` panel under the operations destination; a pre-flight check step in the operation registration form; an unmissable banner on the Case File and Investigation Board when an open subject hit exists on that case; officer-safety flags surfaced on live events.

### 8.3 Demo moment

The Cyber Cell analyst expands a phone number on the network graph. A banner appears: *"Deconfliction: this subject is active in an open investigation at Rajajinagar PS. Contact Dy.SP Kavya Hegde. No case detail is disclosed by this notice."* Two officers who would never have known about each other now do. Then show the audit row proving what was disclosed — nothing but the pointer.

---

## 9. Workstream 5 — Make the AI Genuinely Real

**Priority: P0 (parts) · Effort: 12–16 engineer-days**

The pitch is "decision intelligence". Four of the marquee models currently resolve to fallbacks. This workstream is about closing that honestly, and where it cannot be closed, converting the disclosure into a feature.

### 9.1 The cheapest big win: real embeddings, permanently

`cases/embeddings.py:122-136` prefers `SentenceTransformerEmbedder` (paraphrase-multilingual-mpnet-base-v2, 768-dim, English + Kannada) and falls back to `HashingEmbedder`. The AppSail image deliberately excludes the model weights (`requirements.appsail.txt`), so the deployed service uses hashing.

**But the embedder only needs to run once.** Embeddings are a batch artifact stored in pgvector, not a serving dependency. Run `python -m app.batch embed-cases` with real sentence-transformers on a GPU box (or any machine with the weights) over all 100,003 cases, write them to `CrimeEmbedding`, and the deployed service performs **genuine multilingual semantic ANN search forever** — because `cases/similar.py:139-140` embeds the query with `embedder_for_model_name()`, matching whatever model produced the corpus.

The one catch: query-time embedding also needs the model. Two options — (a) embed queries via a small QuickML-hosted embedding endpoint, or (b) for case-to-case similarity, which is the dominant use, look up the stored corpus vector for the query case rather than re-embedding, requiring no model at serving time at all. Option (b) is free and covers `/cases/{id}/similar` completely.

**Effort: 2 days. Impact: converts a headline capability from hashed bag-of-words to real multilingual semantics.** This is the best value in the whole plan.

### 9.2 Ask DRISHTI v2 — from single-query to agentic

Today: one question → one SQL → one answer. `nlsql/planner.py` selects `FallbackPlanner`, a regex intent matcher, because `semantic_planner_provider = ""`.

Two upgrades:

**(a) Make the semantic planner primary.** Deploy a QuickML LLM Serving endpoint, set `semantic_planner_provider = "catalyst_quickml"`, and configure `quickml_llm_endpoint` / `quickml_llm_model`. The client already exists at `planner.py:352-386` and speaks OpenAI-compatible `/chat/completions` with `response_format=json_object`. This is configuration and deployment work, not new code — the hard part was already built.

**(b) Multi-step tool-calling over the existing API.** This is the real 5x. DRISHTI has ~330 endpoints; they are already a tool registry. Build `nlsql/agent.py`:

```
question → decompose into sub-questions
         → select tools from a typed, role-filtered registry
         → execute (each tool independently scope-guarded)
         → synthesise a grounded answer from actual tool outputs
         → cite every contributing record and tool call
```

This lets DRISHTI answer questions it structurally cannot answer today:

- *"Which stations in Bengaluru South have chargesheet deadlines at risk this month, and how does their disposal rate compare to last quarter?"* → compliance queue + workload + trends, three tools, one answer.
- *"Show me the money trail for the accused in case 100239 and whether any of those accounts appear in other open cases."* → case detail + money trace + deconfliction pointer.
- *"Is series S-2026-041 still active, and what did the last patrol tasking there achieve?"* → linkage + tasking scorecard.

**Non-negotiable safety carry-overs.** Everything that makes the current engine safe must survive:

- Every tool call passes through the existing scope guard. `nlsql/scope.py:enforce_scope()` runs on any generated SQL, after the model, independently of it.
- The read-only path (`ro_conn()` + `SET ROLE drishti_readonly`) remains the only execution route for generated SQL.
- No tool may perform a write. The registry is read-only by construction, asserted in a test.
- Answers remain grounded in returned rows — extend `_grounded_reply` rather than letting the model narrate freely.
- Citations extend to tool calls: every answer lists which endpoints ran with what parameters. This is strictly better provenance than today.
- Keep `planner_source` / `planner_degraded` labelling and extend it to per-tool degradation.

**(c) A published evaluation harness.** Build `services/ml/eval/nlsql_golden.jsonl` with ~150 question/expected-answer pairs spanning English, Kannada script, transliterated Kannada, all ten roles, aggregate-only role restrictions, out-of-scope refusals and deliberately ambiguous questions that *should* trigger clarification. Score exact-match, semantic-match, refusal correctness and scope-violation rate. Publish the numbers.

Being able to say *"our NL interface scores 0.87 on a published 150-question benchmark, including 100% correct refusal on 22 out-of-scope probes"* is worth more than any architecture diagram.

### 9.3 Forecasting: commit to one honest position

Currently `get_forecaster()` (`forecast/timesfm.py:220-229`) resolves to `SeasonalForecaster` unless `DRISHTI_TIMESFM_SAGEMAKER=true` or `timesfm` imports locally. The measured backtest — the one in the README — ran the seasonal forecaster, and the README says so.

Pick one and be unambiguous:

- **Option A (recommended):** run the real TimesFM 2.5 path via SageMaker for a bounded acceptance run, record its own backtest with its own model version on the identical rolling-origin split, and publish both rows side by side. The `SageMakerTimesFMForecaster` and its fail-closed device check already exist. Cost is a few GPU-hours.
- **Option B:** accept the seasonal forecaster as the serving model, rename it so nothing implies a foundation model, and lean on the fact that it already beats seasonal naive by 17.8% MAE and moving-average by 7.1%. That is a legitimate result.

What must not happen is a third phase in which the ambiguity persists. Also worth noting from the existing benchmark: the seasonal forecaster has **0.6094 coverage on an 80% interval** while moving-average achieves 0.8333. The intervals are overconfident. Fix the quantile calibration — well-calibrated uncertainty matters more for a decision-support tool than a marginal MAE gain, and an evaluator who reads the table will notice.

### 9.4 Kannada as a first-class language

Currently: font fallbacks (`tailwind.config.js:113-118`), 19-line script detection (`lib/lang.ts`), Kannada cue sets in the fallback planner, and a `translate` endpoint that honestly returns `available=false` when unconfigured. The UI chrome is entirely English. `zia_voice.py` raises `NotImplementedError` for transcribe/synthesize/translate.

For a Karnataka police platform this is the most obvious credibility gap after RBAC.

- **UI localisation:** add a lightweight i18n layer (`react-i18next` or a hand-rolled dictionary — the app has no form or i18n library today) and translate the shell, navigation, all ten role labels, case-file field labels and error states. Full Kannada UI toggle.
- **Kannada NL queries end to end:** already partly there via the planner cue sets; validate with the golden set above and report Kannada accuracy separately.
- **Translation:** IndicTrans2 from AI4Bharat is open-source, transformer-based, and covers all 22 scheduled languages including Kannada. Host a small endpoint or wire it through QuickML, replacing the `NotImplementedError`.
- **Voice:** IndicWhisper (Whisper fine-tuned on ~10.7k hours across 12 Indian languages) has the lowest WER on 39 of 59 Vistaar benchmarks. Browser Web Speech API handles Kannada poorly; a hosted IndicWhisper endpoint would let the existing voice-confidence gate (`voice_low_confidence_threshold`, already implemented with a `VoiceTranscript` table) work on real Kannada dictation.

An SHO dictating a question in Kannada and getting a cited answer in Kannada is a demo moment nothing else in the field will match.

### 9.5 Turn the honesty into a feature: the Model Assurance surface

`predict/enablement.py`, `predict/placement.py` and `predict/capability_gaps.py` already model exactly this. Surface it as a first-class screen at `/governance?mode=assurance`:

| Capability | Serving backend | Benchmark | vs baseline | Status |
|---|---|---|---|---|
| District trajectory forecast | `drishti-timesfm-seasonal` | MAE 6.327 | +17.8% vs seasonal naive | Approved, decision support |
| Workload band | in-context kNN | Acc 0.4141 | **loses** to prior-period 0.6484 | **Not promoted** |
| Similar case | sentence-transformers 768d | recall@10 pending | — | Approved |
| NL→SQL planner | QuickML / deterministic | 0.87 golden set | — | Approved, read-only |
| Offender risk | TabFM (GPU) / kNN | calibration ECE | — | Acceptance gate open |

Reading live from the enablement registry, with the interval-coverage numbers included. A system that displays a model it refuses to promote, in the product, is making a strong argument about itself.

---

## 10. Workstream 6 — Temporal Fusion & Chronology

**Priority: P1 · Effort: 6–8 engineer-days · Highest visual impact per day spent.**

### 10.1 The gap

Gotham and i2 both rest on a tripod: **graph + map + timeline**. DRISHTI has two legs. `BoardTimeline.tsx` is 69 lines and `routes/cases/subpages/TimelinePage.tsx` is 77 — both are simple event lists, not analytical timelines. Meanwhile the corpus holds 386,990 `CaseEvent`, 64,391 `CourtEvent`, 72,762 `ArrestSurrender`, 27,196 `BailEvent`, 13,642 `Seizure`, 11,091 `StatementVersion` and 11,049 `FinancialTransaction` rows — all timestamped, all currently viewable only in separate tabs.

### 10.2 Design

**A unified chronology component** with entity lanes, zoom from years to minutes, and every timestamped record type as a filterable track:

```
                2026-03-14              2026-03-15              2026-03-16
Case 100239   ●FIR 02:14                                      ○CS due day 90
Accused A               ●arrest 09:40   ●bail applied
Phone  ...8821 ▮▮cell activity 01:50-02:30      ●SIM swap
Account ...4417                ●₹48,000 out 03:05
Evidence                ●CCTV upload   ●seizure video (missing → s.105 gap)
Court                                                  ●remand 11:00
```

Four capabilities beyond a list:

1. **Cross-entity temporal correlation.** Surface co-occurrence automatically: *"three phones registered at the same cell site within a 20-minute window"*, *"a transfer of ₹48,000 occurred 51 minutes after the reported theft"*. Implement as a windowed self-join over the fused event stream with a configurable window, ranked by improbability (rarity of the co-occurrence given base rates) rather than raw proximity.
2. **Gap detection.** *"No investigative activity recorded for 23 days."* Straightforward to compute, immediately valuable to supervisors, and it pairs naturally with Workstream 1's clocks.
3. **Series timeline.** Overlay a whole `CaseSeries` from Workstream 2 on one axis, revealing cadence — an offender striking every 4–6 days, or only on weekends.
4. **Board integration.** Any timeline selection becomes a board pin with its snapshot, so a chronology finding flows into the investigation narrative.

### 10.3 Implementation

**Endpoint:** `GET /timeline/fused?subject_ref=&subjects[]=&from=&to=&tracks[]=` returning a normalised event stream — `{t, track, kind, ref, label, detail, confidence}` — with server-side scope filtering applied per track, and `GET /timeline/correlations?...` for the windowed co-occurrence analysis.

**Service — `services/ml/app/timeline/`:** `fuse.py` (per-track extractors + normalisation), `correlate.py` (windowed co-occurrence + rarity scoring), `gaps.py`, `router.py`.

The main design care needed: each track extractor must apply its own scope guard, because fusing across tables is exactly where an unscoped join could leak an out-of-jurisdiction record. Route every extractor through the existing `enforce_geo_request` / `geoscope` helpers.

**Frontend:** one new component `components/timeline/ChronologyCanvas.tsx` (SVG or canvas; avoid a new dependency — Recharts is already present but is not suited to lane-based timelines, so a hand-rolled canvas is likely cleaner). Mounted in three places: Case File timeline tab (replacing the 77-line list), Investigation Board timeline drawer (replacing the 69-line version), and a new Network Analysis timeline mode.

Because it is one component reused three times, this is the cheapest large visual upgrade available.

---

## 11. Workstream 7 — Real RBAC, Purpose-Based Access & Redaction

**Priority: P0 · Effort: 8–10 engineer-days · This is a credibility gate, not a feature.**

### 11.1 The problem restated

An evaluator who opens `web/src/config/roles.ts:170` reads `return true`. One who opens `services/ml/app/roles.py:14-24` reads *"every role currently holds EVERY capability"*. The README makes strong claims about jurisdiction being part of correctness; the code grants everything to everyone, trusts `X-Role` from the browser by default, and leaves district narrowing inert (`org/scope.py:127-135`).

The good news: **the enforcement points are all built and centralised.** This is a matter of populating a matrix and turning on narrowing, not architecting from scratch.

### 11.2 What to do

**A. A real role × capability matrix.** Replace `full_grants()` (`roles.py:120-126`) with a differentiated matrix. Illustrative, to be agreed with the team:

| Capability | DGP | IGP | SP | DySP | SHO | IO | Analyst | Cyber | Traffic | Admin |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Case detail (PII) | ● | ● | ● | ● | ● | ◐¹ | ○² | ◐³ | ◐³ | ○ |
| Aggregate dashboards | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Case write | ○ | ○ | ○ | ◐ | ● | ● | ○ | ● | ◐ | ○ |
| Intake review | ○ | ○ | ● | ● | ● | ○ | ○ | ● | ● | ○ |
| Network analysis | ● | ● | ● | ● | ● | ● | ● | ● | ◐ | ○ |
| Money trail | ● | ● | ● | ◐ | ○ | ◐¹ | ● | ● | ○ | ○ |
| Investigation board | ● | ● | ● | ● | ● | ● | ● | ● | ◐ | ○ |
| Case-level export | ◐ | ◐ | ● | ● | ● | ◐¹ | ○ | ● | ○ | ○ |
| Aggregate export | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Identity merge | ○ | ○ | ◐ | ● | ● | ○ | ● | ● | ○ | ○ |
| Governance run/approve | ○ | ◐ | ◐ | ○ | ○ | ○ | ● | ○ | ○ | ● |
| Admin console | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |

¹ assigned cases only · ² aggregate + de-identified only · ³ own case category only
● granted · ◐ conditional · ○ denied

Note what this buys: the **Crime Analyst seat becomes genuinely interesting** — state-wide read-across but no PII. That is how real crime analysis units operate, and `nlsql/schema.py` already has `AGGREGATE_ONLY_ROLES` machinery to enforce it.

**B. Turn on geographic narrowing.** Fix `org/scope.py:127-135` so a district or station seat without a trusted assignment gets a **deny-by-default empty set**, not `None`. Seed the synthetic `users` rows with real `unit_id` / district assignments so each demo seat actually has a jurisdiction. Then `enforce_geo_request` (`:236-256`), which is already correct, starts doing real work.

**C. Enable the gateway enforcement path.** Set `DRISHTI_REQUIRE_GATEWAY_CONTEXT` in the deployed AppSail so `GatewayContextEnforcementMiddleware` stops being a no-op and `X-Role` stops being authoritative. The verification code, nonce replay guard and audience check already exist in `gateway_context.py`.

**D. Purpose-of-access.** Genuine world-class practice: before opening a PII-bearing record outside the user's own caseload, require a purpose selection (investigation of assigned case / supervisory review / analytical study / court preparation / public complaint response) with optional free text. Stored on the audit row. Implementation cost: one modal, one audit field, one middleware check. Deterrent value: substantial, and it is the single most-cited safeguard in police data-protection literature.

**E. Statutory redaction.** This is a legal requirement, not a nicety. BNS prohibits disclosing the identity of a victim of a sexual offence. Implement field-level redaction so victim identity in sexual-offence and POCSO-category cases is masked unless the seat holds a specific entitlement, with unmasking itself audited as a distinct action. Extend `guards.py`, which already has the `k_anon_suppress()` (k ≥ 10) pattern to build on.

**F. Break-glass access.** Sealed or restricted cases accessible only with mandatory justification plus immediate supervisor notification, time-limited, and prominently logged. Every serious police system has this; its absence is conspicuous.

**G. Access-anomaly detection.** `audit_logs` already records every read with actor, resource and IP. Add a nightly job flagging: reads far outside a seat's jurisdiction, volume spikes versus the officer's own baseline, repeated access to a single person's records without a case linkage, and after-hours bulk export. Surface in `/admin/access-review`. This is self-policing, and it is the strongest possible answer to "how do you prevent misuse".

**H. Resolve the person-risk contradiction.** Decide and document: either `GET /risk/entity/{id}?rescore=true` and `GET /risk/{accused_id}` stay, with explicit framing as investigative prioritisation, capability-gated to specific seats, audited on every call, and never surfaced as a persistent label on a person's profile — or they are removed. My recommendation is to keep the accused-level score for charged individuals within an active case context only, drop on-demand rescoring of arbitrary entities, and state the position plainly in the README. The current mismatch between the code and the responsible-use statement is the most easily attacked thing in the submission.

**I. Frontend cleanup.** Once `roleCan()` is real, the seven `Lock` / `EmptyState` gates become live. Test each one under each seat. If a gate is not intended to fire, delete it rather than leaving dead UI.

### 11.3 Demo moment

Sign in as Crime Analyst. Open a case: a redaction notice appears — aggregate and de-identified access only, with the capability that would be required named. Switch to SHO for the same station: full detail, but a purpose-of-access prompt first. Open `/admin/access-review`: the analyst's blocked attempt is logged, alongside a flagged anomaly showing an officer who read 40 records outside their jurisdiction last night. Then show the same seat being denied by the *server* with the browser role header spoofed, proving the boundary is real.

---

## 12. Workstream 8 — Field Mobility & Chain of Custody

**Priority: P2 · Effort: 10–14 engineer-days**

### 12.1 Rationale

Every user in the current build is at a desk. The Investigating Officer — the single most important role in the ten — works at scenes, in transit and in low-connectivity areas. And BNSS/BSA now impose evidence-capture duties precisely at the scene: s.105 audio-video recording of search and seizure, s.176(3) crime-scene videography for serious offences, and s.536 providing the statutory basis for audio-visual electronic evidence that underpins e-Sakshya.

This workstream is where compliance stops being a report and becomes the act of capture itself.

### 12.2 Scope for an MVP

Deliberately a **PWA, not a native app** — no app stores, one codebase, installable, and it reuses the entire existing API surface.

| Feature | Detail |
|---|---|
| Offline-first shell | Service worker + IndexedDB queue. My cases, today's taskings, and recent case files cached and readable with no connectivity. |
| Scene capture | Geo-tagged photo/video with client-side SHA-256 computed at capture, EXIF preserved, device id and timestamp bound in. |
| s.105 / s.176(3) guided capture | A checklist-driven flow: seizure recording, witness presence, scene walkthrough. The app knows which mandates apply from the case's sections and will not let the officer mark the step complete without the artifact. |
| Statement capture | Structured statement with optional Kannada voice dictation, reviewed and confirmed before submission. |
| Property / malkhana | QR-coded property items, custody transfer by scan. |
| Deferred sync | Queue with conflict handling; every queued item shows its state. Uploads use the existing pre-signed URL flow (`/evidence/items/{id}/upload-url` → `/complete`), so file bytes never traverse the API body. |
| Tasking acknowledgement | Accept and complete taskings from Workstream 3 in the field. |

### 12.3 Chain of custody, done properly

The existing evidence pipeline is already better than most: pre-signed PUT, SHA-256 verification on completion (`evidence/router.py:118`), versioning, archive/restore, and an activity trail. Extend it into a defensible custody chain:

- **Hash chain.** Each custody event stores `prev_hash`, and its own hash covers `(object_hash, actor, action, timestamp, prev_hash)`. Tamper-evident with no external dependency, and it makes an evidence-integrity claim you can demonstrate rather than assert.
- **Signed manifest per case.** An exportable manifest listing every artifact, its hash, custody chain and capture metadata, with a verification endpoint. `reports/router.py:78` already has a hash-verify pattern to follow.
- **BSA s.63 certificate scaffold.** Electronic evidence requires an accompanying certificate. Generate a pre-filled draft from the captured metadata — device, capture time, hash, custodian chain — for the officer to review and sign. Enormous practical value; a form generator, not AI.
- **Custody transfer** as an explicit two-party action (releasing and receiving officer), not a status edit.

### 12.4 What this replaces

`smartbrowz.py:47-56` currently returns `PNGSTUB DRISHTI` bytes for PDF export. Either wire the real Catalyst SmartBrowz path or generate PDFs server-side with a real library. A manifest or certificate that renders as a stub undermines the entire integrity story, so this must be genuine before the custody work ships.

---

## 13. Workstream 9 — Command & Supervisory Intelligence

**Priority: P1 · Effort: 7–9 engineer-days**

Currently `performance/router.py` has exactly **one** route, and `analytics/router.py` has two. For a platform whose primary users are five levels of command, supervisory tooling is thin.

### 13.1 Scheduled briefings

`nlsql/briefing.py` already composes a grounded multi-metric briefing, and `is_briefing_request()` routes to it. Make it scheduled and delivered:

- Catalyst Cron → `POST /internal/briefing/generate` per seat, at a configured hour.
- Output: a cited briefing with statutory clocks at risk, new series candidates, open deconfliction hits, forecast changes, workload anomalies and yesterday's tasking outcomes.
- Delivered through the existing notifications channels; archived as a hash-verifiable report snapshot via `reports/`.
- Available in Kannada.

A DGP receiving a one-page cited briefing at 07:00 every morning is a more compelling adoption story than any dashboard.

### 13.2 Supervisory analytics worth having

| Capability | Basis in existing data |
|---|---|
| **Disposal funnel** | FIR → investigation → chargesheet → trial → disposition. `CaseDisposition` (28,309) + `OutcomeObservation` (28,309) + `CourtEvent` (64,391) are all present and unused for this. |
| **Conviction-rate analysis** | By crime head, station, IO, and time-to-disposal. Identifies where cases fail — the question every SP actually asks. |
| **Trend-break detection** | Changepoint detection (PELT / CUSUM via scipy, already a dependency) on district series, with statistical significance rather than eyeballed spikes. |
| **Station scorecards with fairness guards** | Extend the single existing `performance` route. Normalise for workload, population and crime mix; publish the normalisation; refuse to rank on raw counts. The existing `limitations` disclosure at `performance/service.py:53-58` is the right instinct — build on it. |
| **Escalation engine** | Rule-based, e.g. heinous case with no arrest in 15 days, statutory clock at T-14, case unassigned for 72 hours, deconfliction hit open for 48 hours. `POST /notifications/escalations/run` exists; give it a real rule set. |
| **Court readiness** | Cases listed for hearing this week, witness summons pending, chargesheet-quality blockers unresolved. Directly reuses Workstream 1's readiness gate. |

### 13.3 Server-persisted personal workspace

`useSavedQueriesStore`, `useCohortsStore`, `useRecentsStore` and `useDashboardStore` are all localStorage-only. For a supervisor moving between an office desktop and a control-room terminal, this is a real defect, and it also blocks sharing a saved cohort with a subordinate. `/admin/saved-filters` endpoints already exist (`admin/router.py:180,188,197`) — promote all four stores to server persistence with local caching.

---

## 14. Workstream 10 — Foundation, Performance & Craft

**Priority: P0 (the pooling and bundle items) · Effort: 8–11 engineer-days**

These are unglamorous and they are what an evaluator experiences first.

### 14.1 Database connection pooling — do this first

`db.py:12-14` documents the current choice: a fresh psycopg2 connection per context-manager entry, chosen so `SET ROLE` / read-only session state cannot leak between callers. The reasoning is sound; the consequence is that every request pays full TCP + TLS + auth setup, and concurrent evaluators will exhaust `db.t4g.medium` connection capacity.

Fix without losing the safety property:

- Use `psycopg2.pool.ThreadedConnectionPool` (or pgbouncer in transaction mode) with **two separate pools** — one for `rw_conn`, one for `ro_conn`.
- On checkout of a read-only connection, `RESET ROLE` then `SET ROLE drishti_readonly`; on return, `RESET ROLE` and rollback. The isolation guarantee is preserved by explicit reset rather than by connection destruction.
- Add a test that asserts a pooled read-only connection cannot write and cannot retain a prior `SET ROLE`.

Expect the largest single latency improvement in the project from roughly a day of work.

### 14.2 Bundle: 3,836 kB → target under 600 kB initial

Currently no route-level code splitting. The heavy libraries — maplibre-gl, deck.gl (5 packages), sigma + graphology, reactflow, recharts, mapillary-js — all load on first paint even for a user who only opens the Command Center.

- `React.lazy` per route in `App.tsx` (30 routes, mechanical change).
- Dynamic-import the map stack inside `MapHotspots` / `LiveSituation`, the graph stack inside `NetworkAnalysis`, reactflow inside `BoardWorkspace`, mapillary-js only when street view opens.
- Manual `rollupOptions.output.manualChunks` for the map, graph and chart vendor groups.
- Add virtualization (`@tanstack/react-virtual`) for the 12k-point map lists and long case tables.

Target: initial JS under 600 kB gzip, with heavy chunks arriving on navigation. Ship a Lighthouse before/after in the README — a measured improvement is worth more than the claim.

### 14.3 Product-surface honesty pass

Cheap, and their absence is what makes a build feel unfinished:

- Delete `routes/Placeholder.tsx` (orphaned "Wave-C phase" screen).
- Remove the hardcoded `"NL→SQL · Phase 2"` chip (`components/ask/Composer.tsx:17`) and the two stale comments claiming the engine is unwired (`AskDrishti.tsx:14`, `CommandBar.tsx:32`) — it *is* wired.
- Remove internal prompt numbering from user-visible copy: `IntakeInbox.tsx:49-50`, `FirWizard.tsx:64-65`, `ReviewStep.tsx:8-9`.
- Move "Seed demo scenario" / "Fetch live feed" (`SituationOverview.tsx:38-49`) behind an admin-only or dev-flag surface.
- Make the red-zone alert acknowledgement real (`MapHotspots.tsx:121`).
- Keep the synthetic-data badging — it is the right call — but render it once in the shell rather than repeated per page.

### 14.4 Missing frontend infrastructure

The audit found no error boundary, no toast system, no form library and no i18n. Add: a route-level error boundary with a recovery action; a toast/sonner layer so mutations give feedback (many currently succeed silently); `react-hook-form` + `zod` for the FIR wizard and the new compliance and operation-registration forms.

### 14.5 Observability and accessibility

- p50/p95/p99 per endpoint and Web Vitals. `obs.py` `AccessLogMiddleware` exists but is off unless `DRISHTI_ACCESS_LOG_ENABLED` — enable it and add a latency panel to `/admin`.
- An in-product build/version panel (commit SHA, build time, model versions active) for evaluation traceability.
- Accessibility: keyboard-only traversal of the ten primary flows, focus management in dialogs, contrast audit, `aria-live` for async results, `prefers-reduced-motion` respected beyond the one place it currently is (`MapHotspots.tsx:168-172`). Target WCAG 2.2 AA, and state plainly that full conformance requires manual assistive-technology testing and expert review that has not yet been done.
- Extend the Playwright suite to cover the golden thread end to end, per seat.

---

## 15. Prioritisation and sequencing

### 15.1 Impact vs effort

```
        HIGH IMPACT
             │
  WS1 Compliance ●        ● WS3 Closed loop
  WS2 Linkage ●           ● WS5 AI real
             │   ● WS7 RBAC
  WS10a Pooling ●         ● WS4 Deconfliction
  WS5a Embeddings ●       │
  WS10b Bundle ●   ● WS6 Timeline
             │            ● WS9 Command intel
             │                      ● WS8 Field PWA
             │
        LOW ─────────────────────────────── HIGH EFFORT
```

### 15.2 Ranked backlog

| # | Item | WS | Days | Why this rank |
|---|---|---|---:|---|
| 1 | Connection pooling | 10 | 1–2 | Everything else is slower or falls over without it |
| 2 | Real case embeddings (batch, once) | 5 | 2 | Cheapest conversion of a fallback into a real model |
| 3 | Statutory compliance engine | 1 | 12–15 | Unique, India-specific, uses dormant data, changes the category |
| 4 | Real RBAC + geo narrowing + gateway on | 7 | 8–10 | Credibility gate; `roleCan(){return true}` is indefensible in a refinement phase |
| 5 | Closed-loop tasking + outcomes + PEI\* | 3 | 9–12 | Completes the governance thesis; nothing else in the field will have it |
| 6 | Crime linkage + series detection | 2 | 10–13 | Highest analytical craft; the "intelligence" in crime intelligence |
| 7 | Deconfliction | 4 | 3–4 | Best impact-to-effort ratio in the plan; officer-safety story |
| 8 | Bundle code-splitting + virtualization | 10 | 3–4 | First thing an evaluator physically experiences |
| 9 | Temporal fusion chronology | 6 | 6–8 | Completes the graph/map/timeline tripod; one component, three placements |
| 10 | Ask DRISHTI v2 agentic + golden set | 5 | 6–8 | Marquee feature genuinely upgraded, with a published number |
| 11 | Purpose-of-access + redaction + anomaly | 7 | 3–4 | Strongest available answer to "how do you prevent misuse" |
| 12 | Product-surface honesty pass | 10 | 2 | Removes every "unfinished" signal for two days of work |
| 13 | SSE real-time transport + broker | 4 | 4–5 | Liveness; keep polling as the correctness path |
| 14 | Scheduled briefings + supervisory analytics | 9 | 7–9 | Serves the five command seats that are currently thinnest |
| 15 | Kannada UI + IndicTrans2 + IndicWhisper | 5 | 5–7 | Karnataka credibility; unmatched demo moment |
| 16 | Server-persisted saved queries/cohorts | 9 | 2 | Fixes a real cross-device defect |
| 17 | Model Assurance surface | 5 | 2–3 | Turns the honest weakness into a governance feature |
| 18 | TimesFM decision + interval calibration | 5 | 3–4 | Resolve the ambiguity; fix 0.61 coverage on an 80% interval |
| 19 | Field PWA + chain of custody | 8 | 10–14 | Big reach expansion; correctly last because it depends on WS1 and WS3 |
| 20 | Observability + accessibility + e2e | 10 | 4–5 | Continuous, run alongside everything |

**Total: roughly 100–130 engineer-days.**

### 15.3 Three plans depending on time available

**Full plan — 12 weeks, 2–3 engineers (6 sprints)**

| Sprint | Focus | Exit criteria |
|---|---|---|
| 1 | Foundation: pooling, embeddings batch, bundle split, honesty pass | p95 latency halved; initial JS < 600 kB gzip; real 768-dim vectors in `CrimeEmbedding`; zero internal prompt references in UI |
| 2 | Statutory compliance engine | Clocks on all 100k cases; forensic + AV gaps detected; queue and case chip live; nightly cron |
| 3 | RBAC for real + purpose-of-access + redaction | Differentiated matrix enforced; geo narrowing active; gateway enforcement on; access-review panel |
| 4 | Closed loop: tasking, outcomes, scorecard, PEI\* | Accept/modify/reject with rationale on patrol + leads; auto-derived spatial outcomes; scorecard with resolution sensitivity |
| 5 | Crime linkage + series + timeline chronology | MO profiles extracted; series review queue; calibrated linkage; chronology in three placements |
| 6 | Deconfliction, Ask v2 + golden set, briefings, Kannada, polish | Deconfliction hits with pointer-only disclosure; published NL benchmark; scheduled cited briefings; Kannada UI toggle |

**Compressed — 6 weeks, 2 engineers**

Sprints 1–4 above, plus deconfliction (it is only 3–4 days and carries disproportionate weight) and the Model Assurance surface. Defer linkage, timeline, Ask v2, Kannada and the field PWA to a documented Phase 3. Rationale: compliance + RBAC + closed loop is a coherent, defensible story on its own — "we made it true and we made it accountable."

**Minimum viable — 3 weeks, 1–2 engineers**

Pooling, embeddings batch, bundle split, honesty pass, statutory compliance engine, deconfliction, Model Assurance surface. That is roughly 22–26 days and still delivers one genuinely novel capability (compliance), one standout safety feature (deconfliction), one fallback converted to real (embeddings), and a visibly faster, cleaner product.

**Recommendation if you must choose only one thing: the statutory compliance engine.** It is the only item that changes what category of product DRISHTI is.

### 15.4 Dependency graph

```
Pooling ──────────────► everything
Embeddings batch ─────► Linkage (narrative term)
Compliance ───────────► Chargesheet readiness ──► Court readiness (WS9)
              └───────► Field guided capture (WS8)
RBAC ─────────────────► Redaction ──► Purpose-of-access ──► Access anomaly
Tasking spine ────────► Patrol outcomes ──► Scorecard ──► Re-ranking
              └───────► Lead outcomes
              └───────► Series review ◄──── Linkage
Timeline fusion ◄───── (independent; can run in parallel any sprint)
Deconfliction ◄─────── Entity resolution (already exists)
SSE transport ────────► Live ops, deconfliction alerts, board collab
```

Only two hard sequencing constraints: pooling before load-sensitive work, and the tasking spine before any outcome metric. Everything else can be parallelised across two engineers.

---

## 16. The golden-thread demo

A refinement phase is judged on a narrative, not a feature list. One case, one continuous story, every new capability appearing where it naturally belongs. Target: eight minutes.

**02:14 — FIR registration.** A two-wheeler theft is registered at Rajajinagar. Nobody touches a keyboard for the next 90 seconds.

**02:14:03 — Statutory clocks start.** BNSS 193 chargesheet deadline computed from the section's punishment band. s.176(3) evaluated — offence under 7 years, forensic mandate not triggered, and the system says so with a citation rather than staying silent.

**02:14:11 — MO extraction and linkage.** Facets extracted; the case is scored against the corpus. Series `S-2026-041` surfaces: six prior thefts, confidence 0.81, driver = identical ignition-bypass method (present in 0.7% of all cases), 02:00–04:00 window, 600 m radius, 34-day span.

**02:14:19 — Deconfliction.** The complainant's phone number matches a subject in an open Cyber Cell investigation. Both supervisors are notified. Show the notice: unit name and contact designation only. Then show the audit row proving no case detail was disclosed. *"This is a pointer index, not a data share."*

**02:14:26 — Near-repeat forecast.** Elevated 14-day risk in four adjacent cells. A patrol tasking is proposed with its model version, feature snapshot and confidence interval attached.

**02:31 — The human decides.** The SHO reviews the tasking, modifies the window (festival deployment conflict), types a rationale, and accepts. The original recommendation is preserved immutably alongside the modification.

**Day 9 — The loop closes.** The tasked outcome is auto-derived: two incidents in the tasked cells versus 6.1 expected. The scorecard updates — PAI 3.14, PEI\* 0.42, acceptance rate 71%. *"This is the only system here that grades its own homework."*

**Day 34 — Chronology.** The IO opens the fused timeline: arrest, cell-site activity, a ₹48,000 transfer 51 minutes after the theft, CCTV upload, remand — all on one axis with entity lanes. A correlation is flagged automatically: three phones at the same cell site inside 20 minutes.

**Day 76 — The clock bites.** No chargesheet, accused in custody. A default-bail exposure alert reaches the SP: 14 days remaining, and separately the s.193(8) document set is incomplete, so filing alone would not clear it. Cite the section.

**Day 76, second screen — Access control is real.** Switch to Crime Analyst: the case detail is redacted with the required capability named. Spoof `X-Role: dgp_state_command` in the browser and the server still denies it, because the gateway derives the role independently.

**Closing — Ask DRISHTI, in Kannada.** Dictate: *"Which stations in my district have chargesheet deadlines at risk this month?"* The agentic planner runs three tools, returns a cited answer with a chart, lists every endpoint it called, and names the planner that served it. Then show the Model Assurance screen — including the workload model the system openly refuses to promote because it lost to a baseline.

**The last line.** Every step above was cited, attributed to a named human, reversible, and audited. Nothing was decided by a model.

---

## 17. What NOT to build

Scope discipline is worth as much as scope ambition, and being explicit about refusals is itself a governance signal.

| Do not build | Why |
|---|---|
| **Face recognition / biometric identification** | No lawful basis in this prototype, no data, and it would contradict the responsible-use statement. `evidence_extraction_enabled = false` at `config.py:55` is the correct call — keep it, and say why. |
| **Live CCTV / ANPR / video analytics ingest** | This is Fusus's core and it needs real camera infrastructure. Attempting it on synthetic data produces a fake. Note the Karnataka HC CCTV-monitoring direction as future integration context instead. |
| **Autonomous dispatch or enforcement** | The whole architecture is built on human authority. Do not erode it for a demo effect. |
| **Individual predictive risk labels on people** | Feedback loops and automation bias. Keep suspect prioritisation as a transient, evidence-linked query result, never a stored attribute. Resolve the existing `/risk/entity` contradiction. |
| **Social media / OSINT scraping** | Legal exposure, no consent basis, and it would swamp the governance story. |
| **A native mobile app** | A PWA delivers the field capability without app-store overhead or a second codebase. |
| **Migrating off Catalyst** | It is the evaluation deployment. Optimise within it. |
| **New destinations beyond compliance, linkage/series, operations** | The sidebar is already at ten crime destinations. Depth, not breadth. |
| **Replacing the deterministic NL→SQL fallback** | It is the fail-closed path and a genuine safety asset. Add a semantic primary above it; keep the fallback. |
| **Rewriting the Investigation Board** | It is the strongest existing feature. Extend it with timeline and series pinning; do not touch its core. |
| **Removing polling in favour of SSE** | The reconnect-with-`after_id` replay design is the correctness guarantee. SSE is an optimisation on top. |

---

## 18. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|:--:|:--:|---|
| **Statutory rules encoded incorrectly** | Medium | High — wrong legal advice is worse than none | Every rule carries a `Citation`; validate against the BNSS ready-reference material; label the engine as advisory decision support; make every gap disputable; have a law student or practitioner review the rule table. Do not ship a rule you cannot cite. |
| **Punishment-years seeding is a data slog** | High | Medium | Scope to the BNS sections actually present in the corpus, not the whole statute. Budget 2 days. Record a source per value and a null-safe default that fails to "mandate not evaluated" rather than "mandate not required". |
| **Linkage produces confident nonsense on synthetic MO** | Medium | High | The corpus was generated, so MO facets may be less distinctive than reality. Calibrate on confirmed shared-accused pairs; report the operating point and its precision honestly; consider enriching `datagen` with deliberate offender signatures so the capability has something real to find. |
| **Suspect prioritisation read as predictive policing** | Medium | Very high | Guardrails in §6.2D are mandatory, not optional. Lead-list framing, no stored person score, mandatory rationale, protected features excluded and asserted in a test. If the framing cannot be made airtight, ship series detection without suspect prioritisation. |
| **Scope creep across ten workstreams** | High | High | Use the ranked backlog. Complete items rather than starting many. A half-built compliance engine is worth less than nothing. |
| **Real model paths cost GPU money** | Medium | Medium | Embeddings are a one-time batch. TimesFM acceptance is a bounded run of a few GPU-hours. Both are capped, one-off costs — budget them explicitly rather than leaving them open-ended. |
| **RBAC tightening breaks the demo** | Medium | Medium | Every demo seat needs a seeded jurisdiction assignment before narrowing goes on, or screens go empty. Do this in the same PR, and add an e2e test per seat. |
| **SSE without a broker misleads on scalability** | Low | Medium | State the single-instance limitation plainly in the README. An honest limitation beats an unqualified real-time claim. |
| **Bundle split introduces route-level regressions** | Medium | Low | Playwright coverage of all 30 routes before splitting; add a suspense fallback per route. |
| **Compliance engine is read as officer surveillance** | Medium | High | Frame and build it as a support tool: gaps are disputable, scorecards are workload-normalised with the normalisation published, and no individual officer metric feeds a disciplinary surface. Document this stance in the README. |

---

## 19. Measurable success criteria

Phase 2 should be judged on numbers, not adjectives. Commit to these up front.

**Functional**

- [ ] Statutory obligations computed for **100% of 100,003 cases**, each citing a statute section
- [ ] Forensic-mandate and AV-record gaps detected across the corpus, with counts published
- [ ] Default-bail exposure list live, escalating at T-21 / T-14 / T-7
- [ ] Chargesheet readiness checklist returning a blocking list per case
- [ ] MO profiles extracted for 100% of cases; ≥ 50 candidate series surfaced with calibrated confidence
- [ ] Linkage precision reported at the chosen operating point against shared-accused ground truth
- [ ] Recommendation → decision → outcome loop closed for **at least two** recommendation classes
- [ ] PAI, hit rate **and PEI\*** published, plus the grid-resolution sensitivity curve
- [ ] Deconfliction detecting all three hit types, with a test asserting no PII in the hit payload
- [ ] Fused chronology live in three placements with automatic correlation flagging
- [ ] Kannada UI toggle covering shell, navigation, role labels and case-file field labels

**AI honesty**

- [ ] Real 768-dim sentence-transformer vectors in `CrimeEmbedding` for the full corpus
- [ ] NL→SQL golden set of ≥ 150 questions published, with accuracy reported per language and per role
- [ ] 100% correct refusal on out-of-scope and aggregate-only probes — **zero** scope violations
- [ ] TimesFM position resolved: either a real GPU acceptance backtest recorded, or the serving forecaster renamed
- [ ] 80% prediction interval achieving ≥ 0.75 empirical coverage (from 0.6094)
- [ ] Model Assurance surface live, reading the enablement registry, showing at least one non-promoted model

**Security and governance**

- [ ] `roleCan()` returns differentiated results; every capability gate exercised per seat in e2e tests
- [ ] Geographic narrowing active: a station seat provably cannot read another district
- [ ] `DRISHTI_REQUIRE_GATEWAY_CONTEXT` enabled; spoofed `X-Role` demonstrably rejected
- [ ] Purpose-of-access captured on PII reads and stored on the audit row
- [ ] Statutory victim-identity redaction enforced, with unmasking audited as a distinct action
- [ ] Access-anomaly detection running nightly with results in `/admin/access-review`
- [ ] Person-risk position resolved and documented; no contradiction between code and README

**Performance**

- [ ] Connection pooling live; **p95 API latency reduced ≥ 50%** under a 20-concurrent-user load test (`scripts/load_test.py` exists — use it)
- [ ] Initial JS bundle **< 600 kB gzip** (from 1,044 kB)
- [ ] Lighthouse performance ≥ 85 on Command Center and Case Explorer
- [ ] Map renders 12k points without main-thread block > 200 ms
- [ ] Zero unhandled promise rejections and zero console errors on the golden thread

**Craft**

- [ ] No internal prompt/phase numbering in any user-visible string
- [ ] `Placeholder.tsx` deleted; no orphaned routes
- [ ] Every mutation gives user feedback (toast or inline state)
- [ ] Route-level error boundary with a recovery action
- [ ] Playwright coverage of the golden thread for all ten seats
- [ ] WCAG 2.2 AA automated checks passing, with manual-testing caveat stated honestly

---

## 20. Sources

Competitive and domain research underpinning §3. Content was rephrased for compliance with licensing restrictions.

**Reference platforms**
- Palantir — [Case Management](http://www.palantir.com/solutions/case-management/); [Gotham AI-Enabled Operations white paper](https://www.palantir.com/assets/xrfr7uokpv1b/3A0y10xksgXENvRMNaAsUu/ed8f7f1ed534c0101f64536a85f7297b/Gotham_AI-Enabled_Operations_White_Paper.pdf)
- Independent Gotham analysis — [Golding Research, Sep 2025](https://goldingresearch.substack.com/i/173524962/weaknesses-and-gaps)
- Axon — [Ultimate Guide to Real-Time Crime Centers](https://www.axon.com/resources/real-time-crime-center); [Axon Fusus](https://www.axon.com/products/axon-fusus); [Peoria PD RTCC](https://www.axon.com/resources/how-peoria-pd-built-an-award-winning-rtcc)
- IBM i2 — [Analyst's Notebook overview](https://www.ibm.com/id-en/products/i2-analysts-notebook); [details](https://www.ibm.com/id-en/products/i2-analysts-notebook/details); [9.3 chart store announcement](https://www.ibm.com/common/ssi/ShowDoc.wss?docURL=/common/ssi/rep_ca/5/899/ENUSLP21-0365/index.html)
- i2 Group — [What is link analysis (POLE model)](https://i2group.com/articles/what-is-link-analysis-and-link-visualization)

**Crime linkage**
- [Bennell et al., ViCLAS evaluation](http://eprints.lancs.ac.uk/53598/4/Bennell_et_al_ViCLAS_Final_Nov_21.pdf)
- [ViCLAS technical overview](https://www.emergentmind.com/topics/violent-crime-linkage-analysis-system-viclas)
- [A Statistical Approach to Crime Linkage (Bayes factors)](https://www.researchgate.net/publication/266748053_A_Statistical_Approach_to_Crime_Linkage)
- [Modelling crime linkage with Bayesian networks](https://www.researchgate.net/publication/271080746_Modelling_crime_linkage_with_Bayesian_networks)
- [Crime linkage: comprehensive review of data-driven approaches](https://arxiv.org/html/2411.00864v1)

**Deconfliction**
- [BJA — Enhancing Officer Safety Through Event Deconfliction Systems](https://bja.ojp.gov/sites/g/files/xyckuh186/files/media/document/event_deconfliction_call_to_action1-2.pdf)
- [DOJ — RISSafe overview](https://www.justice.gov/file/440496/dl?inline)
- [NCIRC — Event Deconfliction](https://ncirc.bja.ojp.gov/event-deconfliction)
- [Chicago HIDTA — pointer-index architecture](https://www.chicago-hidta.org/deconfliction)

**Indian statutory and systems context**
- [MHA — Inter-Operable Criminal Justice System (ICJS)](https://www.mha.gov.in/en/commoncontent/inter-operable-criminal-justice-system-icjs)
- [MHA — CCTNS deployment status, 2026](https://www.mha.gov.in/MHA1/Par2017/pdfs/par2026-pdfs/RS11032026/2154.pdf)
- [BNSS s.176(3) forensic mandate — constitutional analysis](https://3fdef50c-add3-4615-a675-a91741bcb5c0.usrfiles.com/ugd/3fdef5_7ba4e649b4a1492084db8062fe6505d0.pdf)
- [LiveLaw — Allahabad HC on s.105 BNSS videography non-compliance](https://www.livelaw.in/high-court/allahabad-high-court/allahabad-high-court-police-non-compliance-section-105-bnss-videography-search-seizure-547230)
- [Supreme Court Observer — default bail and s.193(8) document copies](https://www.scobserver.in/supreme-court-observer-law-reports-scolr/eligibility-for-default-bail/)
- [BNSS s.536 and the e-Sakshya framework](https://www.granthaalayahpublication.org/Arts-Journal/ShodhKosh/article/download/8559/7770/46199)
- [Vidhi Centre for Legal Policy — Procedure in Practice: on the BNSS](https://vidhilegalpolicy.in/wp-content/uploads/2026/05/Procedure-in-Practice.pdf)
- [Karnataka State Police — technology posture](https://bangaloreurbanpolice.karnataka.gov.in/english)
- [The Hindu — Karnataka HC orders centralised state-level CCTV monitoring system](https://www.thehindu.com/news/national/karnataka/karnataka-high-court-orders-cctv-audit-at-all-police-stations-across-state/article71369726.ece)

**Forecast evaluation**
- [Discussion of crime forecasting indices and PEI\* improvement](https://link.springer.com/10.1057/s41284-023-00367-4)
- [Spatial resolution effects on RTM performance, 2026](https://link.springer.com/article/10.1007/s12061-026-09888-y)
- [Near-repeat vs ML vs RTM comparison](https://link.springer.com/article/10.1007/s12061-020-09339-2)
- [RTM systematic review and meta-analysis](https://link-hkg.springer.com/article/10.1186/s40163-021-00149-6)
- [NIJ — Measuring how relatively good a hot-spot map is](https://www.ojp.gov/pdffiles1/nij/305365.pdf)

**Indic language models**
- [AI4Bharat IndicTrans2](https://github.com/ai4bharat/IndicTrans2); [AIKosh model card](https://aikosh.indiaai.gov.in/home/models/details/indic_trans2.html)
- [IndicWhisper / Vistaar benchmark](https://arxiv.org/html/2305.15386v1)
- [IndicBERT v3](https://huggingface.co/ai4bharat/IndicBERT-v3-1B)

**Platform**
- [Catalyst Job Scheduling](https://docs.catalyst.zoho.com/en/job-scheduling/getting-started/introduction/); [Catalyst Cron](https://docs.catalyst.zoho.com/en/cloud-scale/help/cron/introduction/); [QuickML LLM Serving](https://docs.catalyst.zoho.com/en/quickml/help/generative-ai/llm-serving/)

---

## Appendix A — New files and modules

```
services/ml/sql/
  024_statutory_compliance.sql
  025_crime_linkage.sql
  026_tasking_outcomes.sql
  027_deconfliction.sql
  028_custody_chain.sql

services/ml/app/
  compliance/    rules.py engine.py gaps.py service.py schemas.py router.py
  linkage/       facets.py scoring.py series.py suspects.py service.py router.py
  tasking/       recommend.py decisions.py assignments.py outcomes.py scorecard.py router.py
  deconfliction/ detect.py notify.py service.py router.py
  timeline/      fuse.py correlate.py gaps.py router.py
  nlsql/agent.py                     # multi-step tool-calling planner
  nlsql/tools.py                     # typed, role-filtered, read-only tool registry
  custody/       chain.py manifest.py certificate.py router.py

services/ml/eval/
  nlsql_golden.jsonl                 # >=150 Q/A pairs, EN + Kannada + transliterated
  linkage_calibration.py

web/src/
  routes/compliance/                 # 4 modes
  routes/linkage/                    # series review queue
  routes/ops/                        # live operations + deconfliction
  routes/cases/subpages/CompliancePage.tsx
  components/timeline/ChronologyCanvas.tsx
  components/tasking/DecisionDialog.tsx
  realtime/useRealtimeChannel.ts
  i18n/                              # en.json, kn.json
```

## Appendix B — Immediate next actions

1. **Decide the deadline and headcount.** The three plans in §15.3 assume 12 / 6 / 3 weeks. Everything else follows from this.
2. **Confirm the compliance scope.** Which BNSS obligations to encode in v1. My recommendation: chargesheet deadline, progress intimation, forensic mandate, AV record, chargesheet completeness. Five rules, high value, all citable.
3. **Sign off the RBAC matrix** in §11.2 — it needs a decision from whoever owns the product story, not just an engineer.
4. **Resolve the person-risk question** (§11.2H) before writing any linkage code, because the answer shapes the suspect-prioritisation design.
5. **Provision one GPU session** for the embeddings batch and, if Option A is chosen, the TimesFM acceptance run. Both are one-off and cost-bounded.
6. **Start with pooling.** One to two days, and it makes every subsequent demo faster.

---

<p align="center">
  <strong>DRISHTI Phase 2</strong><br />
  Make it true · Close the loop · Know the law
</p>
