# DRISHTI — Production role, dashboard and analytics plan

**Prepared:** 7 September 2026  
**Status:** Proposed product and implementation specification; not an implementation or production-readiness certification.  
**Basis:** Current working-tree code and a read-only query of the configured PostgreSQL database. No application settings or permissions were changed to produce this plan.

## 1. How many roles are there?

**There are six core application roles. The live database currently contains exactly these six roles and zero custom roles.** Keep this model. Different ranks and postings should select different dashboard profiles without creating a new application role for every rank.

| Application role | Display name | Allowed scope | Default experience | User rows currently linked to role |
|---|---|---|---|---:|
| `dgp_state_command` | DGP / State Command | State | State priorities and oversight | 2 |
| `senior_command` | Senior Command | Functional wing or geographic range | Wing specialist dashboard or range supervision | 18 |
| `district_command` | District Command | District or commissionerate | District / city operations | 41 |
| `sho` | Station House Officer | One station | Station queues and workload | 1,001 |
| `investigating_officer` | Investigating Officer / Case Assistant | Assigned cases | Personal case workspace | 10,761 |
| `system_admin` | System Admin | Platform | Service, access and data operations | 2 |
| **Total** | **6 roles** | | | **11,825** |

These are database user-row counts, including any demo/test or inactive rows; they are **not** verified active users, sanctioned posts or a real police establishment count. The scope counts are state 2, wing 10, range 8, district 35, commissionerate 6, station 1,001, assigned-case 10,761 and platform 2.

There are **eight operational dashboard profiles**: state, wing, range, district, commissionerate, station, assigned-case and platform. `unresolved` is an access/setup state, not a ninth operational dashboard. The wing profile has six specialisations. Case assistants share the assigned-case profile but have fewer actions than lead investigators.

Custom roles already have a schema and administration service. A custom role should compose approved capabilities and one existing dashboard surface; creating one must not silently grant a broader scope.

## 2. What the current project already has—and what needs changing

| Observed in the current source | Production decision |
|---|---|
| Six roles and scope-based boards exist in frontend and backend. | Retain the role/scope separation; do not revert to the old ten-role vocabulary. |
| The KPI registry defines **50 cards**. Boards automatically append eligible cards even when they were not explicitly ordered. | Make the primary board an explicit allow-list. New registry entries must not automatically appear on every eligible board. |
| Nine IDs have no explicit value binding in `useKpiValues.tsx`: flagged transactions, circular flows, resolved account links, intake review queue, evidence pending, active seats, pending imports, model count and UI overrides. | Complete their aggregate endpoints/bindings before exposing them as working cards. The existence of a registry entry is not implementation evidence. |
| The KPI resolver invokes many data hooks together, including model, network and socioeconomic hooks. | Fetch only the authorised modules needed for the selected board/tab. Check each hook's internal gates; do not rely on hiding its card. |
| State and wing scopes are marked aggregate-only. | Keep case files, named people, face portraits and raw evidence out of these profiles. Aggregate drill-downs must remain aggregate. |
| Several cards declare `reach: client` or `reach: none`; some totals are calculated from returned lists. | Require server-enforced scope and uncapped aggregate totals. A capped list length is not a valid headline total. |
| Station/IO map widgets can show district-grain hotspots. | Do not label district hotspots as station or personal hotspots. Use properly scoped incident maps, or clearly separated district context only when explicitly authorised. |
| The current performance service treats an open case older than 90 days as an overdue review and uses a fixed heavy-load threshold of 15. | Label these as current demo rules. Actual overdue reviews need due-date and completion records; capacity thresholds must be configurable and contextual. |
| Performance, caseload and outcome code use different lifecycle concepts; chargesheet filing appears in the performance service's disposed-status set. | Publish a common lifecycle dictionary. Chargesheet filing is a milestone; do not present it as final court disposal. |
| Demo analytics can use the dataset's as-of date; some card windows are fixed at 90 days. | Separate historical demo mode from live mode. One visible analysis window and one comparable data snapshot must apply across a board. |
| Capability helpers still document broad interim permissions; UI visibility switches are presentation controls. | Production release requires actual backend capability checks and trusted identity. A polished UI alone does not close this gap. |

This plan proposes changes beyond the earlier `role-scoped-command-plan.md`, including a genuine production access model. It does not silently change that earlier phase's decision to operate without authentication/RLS.

## 3. Shared dashboard design

### 3.1 Page composition

Every home dashboard should have a consistent shell but a different operational purpose:

1. **Context header:** dashboard title, officer posting, scope, date window, data-as-of time and live/synthetic badge. Geographic selectors only offer allowed descendants.
2. **Primary KPI row:** six cards, normally a three-by-two layout on laptop screens. Each card answers a distinct question; do not show multiple versions of the same count.
3. **Main analytical row:** one wide trend/comparison chart and one narrower distribution or forecast chart.
4. **Operational row:** a map, an exception queue or an actionable work table. Use at most four analytical widgets on the overview; deeper views are separate tabs.
5. **Trust strip:** freshness, coverage, missing records and model limitations. Technical details open on demand rather than occupying executive KPI slots.

