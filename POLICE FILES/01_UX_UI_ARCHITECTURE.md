# 01 — UX / UI Architecture
### The complete placement of every page, sub-page, panel and widget

> This document is the blueprint an engineer or designer can build directly from. It defines the design language, the app shell, all eight destinations with their sub-pages and layouts, the widget taxonomy that makes each data type instantly legible, where officers *add* data, the role-based views, and the interaction patterns that make DRISHTI feel a decade ahead. Companion clickable screens: **[mockups/index.html](mockups/index.html)**.

---

## 1. Design philosophy — five laws

Everything below is downstream of these five laws. When two ideas conflict, the earlier law wins.

1. **One panel, one idea.** A widget shows a single, nameable thing. If you cannot say what a panel is *for* in five words, it is two panels.
2. **The data type chooses the visual.** A count is never a line chart; a relationship is never a table; a place is always a map. This mapping is fixed and documented (§5) so the whole product feels coherent and every chart is understood at a glance.
3. **Progressive disclosure, AWS-style.** The top level is shallow and calm (8 items). Depth is reached by *drilling into an object*, where a local sub-navigation appears — not by hunting through nested menus. You are never more than: *destination → object → sub-page*.
4. **Show provenance, always.** Every derived number wears a small confidence/⌄ source affordance. Trust is the product.
5. **Act where you look.** The action that belongs to a piece of data lives next to that data. The IO adds evidence on the Evidence sub-page, not in a separate "data entry" module.

---

## 2. The design system — "Calm Authority"

