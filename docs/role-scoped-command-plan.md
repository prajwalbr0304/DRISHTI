# Role-scoped command views — production plan

Status: approved design, not yet implemented.
Scope: Karnataka Police deployment of DRISHTI.

Locked decisions (from review):

- Six application roles, with a `scope_type` discriminator carrying the variation.
- Six ADGP functional wings; seven geographic ranges; two Commissionerates outside the range hierarchy.
- 1,046 real seat rows plus an IO pool and one admin seat; searchable seat picker replaces the ten demo login cards.
- Crime Analyst, Cyber Cell and Traffic Command fold into wings. DySP/ACP deferred (no sub-division data).
- No authentication and no RLS in this phase. Scope is a presentation and query-filter concern only.
- Admin controls per-role UI visibility from the Admin dashboard via on/off switches.

---

## 0. Layered model — five separate concepts

These stay orthogonal. Collapsing any two is what produced `adgp_igp_range`, a single role trying to be both a functional ADGP seat and a geographic DIG seat.

| Concept | Question it answers | Where it lives | Example |
|---|---|---|---|
| **Rank** | What is the officer's establishment rank? | `Rank.RankName` via `Employee.RankID` | Additional Director General of Police |
| **Assignment** | What post do they hold? | `Designation.DesignationName` via `Employee.DesignationID` | Station House Officer |
| **Organizational unit** | Where are they posted? | `Wing` / `Range` / `District` / `Unit` | Internal Security & Cyber |
| **Scope** | How much data does the seat carry? | `users.scope_type` + one anchor | `wing`, anchored to `wing_id` |
| **Permission** | Which actions may they take? | `role_permissions` | `case_read`, `board_share` |

The **application role** is a sixth, derived concept, and it answers only one question: which UI surface to render. It is stored explicitly rather than computed, so ADGP and DIG can share `senior_command` while differing entirely in scope.

Two consequences worth stating, because they are easy to lose:

- Rank does not imply scope. A DIG posted to a range and a DIG posted to a wing hold the same rank and different scope.
- Holding a seat does not imply being assignable. All ~10,744 IO seats carry `scope_type='assigned_case'`, but whether an officer can be the IO of record is an *assignment* question settled by `users.is_lead_investigator`, not by having a seat. Head Constables and Constables get seats to see their work; they are not lead investigators.

### The IO seat model in practice

This is where collapsing the layers would do the most visible damage, so it is worth being explicit. ~10,744 seats span four ranks and must not be labelled uniformly:

| Column | Varies across IO seats? | Example values |
|---|---|---|
| `scope_type` | no — identical for all | `assigned_case` |
| `rank_label` | **yes** | Police Sub-Inspector, Assistant Sub-Inspector, Head Constable, Police Constable |
| `designation_label` | **yes** | Investigating Officer, Case Assistant |
| `is_lead_investigator` | **yes** | `TRUE` for PSI/ASI holding an IO posting, `FALSE` for assisting HC/PC |

Approximate split: ~1,656 lead-investigator seats (PSI and ASI on IO postings) and ~9,088 assisting seats (HC and PC). A constable sees the work assigned to them and cannot be recorded as the IO of a case.

`is_lead_investigator` is seeded from `Employee.DesignationID` at provisioning and is admin-editable afterwards, because a posting can change without an establishment change. `rank_label` and `designation_label` are display denormalisations; `Employee.RankID` and `Employee.DesignationID` stay authoritative. Seat usernames are rank-neutral (`io.<employee_id>`), so nothing in the identifier asserts a rank the officer does not hold.

---

## 1. Role model

Ten presentation seats collapse to six application roles. `scope_type` is what varies, not the role name.

| Application role | `scope_type` | Rank in the field | Scope anchor | Count |
|---|---|---|---|---|
| `dgp_state_command` | `state` | DG&IGP | none (whole state) | 1 |
| `senior_command` | `wing` | ADGP | `wing_id` | 6 |
| `senior_command` | `range` | DIG / IGP | `range_id` | 7 |
| `district_command` | `district` | SP | `district_id` | 30 |
| `district_command` | `commissionerate` | CP | `district_id` | 2 |
| `sho` | `station` | PI (urban) / PSI (rural) | `unit_id` | 1,000 |
| `investigating_officer` | `assigned_case` | PSI / ASI / HC / PC | `unit_id` + assigned case set | ~10,744 |
| `system_admin` | `platform` | — | none | 1 |

Hierarchy: DGP → Senior Command (wing or range) → District Command (district or commissionerate) → SHO → IO. System Admin sits outside.

`wing` is a functional scope: state-wide geography, narrowed by crime head. `range` is a geographic scope: a set of districts, all crime heads. Both are `senior_command`, which is why the scope type and not the role determines the filter.

### Files that must agree

The role set is mirrored in five places today and all five change together:

- `web/src/config/roles.ts` — `UserRole` union, `ROLES` table
- `services/ml/app/roles.py` — `FUNCTIONAL_ROLES`, `ROLE_SCOPE_LEVEL`, `DEMO_USERS`
- `services/ml/app/gateway_context.py` — literal role set for defence-in-depth revalidation
- `infra/catalyst/functions/gateway_api/index.js` — `FUNCTIONAL_ROLES`, `RANK_MAP`, `ROLE_DEFAULT_SCOPE`
- `services/ml/sql/police_fir_extensions.sql` — `roles` seed

Add a test asserting the Python and Node sets are identical; `tests/test_gateway_authz.py` already does this for the current set and only needs its fixture updated.

---

## 2. Wings

Six data-consuming wings. Each is state-wide, filtered to its crime heads. Heads come from the existing nine-row `CrimeHead` taxonomy.

| Wing | Code | Crime heads | Absorbs |
|---|---|---|---|
| Law & Order | `LO` | Public Order, Crimes Against Body, Crimes Against Women | — |
| Crime & Technical Services | `CTS` | all heads | Crime Analyst (SCRB) |
| Intelligence | `INT` | Public Order, Crimes Against Body, Smuggling & Excise | — |
| Internal Security & Cyber | `ISC` | Economic & Cyber Crime | Cyber Cell (CEN) |
| Traffic & Road Safety | `TRF` | Traffic Offences | Traffic Command |
| CID / Economic Offences | `CID` | Economic & Cyber Crime, Crimes Against Property, Drug Offences | — |