Keep each KPI's label, unit, time basis, comparison and click action visible. A click should preserve filters and open the corresponding authorised rows or aggregate breakdown. A card with no legitimate drill-down should explain its calculation instead of implying one exists.

### 3.2 Time and comparison rules

| Metric type | Default | Comparison |
|---|---|---|
| State / wing / range demand | Last 30 complete days; 90-day and annual views available | Prior equal-length period; same period last year as a selectable comparison |
| District demand | Last 30 complete days | Prior equal-length period, with daily trend available |
| Station demand | Today, with 7-day overview | Same elapsed period yesterday or corresponding previous week; never a partial day versus a full day |
| Personal work | Today and next 7 days | Due dates and completion state; avoid meaningless percentage deltas on tiny queues |
| Open cases, unassigned cases, pending queues | Snapshot at the stated as-of time | Previous stored snapshot if available; otherwise no invented delta |
| Court/chargesheet outcomes | Clearly specified event-date cohort or registration cohort | Compare like cohorts; disclose pending/censored cases |
| Live operations | Current shift / last 24 hours | Comparable completed shifts |
| Platform health | Last 24 hours; 30-day service trend | Defined operational target and prior period |

Store timestamps consistently and display local operational time in Asia/Kolkata. In historical demo mode, freeze one shared reference date; in live mode use the real clock and ingestion watermark. Do not anchor each district to a different maximum event date and then compare them as if they cover the same period. A newly inserted test record must not shift the whole historical window.

### 3.3 Status and colour rules

- **Zero:** a valid measurement found no matching records.
- **No data:** the requested source/window has no usable observations.
- **Unavailable:** the source or calculation is not ready; never substitute zero.
- **Stale:** show the last successful value with its age and reason.
- **Suppressed:** explicitly indicate privacy/low-sample suppression without exposing hidden counts through totals or drill-downs.
- **Restricted:** do not fetch or render the data. An unposted seat sees a posting-resolution page.

Use red/amber for a defined exception, overdue item or service breach. More registered FIRs, more verdicts or fewer reports are not inherently good or bad. Remove universal “lower is better” defaults from neutral demand metrics. Use text and icons alongside colour, keyboard-accessible tables and chart data alternatives.

## 4. Role-by-role specification

Readiness notation throughout: **E** = a relevant endpoint/source exists, but still requires scope and formula verification; **W** = additional aggregation, binding or workflow definition is needed; **N** = new instrumentation/data collection is needed. These are implementation assessments, not claims that a live production feed exists.

### 4.1 DGP / State Command

**Purpose:** identify state-wide pressure, service delays and decisions requiring command attention.  
**Scope:** state aggregates only.  
**Tabs:** Overview · Demand & geography · Service & workload · Outcomes · Readiness.

| Primary card, in order | What it means | Click destination | Readiness |
|---|---|---|---|
| New FIRs — selected period | Distinct registered cases in the period; volume is neutral | Range/district aggregate trend | E |
| Active investigations | Investigation-phase cases at the snapshot, separate from pending trial | Lifecycle totals by range | W |
| Critical unresolved escalations | Reviewed operational escalations still awaiting action | Redacted escalation queue with owner and age | W |
| Reviews overdue | Outstanding reviews whose actual due date has passed | Aggregate overdue buckets by command | W |
| Median response time | Confirmed incident to recorded on-scene arrival | Median/P90 by geography and incident class, with sample size | W |
| P90 station workload | 90th percentile of active investigations per eligible lead investigator, across stations | Capacity comparison with staffing/coverage context | W |

**Overview graphs:** 12-month registered-case trend with equal-period comparison; range workload versus available capacity; aggregate district incident map; command exception table. Put the map below the first analytical row rather than making it decorative background.

**Detailed analytics:** crime-head composition and change; backlog ageing; resources requested versus available; chargesheet filing duration; verdict/disposition mix with denominators; area demand forecasts with intervals; district data-coverage exceptions. Socioeconomic associations belong on an optional research tab, not a large permanent home-page band.

**Actions:** request a command review, assign an escalation owner, acknowledge a briefing and export aggregate briefing material. Formal operational approvals require a separately defined capability/workflow.

**Keep off this board:** named accused, portrait galleries, entity centrality rankings, individual money trails, live camera mosaics, case editing, raw model registry counts, API contract-conformance cards and officer league tables.

### 4.2 Senior Command — geographic range

**Purpose:** supervise differences between districts and remove cross-district bottlenecks.  
**Scope:** only districts in the officer's assigned range.  
**Tabs:** Overview · District comparison · Backlog & capacity · Trends & forecasts · Escalations.

| Primary card | Click destination | Readiness |
|---|---|---|
| New FIRs — selected period | District demand breakdown | E |
| Active investigations | District lifecycle totals | W |
| Critical unresolved escalations | Range escalation queue | W |
| Reviews overdue | District-by-age overdue breakdown | W |
| Stations above capacity threshold | Station comparison with staffing denominators | W |
| Median days to chargesheet filing | Filing-date cohort and duration distribution | E |