The aesthetic target: a modern **operations room** — serious, precise, quiet. Not a consumer app, not a 1990s government portal. Reference points to study (layout only, don't lift assets): Palantir Gotham's object panels, Linear's density and keyboard-first feel, Perplexity's inline-citation pattern.

### 2.1 Colour
Two themes ship day one. **Ops Mode (dark)** is the default for map/network/alert work and control rooms; **Desk Mode (light)** for daytime paperwork and report reading. Both are built from the same tokens.

| Token | Ops (dark) | Desk (light) | Use |
|---|---|---|---|
| `--bg` | `#0B1020` | `#F7F8FB` | app background |
| `--surface` | `#141B2E` | `#FFFFFF` | cards, panels |
| `--surface-2` | `#1D2740` | `#EEF1F7` | insets, hovers |
| `--border` | `#28324D` | `#DCE1EC` | hairlines |
| `--text` | `#E8ECF6` | `#141B2E` | primary text |
| `--text-dim` | `#94A0BD` | `#5A6478` | secondary text |
| `--primary` | `#3B82F6` (KSP indigo-blue) | same | primary actions, links |
| `--accent` | `#12B981` | same | positive / verified |

**Semantic colours are reserved and never decorative:**

| Meaning | Colour | Where |
|---|---|---|
| Severity — critical / high / med / low | `#EF4444` / `#F59E0B` / `#EAB308` / `#22C55E` | alerts, gravity, risk |
| Confidence | encoded as **opacity + a small solid/hatched bar**, not hue | every AI output |
| Crime category | one fixed categorical palette (12 hues), defined once | charts, map points, legends |

> Colour-blind safety: severity is *always* paired with an icon and a label, never colour alone (law 2 + accessibility, §9).

### 2.2 Type & number
- **Inter** (or IBM Plex Sans) for UI. Clear at small sizes, neutral, multilingual.
- **Noto Sans Kannada** for Kannada — full script coverage, matches Inter's tone.
- **Tabular (monospaced) numerals everywhere numbers align** — tables, KPIs, money trails. Numbers must never jitter as they update.
- A tight, deliberate scale: `12 / 13 / 14 / 16 / 20 / 28 / 36`. Body is 14; data-dense tables 13.

### 2.3 Spacing, density, motion
- **8-pt grid.** Card padding 16/20; section gaps 24.
- **Two density modes** (user toggle, remembered): *Comfortable* (default) and *Compact* (−25% vertical rhythm, for analysts on big monitors).
- **Motion is informative, never ornamental.** 150–200 ms ease for state changes. The only *looping* animation in the entire product is the **red-zone pulse** on active-alert map markers — because a pulse means "attention, now."
- **Radius** 10 px on cards, 8 px on controls. Soft, not playful.

### 2.4 The universal widget frame
Every widget — chart, map, table, graph — sits in the same frame so the eye always knows where to look:

```
┌─────────────────────────────────────────────┐
│ Title            [context chip]     ⓘ  ⋯  ⤢ │  ← name · scope (e.g. "Mysuru · 30d") · info · menu · expand
├─────────────────────────────────────────────┤
│                                               │
│          the single visual                    │
│                                               │
├─────────────────────────────────────────────┤
│ ⌄ 1,204 records · TabFM v2 · 87% conf         │  ← provenance strip (only if derived)
└─────────────────────────────────────────────┘
```

The provenance strip is the physical embodiment of Law 4 and of Phase 13. Clicking `⌄` opens the Evidence Trail (see §6.9).

---

## 3. The app shell — anatomy of every screen

```
┌──────┬───────────────────────────────────────────────────────────────┐
│      │  TOP BAR:  ⌘K Ask DRISHTI …………   [global time-scrubber]   🌗  🔔  👤 │
│  S   ├───────────────────────────────────────────────────────────────┤
│  I   │  Breadcrumb:  Cases › FIR 104430006202600001 › Network          │
│  D   ├──────────────────────────┬────────────────────────────────────┤
│  E   │                          │                                     │
│  B   │   SUB-NAV (per object,   │   WORKSPACE                         │
│  A   │   AWS-style, appears     │   (the page content —               │
│  R   │   only inside a          │    widgets on the grid)             │
│  (8) │   destination)           │                                     │
│      │                          │                          ┌────────┐ │
│      │                          │                          │ PEEK / │ │
│      │                          │                          │ CONTEXT│ │
│      │                          │                          │ RAIL   │ │
│      │                          │                          └────────┘ │
└──────┴──────────────────────────┴────────────────────────────────────┘
```

- **Left sidebar (icon + label, collapsible to icons):** the 8 destinations. This is the *only* primary navigation. It never grows.
- **Top bar:** the **⌘K command bar** (Ask DRISHTI from anywhere — type or 🎙 speak), the **global time-scrubber** (§8.3), theme toggle, notifications (live alerts), profile/role.
- **Breadcrumb:** the object-centric trail. This is how you know where you are; it replaces deep menus.
- **Sub-nav:** appears *inside* a destination when you open an object (a case, an entity). This is the AWS pattern — the case file's own left rail of sub-pages.
- **Peek / context rail (right):** a slide-over that shows the *selected* object without leaving the current page (§8.2). Dismissible; never mandatory.

---

## 4. The eight destinations in full

For each destination: its **landing page**, its **sub-pages**, the **widgets** on each, the **actions** available, and the **role gating**.

---

### 4.1 · Command Center  🏠  *(role-adaptive home)*

The first screen after login. **It is a different screen for each role** (§7) — assembled from a shared widget library, arranged to that role's job. No sub-nav; it *is* the overview.

**Investigator layout (example):**

| Zone | Widget | Type (see §5) |
|---|---|---|
| Hero left | **My caseload** — open cases, status pipeline | status-pipeline + count |
| Hero right | **My jurisdiction map** — my station's incidents (last 30d) | geo point-density |
| Band | 4 KPI cards: New FIRs · Pending chargesheets · Arrests this week · My alerts | KPI stat cards |
| Row | **Attention queue** — alerts & leads assigned to me, newest first | event list |
| Row | **Recent activity** — cases I touched, resume where I left off | list |

**Supervisor** swaps the caseload for **station/officer performance** and a **review queue**; **Policymaker** sees only **district-aggregate KPIs, trends and forecasts** (no case list, no map pins finer than district choropleth); **Analyst** gets **saved cohorts, the emerging-trend feed, and a network-of-interest shortcut**.

- **Actions:** jump into any item; pin a widget; "Ask DRISHTI about this."
- **Roles:** all (content differs).

---

### 4.2 · Cases  📁  *(the object-centric case file — Phases 2, 7, 10, 13)*

**Landing = Case Explorer.** A fast, filterable index of FIRs — *not* a raw table dump.

- **Left filter rail:** district, station, crime head/sub-head, status, gravity, date range, act/section, "has arrest", "has chargesheet". Filters compose into a **saved view / lens** (§8.4).
- **Main:** results as a **dense but calm table** (13-px tabular numerals) with a **map/table toggle** — the same result set as pins when you think spatially.
- **Semantic search bar:** "cases like this MO" runs pgvector similarity, not keyword (Phase 10).
- **Actions:** open case · export view · save lens · "Register new FIR" (role-gated to IO).

**Open a case → the AWS-style case file with sub-nav:**

| Sub-page | What's on it | Key widgets | Add-data action |
|---|---|---|---|
| **Overview** | The FIR at a glance: crime no., IPC/act-sections, gravity, status, brief facts, location mini-map, key people chips | summary card · mini-map · people chips | edit status (IO) |
| **Timeline** | Every event on the case in order: registered → incident window → arrests → chargesheet → court | horizontal event timeline | add note/event (IO) |
| **Complainant** | `ComplainantDetails` | identity card | edit (IO) |
| **Victims** | `Victim` rows | person cards | **+ Add victim** (IO) |
| **Accused** | `Accused` rows, each linking to its People profile | person cards + link | **+ Add accused** (IO) |
| **Acts & Sections** | `ActSectionAssociation` in print order | ordered list | edit charges (IO) |
| **Arrests** | `ArrestSurrender` + `inv_arrestsurrenderaccused` | timeline + cards | **+ Record arrest** (IO) |
| **Chargesheet** | `ChargesheetDetails`, cstype (A/B/C) | doc card | **+ File chargesheet** (IO) |
| **Evidence** | attachments, seizures, notes | evidence gallery/list | **+ Add evidence** (IO) — the canonical "act where you look" |
| **Network** | this case's mini-graph — co-accused, shared locations, linked cases | node-link (embedded) | promote edge → alert (analyst) |
| **Similar cases** | top-5 by embedding similarity + their outcomes | ranked similarity list | — |
| **AI Summary** | LLM summary + timeline, every claim cited to a record ID | citation-annotated text | regenerate |
| **Leads** | ranked next steps with the evidence behind each (suggestions, not orders) | ranked recommendation cards | accept/assign lead |
| **Evidence Trail** | the explainability panel for everything AI touched on this case | provenance chain | — |

- **Roles:** IO (full + write on own/assigned cases), Analyst (read + network/similar), Supervisor (read all in jurisdiction + reassign), Policymaker (**no access to individual case file**).

---

### 4.3 · People & Entities  👤  *(the object explorer — Phase 9)*

**Landing = Entity Explorer.** Search/browse people, gangs, vehicles, phones, accounts — anything that is a node in `EntityGraph`. Faceted by entity type, district, "has risk score", "gang-affiliated".

**Open an entity → profile with sub-nav** (CRM-contact pattern, applied to an offender):

| Sub-page | Content | Key widgets |
|---|---|---|
| **Identity** | name, aliases, demographics, IDs, photo slot | header summary card |
| **Criminal History** | every linked case, chronological, with role (accused/victim) | event timeline + case list |
| **Network** | this entity's connected subgraph to N hops | node-link (see §4.4) |
| **Risk (TabFM)** | current risk score, level, and the **factor breakdown** driving it | gauge + factor bars (SHAP-style) |
| **MO Cluster** | which modus-operandi cluster they fall in, co-members | cluster card + member chips |
| **Cases** | the raw linked-case table | table |
| **Financial** | linked accounts & flagged transactions *(permission-gated)* | money-flow mini-graph |
| **Locations** | places associated with this entity | geo point map |
| **Evidence Trail** | provenance for the risk score & associations | provenance chain |

- **Actions:** add to a cohort · open in Network canvas · "Ask DRISHTI about this person" · flag for review.
- **Roles:** IO/Analyst/Supervisor read; **Financial** sub-page requires financial-data permission; Policymaker **cannot open individual profiles** (would be de-anonymizing).

---

### 4.4 · Network Analysis  🕸  *(link analysis — Phases 6 & 11)*

The destination that most says "Palantir." A full-canvas link-analysis workspace. Sub-nav switches *modes* over the same graph:

| Sub-page (mode) | Purpose | Interaction |
|---|---|---|
| **Explore** | free-form canvas: drop an entity, expand neighbours hop-by-hop | click node → expand · pin · lasso-select · layout switch (force / hierarchical / geo) |
| **Communities** | Louvain/Leiden clusters coloured as groups; cross-referenced with `GangMembership` | click cluster → member list, shared attributes |
| **Hidden Associations** | **the headline feature** — auto-surfaced pairs sharing ≥2 indirect links (same address *and* account) who never co-appear in a FIR | ranked "association cards", each opening the proof-path on the canvas |
| **Money Trail** | financial graph: accounts as nodes, transactions as weighted directed edges; structuring/layering/circular flags | Sankey + path-trace, max-hops slider |
| **Path Finder** | shortest/all paths between two selected entities (pgRouting / GDS) | pick A + B → animated path(s) |

- **Left rail:** filters (entity types, edge types, min edge weight, time window via the global scrubber), layout, "explain this cluster."
- **Right peek:** selected node/edge details + jump to its full profile.
- **Actions:** save graph as a board (§8.1) · export PNG/JSON · promote a finding to an alert · send to a case.
- **Roles:** Analyst/IO/Supervisor; **Money Trail** gated on financial permission; Policymaker no access.
- Full engine design → [04 — Network / Graph Analysis](04_NETWORK_GRAPH_ANALYSIS.md); node/edge visual encoding → [03 §4](03_DATA_VISUALIZATION.md).

---

### 4.5 · Map & Hotspots  🗺  *(geospatial operations — Phases 7 & 12)*

Full-bleed map (deck.gl/kepler.gl). Sub-nav switches the **layer + intent**:

| Sub-page | Layer | Widgets / controls |
|---|---|---|
| **Live Map** | current incidents, clustered; drill **district → station → point** | hexbin/cluster · layer toggles · legend |
| **Hotspots** | KDE / DBSCAN density surface from `CrimeHotspot` | heat surface · intensity legend · time-of-day filter |
| **Forecast** | next-period predicted risk per district/beat from `CrimePrediction` (TabFM) + spatio-temporal model | choropleth + confidence hatching · horizon selector |
| **Patrol Planning** | overlay beats/resources on hotspots & forecasts | editable beat layer · coverage gaps |
| **Red-Zone Alerts** | active `AlertHistory` items as **pulsing markers** | pulse markers · alert side-list · ack/assign |

- **The global time-scrubber (§8.3) is the star here:** drag it and incidents/hotspots animate through time.
- **Actions:** drill down · switch layer · ack/assign alert · "forecast for this district" · export map.
- **Roles:** all — but Policymaker is capped at **district choropleth** (no point-level pins that could identify a location/victim).
- Full method → [05 — Geospatial & Crime-Pattern Analytics](05_GEOSPATIAL_CRIME_ANALYTICS.md); map encoding → [03 §3](03_DATA_VISUALIZATION.md).

---

### 4.6 · Analytics & Forecasting  📊  *(intelligence dashboards — Phases 7, 8, 12)*

Dashboards for reading trends, not chasing a single case. Sub-nav:

| Sub-page | Content | Key widgets |
|---|---|---|
| **Trends** | crime volume by head/sub-head/district over time; MoM & YoY | time-series + delta KPIs |
| **Crime Patterns** | `CrimePattern` detections: serial, MO-match, spatial, temporal | pattern cards + linked-case lists |
| **Socio-Economic** | correlation of crime with `SocialIndicator`/`EconomicIndicator`/`WeatherIndicator`; **plain-language read-outs** ("districts with unemployment above X show Y% more property crime — correlational, not causal") | correlation matrix + scatter + narrative card |
| **Forecasts** | district/category forecasts, horizon & confidence; TabFM + TimesFM | forecast fan chart + table |
| **Model Explainability** | model registry view: which model, version, inputs, calibration, drift | model cards + calibration plot |

- **Actions:** change scope/period (or use the scrubber) · export chart/CSV · "explain this correlation" (hands the narrative to Ask DRISHTI) · open underlying records.
- **Roles:** Analyst/Supervisor/Policymaker (this is a policymaker's *home turf*); IO read.

---

### 4.7 · Ask DRISHTI  💬  *(conversational + voice — Phases 2, 3, 4, 5)*

The centerpiece feature, and also available as the ⌘K command bar everywhere (§8.5). The full destination is the *workspace* for longer investigative conversations.

**Layout:** a focused chat column (max-width, readable), not edge-to-edge.

- **Composer:** text input · 🎙 **voice** button (Web Speech API, English + Kannada) · **language toggle** (auto-detect default) · model/scope chips.
- **Each answer shows:**
  1. the natural-language reply (in the asked language),
  2. **inline numbered citations** (Perplexity-style) to the exact record IDs used,
  3. a collapsible **"SQL executed"** block (read-only, whitelisted SELECT — proof it's grounded), and
  4. a **confidence** chip.
- **Clarifying questions:** if a query is ambiguous ("which district?"), the assistant asks rather than guesses.
- **Multi-turn memory:** "show me *his* other cases" resolves from prior turns (`ChatSession`/`ChatMessage`).
- **Voice:** transcript + confidence stored in `VoiceTranscript`; low-confidence transcriptions are flagged; TTS reads answers back in the detected language. Latency handled by streaming the text answer while speech synthesizes.

**Sub-nav:** **Chat** (current) · **History** (past sessions, searchable) · **Saved Queries** (reusable prompts).

- **Actions:** 🎙 speak · switch language · **Export session → PDF** (Phase 5: header with session/case ID, investigator, timestamp; original + translated query, answer, citations; print-clean) · cite-to-case.
- **Roles:** all — but **results are scoped to the user's permissions** (the same NL query returns less to a policymaker than to an IO). This scoping is enforced server-side, not in the prompt.

---

### 4.8 · Admin & Governance  🛡  *(super_admin only — Phase 14)*

Hidden entirely from non-admins (the sidebar shows 7 items for them). Sub-nav:

| Sub-page | Content | Key widgets |
|---|---|---|
| **Roles & Permissions** | create/edit/delete **custom roles**; a **resource × action matrix** (read/write/none per table/feature) with a **diff view before save** | permission grid + diff |
| **Users** | create users, assign roles, deactivate, force password reset, **issue credentials** (invite link / initial password, must-change-on-first-login) | user table + inline actions |
| **Audit Logs** | searchable/filterable `audit_logs` — who did what, when, from where; **admin actions are the highest-sensitivity trail** | filterable log table + timeline |
| **Model Registry** | `ModelVersion` inventory: deployed models, versions, metrics, promote/retire | model cards |
| **Data Sources** | connections, sync status, extension health (PostGIS/pgvector/pgRouting) | status board |
| **System Health** | API/DB/ML latency, error rates, active sessions | ops KPIs |

- **Enforcement note (surfaced in-UI):** permissions here drive **dynamic RLS** on sensitive tables (`Victim`, `Accused`, `FinancialAccount`, `ComplainantDetails`) *and* app-layer middleware. A newly created role is enforced without a code change.
- **Roles:** super_admin only. Every action writes to `audit_logs`.

---

## 5. The widget taxonomy — data type → visual (Law 2, made concrete)

This is the table that keeps 40+ screens coherent and each data point self-explanatory. Full rationale and library mapping in [03 — Data Visualization](03_DATA_VISUALIZATION.md); this is the quick contract.

| # | Data shape | Widget | Never use | Example in DRISHTI |
|---|---|---|---|---|
| 1 | Single value + trend | **KPI stat card** + sparkline + Δ vs. prior | pie for one number | "New FIRs this week: 312 ▲6%" |
| 2 | Parts of a whole (few) | **horizontal bar** / **treemap** | 3-D pie | crime mix by head |
| 3 | Value over time | **line / area** + anomaly band | bar-per-day clutter | monthly theft trend |
| 4 | Events on a timeline | **horizontal event timeline** | table of dates | case lifecycle |
| 5 | Point locations | **map: hexbin / cluster / heat** | dots that overlap | incident density |
| 6 | Regions | **choropleth** | colored table | district crime rate |
| 7 | Relationships | **node-link graph** | adjacency table | co-accused network |
| 8 | Flows / money | **Sankey / directed weighted graph** | list of transfers | money trail |
| 9 | A score with drivers | **gauge + factor bars** (signed) | bare number | TabFM offender risk |
| 10 | Correlation | **scatter** + **correlation matrix heatmap** | two lines on one axis | crime vs. unemployment |
| 11 | Ranked similarity | **ranked list with similarity bar** | unranked cards | similar cases |
| 12 | Grounded prose | **citation-annotated text card** | plain paragraph | AI case summary |
| 13 | Process state | **status pipeline** (stepper) | status as text only | investigation stage |
| 14 | Comparison of items | **grouped bar / bullet** | overlapping lines | station A vs. B |
| 15 | Confidence/uncertainty | **hatching / opacity / fan chart** | hidden entirely | forecast bands |

---

## 6. Where officers *add* data (Law 5)

DRISHTI is not read-only intelligence; it is an operating system. Write actions are **inline, contextual, and permission-gated**, never a separate "forms" module.

| Write action | Where it lives | Who | Writes to |
|---|---|---|---|
| Register FIR | Cases → Explorer → "Register new FIR" | IO | `CaseMaster` (+children) |
| Add victim / accused / complainant | the matching case sub-page, `+ Add` | IO | `Victim`/`Accused`/`ComplainantDetails` |
| Record arrest | Case → Arrests → `+ Record arrest` | IO | `ArrestSurrender` (+junction) |
| File chargesheet | Case → Chargesheet → `+ File` | IO | `ChargesheetDetails` |
| **Add evidence** | Case → Evidence → `+ Add evidence` | IO | evidence store + note |
| Add timeline note | Case → Timeline → `+ Note` | IO | note/event |
| Promote finding → alert | Network / Map | Analyst | `AlertHistory` |
| Accept / assign lead | Case → Leads | IO/Supervisor | `OfficerRecommendation` status |
| Acknowledge alert | Map → Red-Zone; 🔔 | assigned officer | `AlertHistory` (status, ack) |
| Create role / user | Admin | super_admin | `roles`/`users` (+`audit_logs`) |

Every write is optimistic-UI with server confirmation, validated against the schema's constraints (e.g. the 18-digit CrimeNo format the trigger enforces), and — for governance-sensitive writes — audit-logged.

---

## 7. Role-adaptive shell (the same product, five faces)

The shell reads the user's role/permissions once at login and adapts three things:

1. **Sidebar composition** — admins see 8 items, others 7; a policymaker's "Cases" and "People" items are hidden or redirect to aggregate views.
2. **Command Center layout** — a different widget set per role (§4.1).
3. **Per-widget data scope** — the *same* widget shows jurisdiction-scoped data for an IO, district-aggregate for a policymaker. Scope is applied server-side (RLS + middleware), so the UI can trust what it receives.

| Capability | super_admin | investigator | analyst | supervisor | policymaker |
|---|:--:|:--:|:--:|:--:|:--:|
| Command Center | ✅ | ✅ own | ✅ | ✅ unit | ✅ aggregate |
| Case file (individual, PII) | ✅ | ✅ own/assigned | ⚪ read, limited PII | ✅ unit | ❌ |
| People profile (individual) | ✅ | ✅ | ⚪ | ✅ | ❌ |
| Network canvas | ✅ | ✅ | ✅ | ✅ | ❌ |
| Money Trail (financial) | ✅ | ⚪ assigned | ⚪ cleared | ⚪ | ❌ |
| Map — point level | ✅ | ✅ | ✅ | ✅ | ❌ district only |
| Analytics / Forecasts | ✅ | ⚪ read | ✅ | ✅ | ✅ |
| Ask DRISHTI | ✅ | ✅ scoped | ✅ scoped | ✅ scoped | ✅ aggregate-only |
| Admin & Governance | ✅ | ❌ | ❌ | ❌ | ❌ |

✅ full · ⚪ partial/conditional · ❌ none *(defaults; the Super Admin can define custom roles that differ — Phase 14).*

---

## 8. Ten out-of-the-box interaction patterns

These are the moves that separate DRISHTI from a CRUD dashboard. Each is feasible with the chosen OSS stack.

1. **The Investigation Board.** A freeform canvas (like a detective's cork-board, digital) where an officer *pins* objects — a person, a case, a map extract, a network cluster, a chat answer — and draws their own connections. It is the connective tissue between destinations: send anything to the board. Persisted per user/case.
2. **Peek panels.** Click any object reference *anywhere* (a name in a table, a node in a graph, a citation in a chat answer) and it opens in the right-side peek rail — full profile, without losing your place. Peek-within-peek breadcrumbs let you go deep and back out.
3. **The global time-scrubber.** One timeline in the top bar governs the *entire* workspace. Drag it and the map animates, the network shows only edges active in that window, the KPIs recompute. Time becomes a dimension you *hold in your hand*, not a filter you re-enter on each screen.
4. **Saved lenses / cohorts.** Any filter combination (a set of cases, a group of offenders, a district+crime-type+period) is saveable as a named "lens," shareable to a role, and re-openable across destinations. Analysts live in these.
5. **Provenance chips → Evidence Trail.** Every derived number has a `⌄` chip; expanding it reveals `{ answer, confidence, source_record_ids[], reasoning_summary, model_version }` — the Phase 13 contract, rendered as a readable chain with clickable source records.
6. **Command bar (⌘K) = Ask DRISHTI, everywhere.** Summon natural-language query/navigation from any screen. "Go to FIR …", "burglaries in Mysuru last month", "open the network for this gang." Type or speak. Results either answer inline or navigate you.
7. **Split-view compare.** Pin two objects side-by-side — two districts' trends, two offenders' networks, two time windows — for genuine comparison instead of tab-flipping.
8. **Focus mode.** Collapse sidebar, sub-nav, and rails to a single maximized workspace (map or graph) for deep work or a projector in the ops room. `F` toggles.
9. **"Explain this" is universal.** Any chart, cluster, correlation, or alert has an "explain" action that routes its context into Ask DRISHTI and returns a grounded, cited narrative — turning every visual into a conversation.
10. **Live alert ambient layer.** New `AlertHistory` items arrive over WebSocket: a subtle 🔔 count, and on the map a red-zone pulse. Never a modal that interrupts — attention is *offered*, not *forced* (except for a defined class of critical alerts, which do interrupt by design).

---

## 9. Accessibility & field-readiness

- **WCAG 2.2 AA as the target.** Contrast ≥ 4.5:1 for text (both themes tuned for it); focus-visible on every control; full keyboard operability (the product is keyboard-first anyway). *Full WCAG conformance requires manual testing with assistive tech and expert review — this is a design target, not a claim.*
- **Never colour alone.** Severity/status/confidence always pair colour with icon + label.
- **Kannada is first-class,** not an afterthought translation layer — layouts are tested with longer Kannada strings; the glossary of police/legal terms (FIR = ಎಫ್‌ಐಆರ್, accused = ಆರೋಪಿ, …) keeps domain terms correct.
- **Field conditions:** Ops (dark) mode for low light and control rooms; large touch targets for tablet use at a scene; graceful degradation when a browser lacks the Web Speech API (fall back to text).
- **Performance is UX:** WebGL rendering (deck.gl, sigma.js) so maps and graphs stay at 60 fps with large data; virtualized tables; server-side scoping so the client never over-fetches.

---

## 10. Security is part of the UX (loud callout)

The base and intelligence schemas currently ship with **Row-Level Security disabled** for development speed. On Supabase, disabling RLS means tables are reachable through the auto-generated API with default grants. **This is acceptable only on a private/trusted network and must not survive into any networked or production deployment.**

Before Wave D / Phase 14:
- Re-enable RLS on all sensitive tables (`Victim`, `Accused`, `ComplainantDetails`, `FinancialAccount`, and the intelligence tables that expose PII by inference).
- Drive those policies **dynamically from `role_permissions`** so a new custom role is enforced without code changes.
- Keep the **app-layer permission middleware** as a second gate behind RLS.
- Require **re-auth for PII-sensitive queries** (victim lookups, financial trails) and enforce token expiry.
- Ensure **Ask DRISHTI's NL→SQL runs under a restricted, read-only DB role** and that result scoping is server-side — a user must not be able to prompt their way past their permissions.

This is not a footnote. On a law-enforcement platform, the access model *is* the product.

---

*Previous: [← 00 Master Plan](00_MASTER_PLAN.md)  ·  Next: [02 Advanced Technology →](02_ADVANCED_TECHNOLOGY.md)*