Crime & Technical Services sees all heads because SCRB owns state crime records and model governance; its distinction is the card set, not a head filter.

---

## 3. Ranges and Commissionerates — VERIFIED AND RESOLVED

Verified against the official source: [Karnataka State Police — Organization](https://ksp.karnataka.gov.in/page/About+Us/Organization/en), retrieved 5 September 2026. *Content paraphrased for compliance with licensing restrictions.*

Official structure: **7 ranges**, each headed by an IGP and comprising 3 to 6 districts, with districts headed by SPs. **6 Police Commissionerates**, where the Bengaluru City CP holds ADGP rank and the other five hold DIG rank.

| Range | HQ | Districts (official) | n |
|---|---|---|---|
| Southern Range | Mysuru | Mysuru, Kodagu, Mandya, Hassan, Chamarajanagara | 5 |
| Western Range | Mangaluru | Dakshina Kannada, Uttara Kannada, Udupi, Chikkamagaluru | 4 |
| Eastern Range | Davanagere | Chitradurga, Haveri, Shivamogga, Davanagere | 4 |
| Central Range | Bengaluru | Tumakuru, Kolar, Bengaluru Rural, **KGF**, Chikkaballapura, Ramanagara | 6 |
| Northern Range | Belagavi | Belagavi, Vijayapura, Dharwad, Bagalkote, Gadag | 5 |
| North Eastern Range | Kalaburagi | Kalaburagi, Bidar, Yadgir | 3 |
| Ballari Range | Ballari | Ballari, Vijayanagara, Raichur, Koppala | 4 |
| | | **Total** | **31** |

### Resolution: the faithful police-unit model

The dataset's 32 rows conflated city and rural commands. Rather than force the org chart into them, migration `034` builds the real structure:

| | Before | After |
|---|---|---|
| District-level units | 32 | **38** |
| Range districts | 30 usable | **32** (31 official + Bengaluru Urban) |
| Commissionerates | 1 usable | **6** |

Added: `Mysuru City`, `Mangaluru City`, `Hubballi-Dharwad City`, `Belagavi City`, `Kalaburagi City` as Commissionerates outside the range hierarchy, and `Kolar Gold Field (KGF)` as a Central Range district. Existing rows keep the **rural remainder**, which is what the official range table refers to.

Per-range counts after the split: SR 5, WR 4, ER 4, CR 7, NR 5, NER 3, BR 4. Central Range holds 7 rather than the official 6 because Bengaluru Urban is retained there — see the deviation note below.

**Bengaluru Urban stays a district, not a Commissionerate.** The official page lists it in neither the range table nor the six Commissionerates, because that revenue district is policed by Bengaluru City. It exists in the dataset only because `datagen/reference.py` tags it `metro`, which made `_load_units` mint a Commissionerate unit for it. It is now a Central Range district under an SP, consistent with the Wikipedia range listing, with its 78 stations intact. The deviation from the official page is recorded in `033_org_roster_seed.sql` rather than hidden.

**How the city/rural split is drawn.** Stations move by `UnitLocation."Taluk"` — the only city/rural signal in the data, and the same field `datagen` used to place each station. Coordinates never change; only the parent district does. `Employee.DistrictID` follows its station, and Commissionerate HQ units are re-parented so `station -> HQ -> district` stays coherent. Every move is recorded in `DistrictSplitAudit`, which is what makes the rollback exact.

**What deliberately does not change.** `CaseMaster."CrimeNo"` embeds a 4-digit district code and is *not* rewritten. A crime number is a permanent identifier; real jurisdictional reorganisations do not renumber historical FIRs. A case's current district is derived through `PoliceStationID -> Unit.DistrictID`, so cases follow their station automatically while the historical number stays truthful about where it was registered.

**Boundaries come from existing geometry.** A Commissionerate polygon is the union of the taluk polygons it took; the rural remainder is the former district polygon minus that union; range polygons are then dissolved from the final district set. No new geodata. The superseded district polygon is retained with `IsCurrent = FALSE` rather than overwritten, so boundary history survives.

### The three findings behind that decision

**3.1 Bengaluru Urban is not a Commissionerate, and is not in the official structure at all.** It appears in neither the range table nor among the 6 Commissionerates: the Bengaluru Urban revenue district is policed by the Bengaluru City Commissionerate. Per your instruction it is not being marked a Commissionerate, and there is no official basis to do so. It exists in the dataset because `datagen/reference.py` tags it `metro`, which made `datagen/lookups.py::_load_units` mint a Commissionerate unit for it. Its 78 generated stations need a destination: fold into Bengaluru City, keep as a Central Range district (Wikipedia lists it there; the official KSP page does not), or retire the row.

**3.2 Five Commissionerates have no row of their own.** Mysuru, Mangaluru, Hubballi-Dharwad, Belagavi and Kalaburagi are *city* commands that coexist with a similarly-named rural police district. The database has one row per name, so a single row would have to be both the city Commissionerate under a CP and the rural district under an SP — different units, different commanders, different station sets, different case loads. This is the largest open decision in the plan, because option (a) moves `Unit.DistrictID`, case jurisdiction and the district boundary layer.

**3.3 KGF is missing.** Official Central Range has 6 districts including Kolar Gold Field. The dataset has no KGF row, which is why a naive mapping gives Central Range 5.

Net: 30 of the dataset's 32 rows mapped cleanly onto official range districts; `Bengaluru City` mapped to a Commissionerate, `Bengaluru Urban` to nothing, and KGF was absent. All three are resolved above.

---

## 4. Data model changes

### 4.1 New tables

```sql
CREATE TABLE "Range" (
  "RangeID"       INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  "RangeName"     VARCHAR NOT NULL UNIQUE,
  "RangeCode"     VARCHAR NOT NULL UNIQUE,
  "HQDistrictID"  INTEGER REFERENCES "District" ("DistrictID"),
  "Active"        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE "Wing" (
  "WingID"      INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  "WingName"    VARCHAR NOT NULL UNIQUE,
  "WingCode"    VARCHAR NOT NULL UNIQUE,
  "Description" TEXT,
  "Active"      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE "WingCrimeHead" (
  "WingID"      INTEGER NOT NULL REFERENCES "Wing" ("WingID") ON DELETE CASCADE,
  "CrimeHeadID" INTEGER NOT NULL REFERENCES "CrimeHead" ("CrimeHeadID"),
  PRIMARY KEY ("WingID", "CrimeHeadID")
);
```

A district belongs to exactly one range, so range membership is a column rather than a join table:

```sql
ALTER TABLE "District" ADD COLUMN "RangeID" INTEGER REFERENCES "Range" ("RangeID");
-- NULL = Commissionerate, outside the range hierarchy
ALTER TABLE "District" ADD COLUMN "IsCommissionerate" BOOLEAN NOT NULL DEFAULT FALSE;
```

### 4.2 Seat scope on `users`

`users` currently has only `unit_id`, which cannot express a wing, a range or a district. Add:

```sql
ALTER TABLE "users" ADD COLUMN "scope_type"  VARCHAR NOT NULL DEFAULT 'assigned_case';
ALTER TABLE "users" ADD COLUMN "wing_id"     INTEGER REFERENCES "Wing" ("WingID");
ALTER TABLE "users" ADD COLUMN "range_id"    INTEGER REFERENCES "Range" ("RangeID");
ALTER TABLE "users" ADD COLUMN "district_id" INTEGER REFERENCES "District" ("DistrictID");
ALTER TABLE "users" ADD COLUMN "employee_id" INTEGER REFERENCES "Employee" ("EmployeeID");
ALTER TABLE "users" ADD CONSTRAINT chk_users_scope_type CHECK ("scope_type" IN
  ('state','wing','range','district','commissionerate','station','assigned_case','platform'));
```

Exactly one anchor must be set per `scope_type`; enforce with a check constraint so a half-provisioned seat fails loudly instead of silently resolving to state-wide.

`employee_id` closes the gap where login accounts and the officer establishment were unrelated populations, which is what made "the SHO of station X" unidentifiable.

### 4.3 Admin UI visibility

```sql
CREATE TABLE "role_ui_grants" (
  "id"            INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  "role_name"     VARCHAR NOT NULL REFERENCES "roles" ("role_name"),
  "scope_type"    VARCHAR,          -- NULL = every scope_type of that role
  "element_kind"  VARCHAR NOT NULL, -- destination | board | kpi | widget
  "element_id"    VARCHAR NOT NULL,
  "enabled"       BOOLEAN NOT NULL,
  "updated_by"    VARCHAR,
  "updated_at"    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_role_ui_grants UNIQUE ("role_name","scope_type","element_kind","element_id"),
  CONSTRAINT chk_role_ui_element_kind CHECK ("element_kind" IN ('destination','board','kpi','widget'))
);
```

An empty table means "use the code defaults". A row is an explicit override. This keeps the registry authoritative and the database a diff, so adding a new card does not require an admin action before anyone can see it.

### 4.4 SHO identification

`datagen/lookups.py::_load_employees` assigns rank independently of station, so a station can hold several DGPs and no SHO. Fix in the generator:

- Guarantee exactly one `Police Inspector` per station carrying designation `Station House Officer`.
- Guarantee at least two officers of PSI rank or below carrying designation `Investigating Officer`.
- Keep `RANK_STAFFING` for the remaining establishment so the rank pyramid stays realistic.

### 4.5 Range and Commissionerate boundaries

`JurisdictionBoundary."Level"` is constrained to `state|district|taluk|unit|beat|sho`. Extend it to include `range`, then dissolve range polygons from the 32 district geometries already present. No new geodata is needed; this is a `ST_Union` over existing rows.

### 4.6 Seat inventory to provision

Derived from the 12,000 `Employee` rows that `datagen/config.py` targets, distributed by the `RANK_STAFFING` pyramid in `datagen/reference.py`.

| Seat class | Rows | Anchor | Drawn from |
|---|---|---|---|
| DGP | 1 | none | DGP rank |
| ADGP wings | 6 | `wing_id` | ADGP rank |
| DIG ranges | 7 | `range_id` | IGP / DIG rank |
| SP districts | 30 | `district_id` | SP rank |
| CP commissionerates | 2 | `district_id` | ADGP / DIG rank |
| SHO | 1,000 | `unit_id` | PI (~419) then PSI (~581) |
| **Command + station subtotal** | **1,046** | | |
| IO | **~10,744** | `unit_id` + case set | PSI/ASI/HC/PC not holding an SHO seat |
| System Admin | 1 | none | — |
| **Total** | **~11,791** | | |

Expected rank distribution at 12,000 officers: DGP 1, ADGP 3, IGP 7, DIG 14, SP 35, Addl.SP 56, Dy.SP 140, PI 419, PSI 839, ASI 1,398, HC 2,796, PC 6,292.

Two things follow from that distribution:

- **PI alone cannot staff 1,000 stations** (~419 available). This is not a defect: in the real force urban stations are headed by an Inspector and rural stations by a Sub-Inspector, so drawing SHOs from PI first and then PSI is correct. PI + PSI ≈ 1,258, comfortably above 1,000.
- **`RANK_STAFFING` is a weighted random draw**, not a deterministic allocation, so actual per-rank counts vary between generator runs. The provisioning script must therefore derive seats from the `Employee` rows that actually exist, never from the expected distribution, and fail loudly if any station has no PI/PSI to make SHO.

Seat usernames derive deterministically from the anchor: `sho.<unit_id>`, `io.<employee_id>`, `sp.<district_slug>`, `cp.<district_slug>`, `dig.<range_code>`, `adgp.<wing_code>`. Display names and rank/designation labels come from the linked `Employee` row via `users.employee_id`.

### 4.7 Admin-editable settings

Two tables, both following the same rule as `role_ui_grants`: an absent row or a NULL column means "use the code default", so shipping a new role or field never requires an admin action first.

**Per-user** (`users`, migration 027): `display_name`, `email`, `phone`, `rank_label`, `designation_label`, `posting_label`, `preferred_language` (`en` | `kn`), `avatar_url`, `notes`, `is_active`, `must_reset_password`, plus the scope anchors. The three `*_label` columns are denormalised for display only; `Employee.RankID` and `Employee.DesignationID` remain the establishment source of truth, preserving the rank/assignment separation from §0.

**Per-role** (`role_settings`, migration 030): `display_label`, `description`, `default_route`, `default_board_id`, `icon_name`, `sort_order`. `default_route` is CHECK-constrained to start with `/` and is validated against the route table before being applied, so a typo cannot strand a role on a dead landing page.

Endpoints:

```
GET    /org/users?q=&role=&scope_type=   → paginated seat directory
GET    /org/users/{id}                   → one seat, resolved labels
PUT    /org/users/{id}/profile           → name, contact, language, labels, notes
PUT    /org/users/{id}/scope             → scope_type + anchor (re-validated)
POST   /org/users/{id}/active            → activate / deactivate
GET    /admin/roles/settings             → all six roles, defaults ∪ overrides
PUT    /admin/roles/{role}/settings      → upsert presentation settings
DELETE /admin/roles/{role}/settings      → clear overrides, revert to code
```

`PUT /org/users/{id}/scope` must re-run the same anchor validation as the CHECK constraint and reject a mismatch, so an admin cannot create through the API a seat state the database would refuse.

---

## 5. Scope resolution

One resolver turns a seat into a query filter. This replaces the current `derive_scope` fall-through that leaves every district and station seat unrestricted.

| `scope_type` | Geographic filter | Head filter | Case-detail access |
|---|---|---|---|
| `state` | none | none | denied (aggregate only) |
| `wing` | none | `crime_head_id IN (wing heads)` | own-wing cases only |
| `range` | `district_id IN (range districts)` | none | read within range |
| `district` | `district_id = X` | none | read within district |
| `commissionerate` | `district_id = X` | none | read within commissionerate |
| `station` | `unit_id = X` | none | read/write within station |
| `assigned_case` | `unit_id = X` | none | read/write assigned cases only |
| `platform` | none | none | denied by default |

Rules that hold at every tier:

1. **Aggregate-only above district.** DGP and ADGP boards must not read case rows. Already a stated constraint in `StateCommandHome`; it becomes enforced rather than conventional.
2. **A card that cannot be scoped says so.** The existing `districtSupport` map and `STATE_WIDE_NOTE` pattern extends to the new tiers. Never let a selector imply a filter that is not applied.
3. **A card that is meaningless at a tier is absent, not zero.** Load imbalance across one station is not 1.0, it is undefined. See the tier matrix in §6.
4. **`derive_scope` must fail closed.** The current `else: districts, units = None, None` branch becomes an empty frozenset for a seat whose anchor is missing, so a misprovisioned seat sees nothing rather than everything.

---

## 6. KPI card registry

One catalogue, one card per row, selected per role. This replaces five hand-written boards where `StateCommandHome` has 26 declarative cards and the other four have 4 hard-coded ones each.

Legend: **Y** included · **–** excluded by choice · **X** not meaningful at that tier · **W** wing-conditional

### Band A — Volume and pulse

| id | Label | Source | DGP | ADGP | DIG | SP/CP | SHO | IO |
|---|---|---|---|---|---|---|---|---|
| `kpi-incidents` | Incidents (window), YoY delta | `/geo/trends` | Y | Y | Y | Y | Y | – |
| `kpi-mom` | Month-on-month change | `/geo/trends` | Y | Y | Y | Y | Y | – |
| `kpi-anomalies` | Anomalous periods | `/geo/trends` | Y | Y | Y | Y | X | X |
| `kpi-new-firs` | New FIRs (90d) | `/performance/overview` | Y | Y | Y | Y | Y | – |
| `kpi-open-cases` | Open cases | `/cases/caseload` | Y | Y | Y | Y | Y | – |
| `kpi-workload` | Active workload | `/performance/overview` | Y | Y | Y | Y | Y | – |
| `kpi-my-open` | My open cases | `/cases/caseload` | X | X | X | X | – | Y |
| `kpi-my-new` | New assignments | `/cases/caseload` | X | X | X | X | – | Y |

`kpi-anomalies` is excluded below district because a single station's monthly series is too sparse for a rolling anomaly band to mean anything.

### Band B — Alerts and urgency

| id | Label | Source | DGP | ADGP | DIG | SP/CP | SHO | IO |
|---|---|---|---|---|---|---|---|---|
| `kpi-critical-alerts` | Critical alerts | `/geo/alerts` | Y | Y | Y | Y | Y | – |
| `kpi-open-alerts` | Open alerts | `/geo/alerts` | – | Y | Y | Y | Y | – |
| `kpi-my-alerts` | My alerts | `/geo/alerts` | X | X | X | X | – | Y |
| `kpi-hotspots` | Hotspots | `/geo/hotspots` | Y | Y | Y | Y | Y | Y |

### Band C — Outcomes and accountability

All from `/performance/overview` unless noted.

| id | Label | DGP | ADGP | DIG | SP/CP | SHO | IO |
|---|---|---|---|---|---|---|---|
| `kpi-chargesheet` | Chargesheet throughput | Y | Y | Y | Y | Y | – |
| `kpi-days-to-chargesheet` | Median days to chargesheet | Y | Y | Y | Y | Y | Y |
| `kpi-disposal` | Disposal rate | Y | Y | Y | Y | Y | – |
| `kpi-conviction` | Conviction rate — **new** `/outcomes/overview` | Y | W:CTS,CID | Y | Y | Y | – |
| `kpi-overdue` | Overdue reviews | Y | Y | Y | Y | Y | Y |
| `kpi-ageing-180` | Open more than 180 days | – | Y | Y | Y | Y | Y |
| `kpi-imbalance` | Station load imbalance | Y | Y | Y | Y | X | X |
| `kpi-stations` | Stations in scope | Y | Y | Y | Y | X | X |
| `kpi-officers` | Officers in scope | Y | Y | Y | Y | Y | X |
| `kpi-officer-p90` | P90 open cases per officer | – | – | Y | Y | Y | X |
| `kpi-heavy-load` | Heavy-load officers | – | – | Y | Y | Y | X |

`kpi-conviction` moves off `pending: true`. `CaseDisposition."DispositionType"` already holds convicted / acquitted / closed_b_report / closed_c_report with an `IsFinal` flag, so the only thing missing was an aggregate endpoint.

### Band D — Forecast and model trust

| id | Label | Source | DGP | ADGP | DIG | SP/CP | SHO | IO |
|---|---|---|---|---|---|---|---|---|
| `kpi-predicted` | Predicted next period | `/forecast/map` | Y | Y | Y | Y | X | X |
| `kpi-wape` | Forecast error (WAPE) | `/forecast/backtest` | Y | W:CTS | – | – | X | X |
| `kpi-coverage` | 80% interval coverage | `/forecast/backtest` | Y | W:CTS | – | – | X | X |
| `kpi-abstention` | Forecast abstention | `/forecast/backtest` | Y | W:CTS | – | – | X | X |

Forecast grain is district, so there is no station-level prediction to show. Backtest accuracy is a state-wide model property with a geographic holdout, not a per-district filter.

### Band E — Data integrity

| id | Label | Source | DGP | ADGP | DIG | SP/CP | SHO | Admin |
|---|---|---|---|---|---|---|---|---|
| `kpi-data-age` | Case-data age | `/performance/overview` | Y | Y | Y | Y | Y | Y |
| `kpi-data-quality` | Data-quality issues | `/intake/quality/issues` | Y | W:CTS | Y | Y | Y | Y |
| `kpi-jurisdiction` | Jurisdiction issues | `/geo/jurisdiction/freshness` | Y | W:CTS | Y | Y | Y | Y |
| `kpi-suppressed` | Cells suppressed (k-anonymity) | `/analytics/socioeconomic` | Y | Y | – | – | X | – |
| `kpi-districts` | Districts analysed | `/analytics/socioeconomic` | Y | Y | Y | X | X | – |
| `kpi-conformance` | Contract conformance | `/explain/contract` | Y | – | – | – | X | Y |

### Band F — Patterns and networks

| id | Label | Source | DGP | ADGP | DIG | SP/CP | SHO | IO |
|---|---|---|---|---|---|---|---|---|
| `kpi-patterns` | Active patterns | `/analytics/patterns` | Y | Y | Y | Y | Y | – |
| `kpi-groups` | Organised groups | `/graph/communities/list` | Y | W:INT,ISC,CID | Y | Y | – | – |
| `kpi-poi` | Persons of interest | `/graph/centrality` | – | W:INT,ISC,CID | Y | Y | Y | Y |
| `kpi-tasks` | Open tasks | `/notifications/tasks` | Y | Y | Y | Y | Y | Y |

### Band G — Cyber and financial (wing-only)

| id | Label | Source | Wings |
|---|---|---|---|
| `kpi-flagged-txn` | Flagged transactions | `/money/flagged` | ISC, CID |
| `kpi-money-trails` | Circular / high-risk flows | `/money/unified` | ISC, CID |
| `kpi-linked-accounts` | Resolved account links | `/identity/stats` | ISC |

### Band H — Traffic (wing-only)

| id | Label | Source | Wings |
|---|---|---|---|
| `kpi-traffic-incidents` | Traffic incidents | `/geo/trends` head-filtered | TRF |
| `kpi-accident-hotspots` | Accident hotspots | `/geo/hotspots` head-filtered | TRF |

### Band I — Case work (SHO and IO)

| id | Label | Source | SHO | IO |
|---|---|---|---|---|
| `kpi-review-queue` | Review queue depth | `/intake` inbox | Y | – |
| `kpi-next-hearing` | Next court date | **new** from `CourtEvent` | Y | Y |
| `kpi-evidence-pending` | Evidence pending | `/casework` | Y | Y |

### Band J — Platform (Admin)

| id | Label | Source |
|---|---|---|
| `kpi-active-seats` | Active seats | `/org/users` |
| `kpi-imports` | Pending imports | `/admin/queues` |
| `kpi-models` | Models in registry | `/admin` registry |
| `kpi-ui-overrides` | UI grants overridden | **new** `/admin/ui-visibility` |

### Card counts per seat

| Seat | Cards |
|---|---|
| DGP | 30 |
| ADGP (varies by wing) | 18–26 |
| DIG | 26 |
| SP / CP | 25 |
| SHO | 20 |
| IO | 10 |
| Admin | 10 |

---

## 7. View and widget allow-lists

Populates the `Destination.roles` allow-list in `web/src/config/destinations.tsx`, which exists today and is unused, plus a new `scopeTypes` field.

| Destination | DGP | ADGP | DIG | SP/CP | SHO | IO | Admin |
|---|---|---|---|---|---|---|---|
| Command Center | Y | Y | Y | Y | Y | Y | Y |
| Cases | aggregate | W: own heads | aggregate + list | full (district) | full RW (station) | assigned only | Y |
| Intake | – | – | review | review | create + review | create | Y |
| People & Entities | aggregate | W:INT,ISC,CID | aggregate | Y | Y | Y | Y |
| Network Analysis | Y | W:INT,ISC,CID | Y | Y | limited | case-centric | Y |
| Investigation Board | Y | W:INT,ISC,CID | Y | Y | Y | Y | Y |
| Map & Hotspots | Y | Y | Y | Y | Y | Y | Y |
| Analytics & Forecasting | Y | Y | Y | Y | – | – | Y |
| Ask DRISHTI | Y | Y | Y | Y | Y | Y | Y |
| Governance | Y | W:CTS | – | – | – | – | Y |
| Imports | – | – | – | – | – | – | Y |
| Review queues | – | W:CTS | Y | Y | Y | – | Y |
| Admin | – | W:CTS (read) | – | – | – | – | Y |
| Support | Y | Y | Y | Y | Y | Y | Y |
| Emergency Response | Y | W:LO | Y | Y | read | – | Y |

`/governance`, `/imports`, `/review/*` and `/profile` are currently reachable by URL but absent from the sidebar. Add them as first-class destinations so the allow-list governs them, rather than leaving them unlisted but open.

Widget allow-lists follow the same table, keyed by widget id. Notable per-seat widgets:

- DGP: state trend, district forecast, socio-economic band, range league table
- ADGP: wing trend, head breakdown, plus wing-specific (money Sankey for ISC/CID, corridor map for TRF, model registry for CTS)
- DIG: **district league table** across the range — the widget a range officer actually works from
- SP/CP: **station league table** (`StationPerformance` already exists), review queue, district hotspot map
- SHO: station status pipeline, review queue, officer load table, station jurisdiction map
- IO: my caseload, attention queue, case timeline, board shortcuts

---

## 8. Drill-down

Each step narrows scope and pushes onto a stack; the breadcrumb renders the stack and back pops it.

| Seat | Chain | Terminates at |
|---|---|---|
| DGP | State → Range → District → Station | station aggregate; no case file |
| ADGP wing | State (head-filtered) → District → Station → Case list | own-wing case detail only |
| DIG | Range → District → Station → Case list | case detail, read-only |
| SP / CP | District → Station → Case list → Case file | full case file |
| SHO | Station → Case list → Case file → Entity / Board | read-write case file |
| IO | My cases → Case file → Entity / Board | read-write assigned cases |

Rules:

- A drill-down never widens scope. Clicking into a district from a range view sets `district_id` but keeps the range as the ceiling.
- The scope ceiling is the seat's anchor and cannot be escaped by UI navigation or by editing the URL.
- Drilling below the aggregate-only floor is not a permission error, it is an absent affordance: DGP league-table rows are not clickable through to case files.

`useScopeStore` currently holds a single `districtId`, which cannot express any of this. It becomes:

```ts
interface ScopeState {
  ceiling: { level: ScopeLevel; rangeId?: number; districtId?: number; unitId?: number };
  active:  { level: ScopeLevel; rangeId?: number; districtId?: number; unitId?: number };
  stack:   ScopeSelection[];
  push(sel: ScopeSelection): void;
  pop(): void;
  reset(): void;
}
```

`ceiling` is seeded once from `/org/my-scope` and never changes in-session. `active` is what the widgets read.

---

## 8b. Custom roles — admin creates any role with any permission

Roles were a fixed set in code. Admin can now create a role of any kind and compose any permission onto it, without a deploy.

**Why not `role_permissions`.** Its `action` column is `permission_action_enum` = `read | write | none`. "Any permission" needs verbs that enum cannot express — approve, export, assign, dispatch, override. `ALTER TYPE ... ADD VALUE` would work, but PostgreSQL cannot *remove* an enum value, which would make the migration irreversible. So `permission_catalogue` uses a text action, and `role_permissions` is kept as a legacy projection because the whitelisted-SELECT executor and the Phase-14 RLS design both read it.

**Permission catalogue: 38 permissions across 7 categories**, 20 flagged sensitive. Each row carries `resource`, `action`, `label`, `category`, `is_sensitive` and `requires_scope`. A catalogue rather than free text, so the console offers real choices and a typo cannot invent a permission nothing checks.

`requires_scope` is the interesting field: it records the narrowest scope at which a permission is meaningful. `cases.detail_read` requires `district`, so granting it to a state seat is refused — that seat is aggregate-only by design, and this is what stops an admin from accidentally dissolving the §5 aggregate-only rule through the roles console.

**A custom role composes three things** and needs no new frontend code:

- `base_surface` — which of the six built-in UI surfaces it renders (`state_command`, `senior_command`, `district_command`, `station`, `case_work`, `platform`). `role_ui_grants` then trims or extends it.
- `role_grant` — any subset of the catalogue.
- `allowed_scope_types` — which `scope_type`s a seat holding this role may be assigned, so a station-only role cannot be issued as a state seat.

A custom role never carries a scope itself. Scope belongs to the seat, so the same role can be issued at district level to one officer and at state level to another.

```
GET    /admin/permissions               catalogue grouped by category
GET    /admin/roles                     roles + grant counts + surface
POST   /admin/roles                     create
PUT    /admin/roles/{role}/grants       replace the grant set
PATCH  /admin/roles/{role}/grants/{key} toggle one grant
DELETE /admin/roles/{role}              custom roles only, zero seats only
```

Five rules the API must enforce that SQL cannot express alone:

1. `is_system` roles cannot be renamed or deleted.
2. A grant whose `requires_scope` is narrower than a seat's `scope_type` is refused.
3. Granting an `is_sensitive` permission requires a reason, written to `audit_logs`.
4. A seat's `scope_type` must appear in its role's `allowed_scope_types`.
5. `role_permissions` is re-projected from `role_grant` on every change.

Built-in roles receive every catalogued permission on migration, matching the interim policy already in force elsewhere, so `035` changes no effective access. Narrowing that is the capability-matrix task in §13.

---

## 9. Admin UI-visibility console

New Admin panel: a role × element grid of switches.

- Rows grouped by `element_kind` (destination, board, kpi, widget), columns are the six roles, with a scope-type sub-selector for `senior_command` and `district_command`.
- A switch writes one `role_ui_grants` row. Clearing an override deletes the row and returns that element to its registry default.
- Bulk actions: enable/disable a whole band for a role, and copy one role's grants to another.
- Every toggle appends to `audit_logs` with actor and before/after, matching how `set_feature_flag` already records.

Endpoints:

```
GET    /admin/ui-visibility               → full matrix: defaults ∪ overrides
PUT    /admin/ui-visibility               → upsert one grant
DELETE /admin/ui-visibility/{id}          → clear one override
POST   /admin/ui-visibility/copy          → copy role → role
```

Frontend: `useUiVisibility()` fetches the matrix once per session and intersects it with the registry. `visibleDestinations()` and the board builder both consult it. Cached with a short TTL and invalidated on toggle.

An important limit to state plainly in the UI: while authentication and RLS are off, these switches control **visibility, not access**. A hidden destination is still reachable by typing its URL, and a hidden card's endpoint still answers. The panel should say so, so nobody mistakes it for an access-control boundary.

---

## 10. Endpoint work

### Scope parameters to add

| Endpoint | Add |
|---|---|
| `/geo/trends` | `unit_id`, `district_ids[]`, keep `crime_head_id` |
| `/geo/hotspots` | `district_id`, `district_ids[]`, `unit_id`, `crime_head_id` |
| `/geo/alerts` | `district_id`, `district_ids[]`, `unit_id` |
| `/forecast/map` | `district_id`, `district_ids[]` |
| `/performance/overview` | `district_ids[]`, `crime_head_ids[]` |
| `/analytics/patterns` | `district_id`, `district_ids[]` |

`district_ids[]` is what makes a range seat possible; nothing today accepts a district set.

### New endpoints

| Endpoint | Purpose |
|---|---|
| `GET /outcomes/overview` | Conviction / acquittal / B-report / C-report counts and rates, scoped. Unblocks `kpi-conviction`. |
| `GET /performance/districts` | District league table for a range. DIG's primary widget. |
| `GET /org/ranges` | Range list with district membership. |
| `GET /org/wings` | Wing list with crime heads. |
| `GET /org/seats?q=&role=&scope_type=` | Paginated, searchable seat directory for the login picker. |
| `GET /casework/hearings/next` | Next court date, scoped. Unblocks `kpi-next-hearing`. |
| `GET/PUT/DELETE /admin/ui-visibility` | Admin toggle matrix. |

### Enforcement wiring

`resolve_request_scope()` exists in `services/ml/app/org/scope.py` and is called by no router. Wire it into every data router as a FastAPI dependency, then have each service apply the returned filter. `/performance/overview` is the only endpoint doing this today via `enforce_geo_request`; that becomes the pattern rather than the exception.

---

## 11. Performance

1,000 SHO seats against an uncached `/performance/overview` that costs 7 sequential aggregate round trips over `CaseMaster ⋈ Unit ⋈ CaseStatusMaster` will not hold up. Current dashboards read base tables live; the three existing materialized views are refreshed but unused by any KPI endpoint.

- **Rollup matview** `mv_case_daily` keyed by `(unit_id, district_id, crime_head_id, registered_date, status_bucket)` with a count. Every Band A and Band C card reads this instead of base tables. Refresh nightly plus on demand, `CONCURRENTLY` with a unique index.
- **Indexes**: composite `CaseMaster(PoliceStationID, CaseStatusID, CrimeRegisteredDate)`; partial index for open statuses. Today the open-status filter is a text predicate on `CaseStatusMaster."CaseStatusName"` with no supporting index.
- **Cache**: add a `dashboard` segment to `app/cache.py` (which has only `idempotency`, `ratelimit`, `nonce`, `lookup`) with a 60–300 s TTL keyed by scope and window. Set `Cache-Control` on metrics responses.
- **Bound the unbounded**: `/geo/alerts` groups over all of `CaseMaster` with no date bound; `/geo/jurisdiction/freshness` runs under a two-minute `statement_timeout`. Both need date bounds and scope pushed into the query.
- Target: warm dashboard payload under 400 ms at the 95th percentile for a station seat.

---

## 12. Task breakdown

### Phase 0 — Data model and seed

Migrations are **written and validated but NOT applied**, pending review. See §14.

1. ~~`026_org_wing_range`~~ — written, validated.
2. ~~`027_users_scope_profile`~~ — written, validated.
3. ~~`028_roles_six_app_roles`~~ — written, validated.
4. ~~`029_role_ui_grants`~~ — written, validated.
5. ~~`030_role_settings`~~ — written, validated.
6. ~~`031_jurisdiction_range_level`~~ — written, validated.
7. ~~`032_dashboard_rollup`~~ — written, validated.
8. ~~`033_org_roster_seed`~~ — written, validated.
9. ~~`034_district_commissionerates`~~ — written, validated.
10. ~~`035_custom_roles`~~ — written, validated.
11. Update the four mirrored role sets (`web/src/config/roles.ts`, `services/ml/app/roles.py`, `services/ml/app/gateway_context.py`, `infra/catalyst/functions/gateway_api/index.js`) and extend the sync test in `tests/test_gateway_authz.py`.
12. Fix `datagen/lookups.py::_load_employees`: exactly one PI-or-PSI SHO per station, at least two IO-designated officers per station, and rank no longer drawn independently of post.
13. Seat provisioning script — ~11,791 seats, idempotent, re-runnable, dry-run mode, deriving from actual `Employee` rows, seeding `is_lead_investigator` from designation, and failing loudly on any station with no PI/PSI available.

### Phase 1 — Backend scope
8. Extend `ScopeContext` with `wing_id`, `range_id`, and a district set; make `derive_scope` fail closed.
9. Resolve seats from the new `users` columns in `org/service.py`.
10. Wire `resolve_request_scope` into every data router as a dependency.
11. Add the scope parameters from §10 to the six existing endpoints.
12. `GET /org/ranges`, `/org/wings`, `/org/seats`.

### Phase 2 — Aggregation and new endpoints
13. `mv_case_daily` plus refresh registration in `app/matviews.py`.
14. Indexes and the `dashboard` cache segment.
15. `GET /outcomes/overview` (unblocks conviction rate).
16. `GET /performance/districts` (DIG league table).
17. `GET /casework/hearings/next`.

### Phase 3 — Frontend scope and seat picker
18. Rewrite `useScopeStore` to ceiling / active / stack.
19. Seed `ceiling` from `/org/my-scope` in `useSeatScopeAnchor`.
20. Replace the ten login cards with tier-then-search against `/org/seats`.
21. Scope breadcrumb component in the app shell.

### Phase 4 — KPI registry and boards
22. `web/src/config/kpi/registry.ts` — the ~45-card catalogue with tier and wing applicability.
23. `web/src/config/kpi/roleBoards.ts` — role and scope_type → ordered card and widget ids.
24. One registry-driven `RoleBoard`, absorbing `StateCommandHome`, `PolicymakerHome`, `SupervisorHome`, `AnalystHome`, `InvestigatorHome`.
25. Populate `Destination.roles` and add `scopeTypes`; make `visibleDestinations` honour both.
26. New widgets: range league table, district league table, wing head-breakdown.

### Phase 5 — Drill-down
27. Drill-down handlers on league tables and map features, respecting the ceiling.
28. Aggregate-only floor: suppress case-file affordances for `state` and `wing` seats.

### Phase 6 — Admin console
29. `role_ui_grants` service plus the four endpoints.
30. `useUiVisibility()` and registry intersection.
31. Admin panel grid with bulk actions, audit logging, and the visibility-not-access notice.

### Phase 7 — Verification
32. Scope tests: each `scope_type` narrows queries as specified; a misprovisioned seat sees nothing.
33. Registry tests: every card resolves at every tier it claims; no card references a missing endpoint field.
34. Seat-count assertions: 1 + 6 + 7 + 32 + 1,000 seats exist with correct anchors.
35. Performance check against the target in §11.

Phases 0–2 are backend and unblock everything else. Phases 3–5 are the visible change. Phase 6 depends only on Phase 0 item 3 and can run in parallel with 4–5.

---

## 13. Before real FIR data

Deliberately out of scope now, and load-bearing before this touches a real record:

1. **Authentication.** `DRISHTI_DEMO_AUTH=true` mints a full-access `system_admin` with no session. Must be off, with Catalyst Authentication resolving real identities.
2. **Enforcement flag.** `DRISHTI_REQUIRE_GATEWAY_CONTEXT` must be `true`, or the gateway-context middleware is a no-op and `X-Role` is client-asserted.
3. **Capability matrix.** `roleCan()` returns `true` for everything and `role_permissions` is a cross join granting every role write on every resource.
4. **RLS.** Explicitly disabled on every base table. It is the backstop for the §5 filters; without it a missed filter is a silent leak.
5. **PII handling.** Retention, redaction and purpose limitation for real complainant, victim and accused records.
6. **Audit completeness.** Every material read of a case file should append, not only writes.
7. **DySP/ACP tier.** 91 SDPOs and 230 circles exist in the real force with no data model here. Needs `Unit` rows at `UnitType` 2 and 3 with `ParentUnit` wiring before that seat is real.

---

## 14. Migration inventory and validation

Ten up/down pairs in `services/ml/sql/`, numbered from 026 (025 was the last in use). **None has been applied to any database.**

| Migration | Adds | Reversible |
|---|---|---|
| `026_org_wing_range` | `Range`, `Wing`, `WingCrimeHead`; `District.RangeID` / `.IsCommissionerate` / `.CommandRank` | yes |
| `027_users_scope_profile` | `users` scope anchors + CHECKs; profile columns; `is_lead_investigator` | yes, lossy on values written after |
| `028_roles_six_app_roles` | Six application roles; remaps users; rebuilds permission matrix | yes, via `legacy_role_name` + `scope_type` fallback |
| `029_role_ui_grants` | Admin UI-visibility override matrix | yes |
| `030_role_settings` | Per-role presentation settings | yes |
| `031_jurisdiction_range_level` | `range` / `subdivision` boundary levels; `JurisdictionBoundary.RangeID` | yes |
| `032_dashboard_rollup` | `mv_case_daily`, `mv_refresh_state`, four indexes | yes |
| `033_org_roster_seed` | 6 wings + crime heads, 7 ranges, range membership | yes, refuses if seats anchored |
| `034_district_commissionerates` | 5 Commissionerates + KGF; station/officer re-parenting; boundary derivation | yes, exactly, via `DistrictSplitAudit` |
| `035_custom_roles` | `permission_catalogue` (38), `role_grant`, `roles.base_surface` / `.allowed_scope_types` | yes |

### Validated in a throwaway PostGIS container

Harness in `scripts/migrations/` (`extract_fixture.py`, `validate_026_035.sh`, `README.md`). It extracts the 19 tables and one enum these migrations touch from `_migration/drishti_schema.sql`, because the full dump cannot load in a stock PostGIS image — it needs `pgrouting` and `pgvector`.

Result: all ten up, thirteen assertions pass with zero errors, all ten down, 32 districts and 10 roles restored, zero leftover tables or columns.

Assertions worth naming:

- **Analytics-eligibility.** Seeds three cases, one flagged `excluded_from_derived_analytics`, and requires the rollup to report `open=1, closed=1` rather than `2/1`. Proves the fail-closed predicate copied from `app/cases/analytics_policy.py` is genuinely in effect — the reason `mv_case_daily` reconciles with `/performance/overview` instead of quietly over-counting.
- **Carved polygons are disjoint.** `ST_Overlaps` between Mysuru and Mysuru City must return zero, so the rural remainder and the Commissionerate never double-count a hotspot.
- **IO seats keep distinct ranks.** Asserts 3 distinct `rank_label` values across the `assigned_case` seats and exactly one lead investigator, which is what would regress if the seats were ever labelled uniformly.
- **Officer/station drift is zero.** No `Employee` left in a district its station no longer belongs to.

### Ordering constraints, found by validating rather than by reasoning

- `027.down` before `026.down` — the `wing_id` / `range_id` FKs reference tables `026` drops.
- `028.down` before `027.down` — it maps post-`028` seats back by `scope_type`, which `027` drops.
- `034.down` before `033.down` — `034` creates District rows referencing `033`'s Range rows.
- `031.down` deletes `range` / `subdivision` boundary rows before narrowing the CHECK, which would otherwise reject the `ALTER`.

### Three bugs the validation caught

1. **`028.down` stranded every provisioned seat.** Seats created after `028` have no `legacy_role_name`, so the rollback could not restore them, and the guard correctly refused to delete a role still referenced — leaving twelve roles instead of ten. With 1,046 seats provisioned, *every one* would have been stranded. Fixed by deriving the legacy role from `scope_type`.
2. **Invalid SQL in that fix.** PostgreSQL forbids referencing the UPDATE target alias from a `JOIN ... ON` inside the `FROM` list. Moved every correlation into `WHERE`.
3. **Identity sequences were never advanced.** `datagen` COPYs `District` and `JurisdictionBoundary` with explicit primary keys. `GENERATED BY DEFAULT AS IDENTITY` permits that but leaves the sequence at 1, so `034`'s first generated insert collided on `District_pkey`. **This would have failed on RDS too.** Fixed with an advance-only `setval` guard.

None of the three would have surfaced from reading the files.

---

## Open items needing your input

1. **Apply the migrations.** All ten written and validated in both directions; nothing applied. I'd take an RDS snapshot first regardless of the tested rollbacks, since `034` re-parents stations and officers.
2. **Station counts in the new Commissionerates.** The taluk split gives Mysuru City 7 stations, Mangaluru City 5, Hubballi-Dharwad 14, Belagavi City 4, Kalaburagi City 4. Those are small against real city commands, because `datagen` allocated stations by district population weight without a city concept. If you want realistic Commissionerate sizes, that is a generator change (re-weight allocation toward the city taluks) rather than a migration change.
3. **Central Range holds 7 districts, not the official 6**, because Bengaluru Urban is retained there. Recorded as a deviation in `033`. Alternative is retiring the row and folding its 78 stations into Bengaluru City.