**Overview graphs:** district workload comparison with staffing context; backlog ageing stacked bars by district; weekly demand trend; district-grain forecast with prediction intervals. Map and additional charts move to Trends & forecasts if four overview widgets are already present.

**Detailed analytics:** within-range demand seasonality; crime-head mix; pending dependencies; district response-time distributions; verified cross-district pattern summaries; court outcome cohorts; data quality by district. Comparisons must include sample size and case mix rather than a single “best/worst district” score.

**Actions:** request district review, route an escalation to the appropriate district and propose cross-district resource coordination. Routine case changes remain with the operational owner.

**Detail access:** aggregate-first. Scoped case inspection can be a separately granted supervisory permission with an audit trail. Current catalogue scope rules may not permit this at range scope; add an explicit reviewed exception model rather than bypassing them or granting broad case access by rank.

**Hide:** other ranges and commissionerates outside scope, unrestricted people search, officer punishment rankings and platform configuration.

### 4.3 Senior Command — functional wing

**Purpose:** statewide specialist oversight, restricted to the wing's configured crime heads.  
**Scope:** geography is statewide; subject-matter scope remains restricted. The Crime & Technical Services wing's current all-head remit is a configured exception.  
**Tabs:** Wing overview · District comparison · Specialist analytics · Quality & outcomes.

The first three cards are **New FIRs in wing scope**, **Active investigations in wing scope** and **Critical unresolved wing escalations**. The next three vary by wing:

| Wing | Three specialist primary cards | Specialist graphs | Detailed analytics and boundaries |
|---|---|---|---|
| Law & Order (`LO`) | Reviews overdue; active confirmed public-order incidents; response-time P90 | Incident trend by category; district response distribution; demand by hour/day | Event readiness and resource gaps when event/roster data exists. Separate reported events from confirmed operational incidents. |
| Crime & Technical Services (`CTS`) | Data feeds meeting freshness target; unresolved data-quality exceptions; forecast WAPE | Completeness/freshness by district; observed versus predicted demand; calibration/interval coverage | Taxonomy consistency, duplicate-record review totals, backtest performance, drift and model release evidence. Model approval is a separate entitlement. |
| Intelligence (`INT`) | Validated pattern reviews pending; cross-district alerts awaiting review; reviews past due | Pattern category trend; aggregate district relationship heatmap; alert-age distribution | Source provenance and analyst review outcomes. Keep named networks and person-level predictions off the wing dashboard; a detected association is not proof of criminal activity. |
| Internal Security & Cyber (`ISC`) | Financial alerts awaiting review; digital-evidence requests overdue; median specialist-review turnaround | Cyber category trend; review-status distribution; request-age chart | Aggregate financial anomaly review and evidence bottlenecks. Do not expose account numbers or raw transaction trails to an aggregate-only seat. |
| Traffic & Road Safety (`TRF`) | Confirmed road incidents; response-time P90; verified unresolved road-safety actions | Incidents by hour/day; validated severity breakdown; road-incident concentration map | Corridor analysis requires road-linked coordinates. Traffic-offence records must not be presented as crashes, injuries or fatalities without those fields and validation. |
| CID / Economic Offences (`CID`) | Reviews overdue; evidence/lab dependencies overdue; median filing duration | Backlog by case stage; dependency-age distribution; disposition mix | Aggregate economic/property/drug case oversight within configured heads; verdict cohorts and specialist case-transfer turnaround. Financial details require separate case-level access. |

These specialist cards are predominantly **W/N**. The existing financial KPI IDs are not yet bound in the common resolver. Event readiness, road-safety actions and specialist request timing need explicit sources; hide their modules until usable data exists.

**Common overview graphs:** wing demand trend, district comparison within wing scope, crime-head composition and one wing-specific analytical panel. Do not show every specialist graph on every wing.

**Hide for every wing:** unrelated heads, named accused/portraits, raw evidence, arbitrary case edits and other wings' specialist modules. Changing a district filter must never remove the wing restriction.

### 4.4 District Command — SP and CP

**Purpose:** turn district/city demand into assignments, reviews and coordinated response.  
**Scope:** one district or one commissionerate, including only its stations. These share the application role but need distinct titles and geographic defaults.  
**Tabs:** Overview · Station workload · Case flow & reviews · Incident response · Outcomes & quality.

| Primary card | Click destination | Readiness |
|---|---|---|
| New FIRs — selected period | Scoped station-level registration breakdown | E |
| Active investigations | Authorised case list by lifecycle stage | W |
| Unassigned investigations | Assignable-case queue | W |
| Reviews overdue | Supervisory review queue | W |
| Intake drafts awaiting review | Station-by-station pending queue | W |
| Median response time | Confirmed incidents with timestamps and P90 | W |

**Overview graphs:** station demand/capacity comparison; registration and filing trend; backlog ageing by station; incident-response queue with a map. A comparison table should carry case count, lead-investigator capacity, missing-capacity flag, review backlog and last update.

**Detailed analytics:** crime-head mix; investigator-load distribution; unassigned-case duration; review turnaround; evidence/lab bottlenecks; charge-sheet filing durations; court outcome cohorts; station data quality; approved district demand forecasts. Link/financial analysis is case-specific and permission-gated, not a blanket dashboard capability.

**CP-specific view:** prefer city station/beat boundaries, shift demand, corridor incidents and command-centre response status where those sources exist. Do not invent subdivision/beat-level metrics from district aggregates. Other commissionerates are outside the profile's data scope.

**Actions:** assign a review, approve an authorised transfer or jurisdiction override, coordinate resources and export audited scoped reports. Editing evidentiary content is not a default SP/CP responsibility.

**Hide:** state-wide raw case search, other districts' identifiable records, model promotion, platform settings and blanket CCTV/face access.

### 4.5 SHO — station dashboard

**Purpose:** organise the station's work today.  
**Scope:** the station's cases, personnel capacity and incident-response responsibilities.  
**Tabs:** Today · Intake & assignment · Cases & deadlines · Evidence & hearings · Station trends.

| Primary card | Click destination | Readiness |
|---|---|---|
| FIRs registered today | Today's station registrations | W: current performance default is not today |
| Active investigations | Station investigation queue | W |
| Unassigned investigations | Eligible lead-investigator assignment queue | W |
| Intake drafts awaiting review | Submitted drafts awaiting action | W: registry binding missing |
| Deadlines due in next 7 days | Review/task deadlines grouped by case | W |
| Evidence requests overdue | Collection/lab/result dependency queue | W: workflow and binding needed |

**Overview graphs/widgets:** station case-stage distribution; investigator workload table with capacity/context; deadline calendar; attention queue sorted by explicit due date and reviewed urgency. Avoid a graph that has no follow-up action.

**Detailed analytics:** daily registration trend; open-case age buckets; assignment delay; intake returns and reasons; review turnaround; evidence turnaround; upcoming hearings; station incident map if exact scoped data exists. The station should not inherit the district's forecast as if it were station-specific.

**Actions:** review intake, assign/reassign eligible officers, request corrections, track evidence dependencies and perform authorised incident response. Case closure and transfers follow explicit approval rules with reasons and audit records.

**Hide:** statewide research correlations, model benchmarking, conviction-rate league tables, other stations' individual cases, district-wide people search, platform settings and automatic predictions about people.

### 4.6 Investigating Officer / Case Assistant

**Purpose:** show the next useful action on assigned work.  
**Scope:** explicitly assigned cases and tasks; station membership alone does not grant every station case.  
**Landing:** personal case workspace, not an executive analytics board.  
**Tabs:** My work · My cases · Evidence & tasks · Hearings.

| Primary card | Click destination | Readiness |
|---|---|---|
| My active cases | Assigned active-case list | E/W: align lifecycle |
| My tasks due today | Today's actionable task list | W: due-date aggregate |
| My overdue tasks | Uncompleted tasks past due | W |
| Hearings in next 7 days | Assigned-case hearing calendar | W: extend beyond current next-date summary |
| Evidence requests overdue | Assigned evidence dependency list | W |
| Reviews/returns awaiting my action | Supervisor requests requiring a response | W |

**Overview widgets:** a prioritised task list, hearing/deadline calendar, case-stage summary and recent case activity. Two compact analytical views are enough; reserve space for work, not dashboard decoration.

**Detailed analytics:** per-case evidence completeness against an explicit checklist, source-linked case timeline, documented person/device/account relationships and permitted case-specific money trails. Show reasons, source records and uncertainty. Do not rank people as dangerous based on centrality or appearance.

**Lead investigator actions:** authorised case updates, evidence/statement submission, lead documentation and requests for supervisory review. No self-approval of a workflow requiring independent review.

**Case assistant actions:** assigned tasks and permitted evidence submissions only. A non-lead seat cannot be selected as the lead investigator or inherit case-closing powers because it shares this dashboard.

**Hide:** colleagues' case lists, station rankings, district forecasting, statewide maps, executive outcomes charts, mass person/face search and platform controls.

### 4.7 System Admin

**Purpose:** maintain a reliable service, correct access and trustworthy data pipelines.  
**Scope:** platform operational metadata. System administration is not an automatic investigative entitlement.  
**Tabs:** Service health · Seats & roles · Data pipelines · Models & governance · Audit.

| Primary card | Click destination | Readiness |
|---|---|---|
| Service availability — 24h | Availability history and affected services | N |
| API latency P95 | Endpoint latency distribution and trace summary | N |
| Failed jobs needing action | Retryable/terminal job failures | W/N |
| Feeds outside freshness target | Source watermarks and lag | W |
| Seats with unresolved/invalid posting | Seat remediation queue | W |
| Critical access/configuration alerts | Access-change and configuration review queue | W/N |

**Overview graphs/widgets:** latency/error time series; job backlog by state; data freshness matrix; actionable incident queue. Technical counts such as model versions or UI overrides belong on their corresponding administration tabs.

**Detailed analytics:** grant changes; active/deactivated seats; orphaned role/scope anchors; ingestion rejection reasons; dead-letter queue; resource consumption and budget; backup/restore evidence; model version health, drift, calibration and abstention. Read access to governance reports and authority to approve a model release are separate grants.

**Actions:** manage seats and role definitions, repair configurations, investigate jobs, manage versioned UI presets and execute controlled recovery. Use a separate business-approved role/seat for operational case inspection. Emergency support access, if required, must be time-limited and audited.

**Hide:** accused galleries, case narratives, raw evidence and investigative maps by default; operational approvals do not become admin powers merely for convenience.

## 5. Shared analytics visibility matrix

**A:** aggregates only. **S:** scoped detail, subject to capability. **C:** assigned-case context only. **G:** separate approved entitlement; not enabled by default. **—:** hidden. Every entry remains subject to organisational scope.

| Module | DGP | Wing | Range | SP/CP | SHO | IO/assistant | Admin |
|---|---|---|---|---|---|---|---|
| Demand trends and category composition | A | A, own heads | A | A | A, station | C summary | — |
| Geographic incident maps | A | A, own heads | A / G detail | S | S, station only | C | — |
| District-grain demand forecasts | A | A, supported heads | A | A | — | — | G model health only |
| Workload/capacity analytics | A | A, valid wing denominator | A | S | S | Own work only | Service capacity only |
| Court outcome cohorts | A | A, applicable wings | A | A | Case status only | C | — |
| Case files, parties and evidence | — | — | G | S | S | C | G support exception |
| Investigation board / named graph | — | — | G | G | G | C + G | — |
| Account/transaction detail | — | — | G | G | G | C + G | — |
| Socioeconomic research | G, aggregate | G, principally CTS | G, valid samples | G, valid samples | — | — | — |
| CCTV event operations | A readiness | A if relevant | A | G | G within station | C evidence links | Device health/config G |
| Face/identity evidence tools | — | — | — by default | G, case-specific | G, case-specific | C + G | Technical job health only |
| Emergency readiness | A | A when relevant | A | S | S for assigned resources | Assigned tasks | Platform health |
| Model evaluation / drift | Summary | CTS specialist | Read-only summary | Read-only availability | — | — | G |
| Data-quality queues | A | A, own heads | A | S | S, station | C corrections | Platform/source quality |
| Aggregate exports | A | A | A | A | A, station | Own-work summary | Platform reports |
| Case-data exports | — | — | G | G | G | C + G | — by default |
| Ask DRISHTI | A answers | A answers | Scoped | Scoped | Scoped | C | Admin-domain answers |

No chart, download, map tooltip, search suggestion or natural-language response may exceed the same permissions as the underlying records. An AI-generated answer must not bypass a hidden/forbidden module through SQL, retrieval, tool calls or exports.

### CCTV and emergency sub-dashboards

The current CCTV service exposes camera health, pending reviews, confirmed alerts awaiting dispatch and active dispatch counts. Reuse these as a separate **Incident Response** workspace for authorised SP/CP/SHO users, not an always-visible state camera wall.

- Primary cards: pending event reviews; confirmed incidents awaiting dispatch; active dispatches; overdue response actions; available responders; offline/degraded cameras.
- Graphs: event counts by class/time; confirmation/dismissal outcomes; dispatch-stage ageing; response median/P90 by confirmed event class.
- Label model detections as unreviewed until a human review is recorded. A detection count is not a crime count; a candidate identity match is not a confirmed identity.
- Resource allocation requires current availability and verified locations. Estimated travel time and measured response time are separate fields.
- Emergency workspace: active incidents, resource shortfalls, pending approvals, dispatch state, shelter/resource status where populated, and a scoped situation map. Hide absent data feeds rather than fabricating readiness.

Keep synthetic portraits and synthetic evidence visibly marked in demo mode. They must not become identity ground truth, performance-evaluation truth or a source of “criminals detected” KPIs.

## 6. Metric contracts—the numbers must mean the same thing everywhere

These are **target definitions**. Reconcile them with existing services before binding production cards. Do not silently change an existing API's meaning while retaining the old metric/version identifier.

| Metric | Required definition and safeguards |
|---|---|
| New FIRs | `COUNT(DISTINCT case_id)` where registration time is in `[start, end)` and the case is analytics-eligible and in scope. Count canonical case records, not joined party rows. |
| Recorded incidents | Use a separately defined canonical incident ID if multiple FIRs can refer to one incident. Until then, label the case-based count “registered cases/FIRs,” not uniquely deduplicated incidents. |
| Active investigations | Snapshot count in approved investigation-active states. Exclude pending-trial-only and finally closed cases; show missing/unmapped states separately. |
| Open legal matters | Broader snapshot including eligible pending trial matters. Keep distinct from active investigative workload. |
| Reviews overdue | Required review with `due_at < as_of` and no valid completion/cancellation. A 90-day-old case is “open over 90 days,” not automatically a missed statutory deadline. |
| Unassigned investigations | Active cases requiring a lead investigator, with no currently valid eligible assignment. Validate assignment dates and `is_lead_investigator`. |
| Intake pending | Submitted drafts awaiting review; exclude drafts still being edited, returned drafts and final decisions. |
| Upcoming deadlines / hearings | Outstanding scheduled items in `[as_of, as_of + 7 days)`, excluding completed/cancelled/superseded schedules. Counts are items, with unique affected case count alongside. |
| Evidence overdue | Required evidence tasks/requests with an explicit due date past and incomplete state. Do not count every evidence object as pending. |
| Personal tasks | Count tasks owned by the actor within permitted case scope. Today, overdue and awaiting-response states must be disjoint or clearly explain overlap. |
| Critical escalations | Distinct unresolved, reviewed escalation records at configured critical severity; exclude dismissed/duplicate alerts. Keep machine proposals separate. |
| Station workload | Active investigations divided by eligible available lead-investigator FTE for that station. If FTE is absent, show raw counts and missing denominator; do not invent capacity. |
| Stations above capacity | Number above a versioned threshold, with threshold owner, case mix and denominator coverage. Current demo threshold “15 open cases per officer” is not a universal production staffing standard. |
| P90 workload | Percentile over the declared station or officer population. Label which population; never substitute maximum/median and call it P90. |
| Median filing duration | Median registration-to-first-valid-chargesheet duration among cases filed in the selected period, with count and P90. It excludes unfinished cases, so show outstanding backlog alongside. |
| Filing throughput ratio | Filings during window / registrations during window. Different cohorts; can exceed 100%. Label as throughput, not clearance probability. |
| Final disposal | Valid final disposition event during the period, distinct from filing a chargesheet. Publish treatment of reopened/transferred/duplicate cases. |
| Conviction share | Convicted case verdicts / (convicted + acquitted case verdicts) for a declared cohort, with both counts. Mixed outcomes, appeals and multiple defendants need explicit handling; exclude unknown outcomes rather than guessing. |
| Response time | Recorded on-scene arrival minus a specified incident clock start (e.g. confirmation); publish the start event in the title/help. Median and P90 over completed responses, with pending count and timestamp coverage. |
| Forecast WAPE | `sum(abs(actual - predicted)) / sum(actual)` on a declared held-out cohort. Undefined if the denominator is zero. Include horizon, grain, model/version and evaluation period. |
| Interval coverage | Share of held-out actuals inside a stated nominal interval (e.g. 80%). Compare with its nominal target; higher is not always better. |
| Source freshness | Current clock minus last successful source watermark, with source-specific target. Latest case registration is not a general ingestion-health measure. |
| API availability / P95 | Defined eligible success/attempt population and duration observations for the window; publish exclusions. Use operational telemetry rather than the number of registered API routes. |
| Failed jobs | Unresolved failed executions requiring action, grouped by workflow and failure class. Retries must not multiply one incident into many headline failures. |
| Invalid seats | Active seats with missing/invalid organisational anchors or incompatible role/scope; distinguish this from all provisioned users. |
| Access/configuration alerts | Unresolved events meeting an explicit severity policy; routine administrative changes are not automatically critical. |

For all rate metrics: publish numerator, denominator, missing/excluded count, unit and sample size. Return null/reason for undefined ratios. Use configurable small-sample suppression; include controls against reconstructing suppressed values from adjacent totals. Do not sum overlapping wing totals to obtain state totals.

Socioeconomic panels must show sample size, time alignment, missingness, uncertainty and multiple-comparison limitations. Correlation is exploratory, not evidence that a demographic group or a person causes crime. Do not convert it into individual criminality scores or automatic enforcement recommendations.

## 7. Backend and frontend implementation contract

### 7.1 Access and visibility

Apply this intersection consistently:

```text
visible module = approved board preset
               ∩ granted capability
               ∩ valid organisational/case scope
               ∩ valid metric grain and wing applicability
               ∩ enabled, ready data source
               ∩ admin presentation settings
```

The server must enforce capability and object scope independently of the visible module. Missing/invalid scope fails closed. Custom-role and posting changes invalidate cached permissions and results. Public demo seat selection must not be a production identity mechanism.

Use authenticated server-derived identity, deny-by-default policies and checks on every request—including exports and image/evidence retrieval. This follows the [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Organisation attributes and case assignments supplement the role; a role string alone is insufficient.

Implement audit records for permission changes, sensitive record access, exports and operational approvals. A settings toggle can hide a widget but cannot grant a forbidden endpoint. Preserve state/wing aggregate-only rules even when an administrator customises a board.

### 7.2 Metric response envelope

Use a shared typed contract for every KPI and chart; endpoint names below are proposed, not existing APIs:

```json
{
  "metric_id": "active_investigations",
  "definition_version": "1",
  "status": "ok",
  "value": 120,
  "unit": "cases",
  "time_basis": "snapshot",
  "window": {"start": null, "end": null},
  "as_of": "2026-09-07T00:00:00Z",
  "snapshot_id": "example-snapshot",
  "scope": {"type": "station", "unit_id": 123},
  "grain": "station",
  "sample_size": 120,
  "missing_count": 0,
  "comparison": null,
  "freshness": {"state": "fresh", "watermark": "2026-09-07T00:00:00Z"},
  "provenance": {"source": "canonical-case-snapshot", "dataset": "synthetic"},
  "drilldown": {"kind": "case_list", "filter_token": "server-issued-example"},
  "limitations": []
}
```

The numbers above illustrate the contract; they are not project measurements. A drill-down token binds metric, window and scope, and must be reauthorised when used. An aggregate-only response never returns a case-list drill-down or hidden row-level payload.

### 7.3 Source and code mapping

| Implementation area | Existing foundation | Work required |
|---|---|---|
| Role / board selection | `roles.ts`, `roles.py`, `roleBoards.ts` | Six explicit primary cards per profile; wing presets; lead/assistant action differences; custom-role capability composition |
| KPI definitions | `config/kpi/registry.ts` | Add time basis, metric version, neutral/target-based polarity, source readiness, required capability and accepted grains |
| KPI loading | `useKpiValues.tsx`, dashboard hooks | Only fetch required authorised datasets; complete missing bindings; cancel and clear queries on seat change |
| Workload | `/performance/overview`, district performance and dashboard rollups | Reconcile lifecycle; common snapshots; real staffing denominators; due-date reviews rather than age proxies |
| Case stages | `/cases/caseload`, casework services | Shared state dictionary and precise active-investigation versus legal-open measures |
| Outcomes | `/outcomes/overview` | Explicit cohorts, mixed/reopened outcomes and sample-size protections |
| Maps / forecasts | `/geo/trends`, `/geo/hotspots`, `/forecast/map`, `/forecast/backtest` | Server scope for every series/total; no false station forecast; uncertainty and availability; aggregate-only map payloads |
| Intake / evidence | Intake and casework modules | Dedicated pending/overdue aggregates and navigation contracts |
| Tasks / hearings | `/notifications/tasks`, `/casework/hearings/next` | Actor-and-case scoped due-date summaries; next-seven-day counts and cancellation handling |
| Specialist analytics | Money, graph, identity, analytics services | Wing-specific aggregate endpoints; do not feed aggregate seats from raw PII responses |
| CCTV | `/cctv/overview`, alerts, dispatch, activity | Reviewed-event metrics, authorised scope, timestamp coverage and response distributions |
| Admin | Admin console, org seats, role grants/UI settings | Bind existing administration KPIs; add service telemetry, feed watermarks and job incidents |
| Natural-language analysis | Ask/SQL/retrieval tools | Same permissions, aggregates, suppression and source traceability as the direct UI |

Cache keys must include the resolved scope/assignment version, capabilities version, analysis filters and snapshot. Never reuse state-wide cached data for a station or IO seat. Drill-downs and exports must share the same metric filters and snapshot semantics.

Use pre-aggregations for high-level boards and paginated scoped queries for operational detail. Do not issue a forecast run or costly model job simply because a dashboard opened. Do not use the first 25 returned stations, top 12 entities or a capped pattern list to calculate an all-scope KPI.

## 8. Production appearance and operational targets

These are proposed acceptance targets to measure, not current performance claims:

| Area | Proposed acceptance target |
|---|---|
| Overview density | Six primary cards; at most four analytical/operational widgets; deeper analysis on tabs |
| Loading | Show context immediately; aim for cached overview data within 2 seconds P95 and uncached within 5 seconds under an agreed concurrency/data-size test |
| Freshness | Operational queues refreshed within 60 seconds where live sources support it; analytical rollups within 15 minutes; disclose exceptions |
| Consistency | KPI total and drill-down reconcile on the same snapshot; explain any intentionally different cohort |
| Accessibility | Keyboard navigation, labelled controls, chart/table alternatives, readable contrast and no colour-only alerts |
| Responsive layout | Primary cards: 3 columns on standard desktop, 2 on tablet, 1 on narrow screens; tables use deliberate horizontal scrolling |
| Reliability | One failed module does not blank the page; retry and last-success timestamps per module |
| Exports | Authorised, scoped, audited; include filter window, as-of date, definitions and synthetic/source labels |
| Presentation | Consistent units and date formatting; readable titles; no random decorative graphs or gauges without real targets |

On executive screens, use “District comparison” or “Workload distribution,” not “Top criminals,” “Worst officers” or a single opaque performance score. A forecast describes aggregate demand, not the guilt or future behaviour of a named person.

## 9. Delivery sequence

| Stage | Scope | Completion gate |
|---|---|---|
| P0 — Definitions and access | Confirm lifecycle dictionary, capability matrix, snapshot clock, scope rules and metric contracts | Written metric definitions agreed; deny/scope tests pass; no hidden broad-data fetches |
| P1 — Operational core | IO/assistant, SHO and SP/CP boards; tasks, intake, assignments, evidence and hearings | Each card has a correct endpoint and actionable scoped destination; no nine unbound cards presented as working |
| P2 — Command analytics | Range, DGP and six wing presets; validated aggregates, comparisons and forecasts | All primary boards use explicit presets; correct denominators/grains; no raw personal data on state/wing boards |
| P3 — Live response and platform | CCTV event operations, emergency readiness, service telemetry and data pipelines | Timestamp/coverage checks, human review transitions, scoped operational grants and observable failures |
| P4 — Release validation | Accessibility, realistic load, export controls, recovery and role-switch testing | Evidence meets the acceptance tests below; deployment cannot advertise production readiness from UI polish alone |

A demonstration can use synthetic, explicitly labelled snapshots before live integrations are ready. Keep unavailable modules out of the default board; an admin diagnostics page may list planned/unbound modules. Do not fill missing cards with fabricated values.

## 10. Acceptance tests

1. **Six-role inventory:** code, gateway and database role mappings agree; legacy aliases do not create extra roles or widen scope.
2. **Eight profiles:** state, wing, range, district, commissionerate, station, assigned-case and platform each render the intended six primary cards. All six wing presets are exercised.
3. **Unposted seat:** sees no operational figures; API denies out-of-scope data rather than treating missing anchors as statewide access.
4. **State/wing privacy:** direct case APIs, graph details, map points, image URLs, exports and Ask responses cannot reveal individual cases/people.
5. **IO isolation:** two officers in the same station cannot see one another's unassigned case work; assignment revocation takes effect after cache invalidation.
6. **Assistant restrictions:** case assistants can complete allowed tasks but cannot become lead IO or inherit supervisory approval actions.
7. **SP/CP/range boundaries:** manipulated IDs and direct URLs cannot escape the allowed district/station set; changing a filter cannot widen a wing's crime-head scope.
8. **Admin separation:** platform permissions do not automatically grant case content, raw camera footage or investigative approvals.
9. **Window honesty:** live clock versus historical snapshot is visible; partial-period comparisons and stale data do not masquerade as full, current measurements.
10. **Lifecycle reconciliation:** active investigations, trial matters, filings and final dispositions reconcile to the published dictionary, including transfers and reopening.
11. **Metric arithmetic:** test null denominators, no cases, one case, duplicate joined rows, no staffing data, zero forecast actuals and overlapping wing scopes.
12. **Uncapped totals:** headline counts remain correct when detail lists are paginated or capped.
13. **Scope/grain honesty:** station dashboards never label district aggregates as station predictions/hotspots; global model metrics ignore neither their labels nor context.
14. **No hidden requests:** a disabled/unauthorised specialist module makes no broad query; changing roles clears old results from the UI and cache.
15. **Operational correctness:** proposed detection → human review → approved response transitions are distinct and auditable; response metrics reject missing/negative timestamps.
16. **UI resilience:** error, stale, empty, suppressed and unavailable states remain distinct; card drill-downs and filters work using a keyboard.
17. **Exports/AI:** output obeys scope and suppression, includes provenance, and does not expose data omitted from the corresponding UI.
18. **Load and recovery:** measure the agreed P95 targets and demonstrate a failed-job retry/restore path with evidence. Do not claim a passed test without running it.

## 11. Evidence and review notes

Primary project sources inspected:

- [Frontend roles and capability helper](C:/Users/Prajwal/Desktop/DRISHTI/web/src/config/roles.ts)
- [Backend canonical role definitions](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/roles.py)
- [Scope derivation and aggregate-only rules](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/org/scope.py)
- [Current scope-based board presets](C:/Users/Prajwal/Desktop/DRISHTI/web/src/config/kpi/roleBoards.ts)
- [50-card KPI registry](C:/Users/Prajwal/Desktop/DRISHTI/web/src/config/kpi/registry.ts)
- [KPI data resolver and pending fallback](C:/Users/Prajwal/Desktop/DRISHTI/web/src/routes/home/useKpiValues.tsx)
- [Dashboard widgets, including district-grain map notes](C:/Users/Prajwal/Desktop/DRISHTI/web/src/routes/home/boardWidgets.tsx)
- [Current workload formulas and demo thresholds](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/performance/service.py)
- [Court outcome response contract](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/outcomes/schemas.py)
- [CCTV overview, review and dispatch schemas](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/cctv/schemas.py)
- [Custom-role and permission-catalogue migration](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/sql/035_custom_roles.sql)
- [Admin role/grant service](C:/Users/Prajwal/Desktop/DRISHTI/services/ml/app/admin_console/service.py)
- [Earlier role-scoped plan](C:/Users/Prajwal/Desktop/DRISHTI/docs/role-scoped-command-plan.md)

Database verification used a read-only join of `roles` and `users`, grouped by `roles.role_id`, plus user counts by `scope_type`. It did not validate the entire application, all endpoints, live integrations or the operational validity of each seat. The current working tree contains ongoing changes; repeat the inventory before implementation and reconcile newer changes rather than overwriting them.

**Recommended implementation starting point:** establish the metric/access contracts, then build the IO → SHO → SP/CP workflow first. Those boards provide the work and review data that higher-command analytics depend on.
