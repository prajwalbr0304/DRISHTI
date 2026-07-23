# PHASE 16 — Investigation Board (Palantir-style object-backed analytical canvas)

Status date: 2026-07-19
Owner: implementation agent (Kiro)
Scope: a shared, object-backed analytical canvas where a synthetic investigator
assembles live DRISHTI objects, explores relationships, separates source
evidence from human hypotheses, annotates reasoning, replays changes, and
exports a fully attributable synthetic demonstration board. Rendered with the
Calm Authority design system. No Palantir names/branding/assets are used —
Palantir Gotham was a behavioural reference only.

> **Honesty note.** Everything below is IMPLEMENTED and locally verified. Board
> records are **Data Store-native** (created directly in Catalyst Data Store and
> populated by the AppSail board service at runtime) — there is **no new
> PostgreSQL operational migration** for the board. In dev/tests the Catalyst
> services run through their in-memory fakes (Data Store / NoSQL / Cache /
> Stratus / Signals); the deployed AppSail selects the Catalyst SDK impls via
> `DRISHTI_USE_CATALYST_*` env flags. AWS RDS is retained only for the protected
> graph/analytics reads (Search Around) and read-only reference hydration.

---

## 0. Executive status

| Area | State |
|---|---|
| Data Store schema (6 board tables, versioned config + repeatable provisioning) | **DONE** |
| Object & provenance contract (whitelist, live ref + pinned snapshot/hash, diff) | **DONE** |
| FastAPI board service + 34 routes (CRUD, import, search-around, promote, export) | **DONE** |
| RBAC (IO/Analyst/Supervisor allow, policymaker denied) enforced in AppSail | **DONE** |
| Append-only BoardActivity + optimistic concurrency + idempotency + compensation ordering | **DONE** |
| Evidence(read-only) vs hypothesis(editable, rationale-gated) distinction | **DONE** |
| Search Around / subgraph import (capped, id-based, cached, benchmarked) | **DONE** |
| Hypothesis promotion → review proposal (never a confirmed NetworkEdge) | **DONE** |
| Locking / branching / private source-linked export (hash + synthetic watermark) | **DONE** |
| React Flow canvas + custom nodes + inspector + Table/History/Timeline helpers | **DONE** |
| Send to Board (universal peek + case + network) | **DONE** |
| Catalyst-hosted collaboration (activity replay + presence NoSQL/TTL + post-commit signal) | **DONE** |
| Deterministic golden fixture (case board, evidence, 2 hypotheses, frames, locked+branch, superseded) | **DONE** |
| Tests (36 board tests pass; 400 collect; frontend typecheck + build) | **DONE** |
| Optional grounded board assist (Explain / What am I missing?) | **Deferred** (feature-flagged absent; see §12) |
| OCR / transcription / file-content extraction | **Deferred** — never invoked (metadata/provenance only) |

---

## 1. Files created / changed

### 1.1 Data Store schema (Data Store-native; no PG migration)
- `services/ml/app/datastore/mapping.py` — added `Disposition.DATASTORE_NATIVE`;
  promoted the 6 board tables from `RESERVED` to live mappings (Prompt 16 removed
  from `RESERVED_NAMESPACES`/prefixes; Prompt 17 still reserved);
  `datastore_native_tables()` helper; `MAPPING_VERSION = 2026.07.19-1`.
- `services/ml/app/datastore/board_schema.py` — **single source of truth** for
  board table columns/types/indexes/search columns/append-only flags + JSON size
  limits (`MAX_JSON_BYTES=16384`, `MAX_SNAPSHOT_BYTES=32768`).
- `infra/catalyst/ds-schema/` — `generate_board_schema.py` (drift-checked
  generator), `provision_board_tables.py` (idempotent SDK provisioning + offline
  dry-run), `board-tables.schema.json` (generated), `README.md`.
- `infra/catalyst/ds-import/configs/*` regenerated (106 configs;
  disposition counts `{operational:93, ui_projection:13, analytics_only:9,
  not_imported:7, datastore_native:6}`).

### 1.2 Backend board service — `services/ml/app/board/`
- `references.py` — whitelist + read-only hydration (column introspection,
  parameterised, never interpolates a client table) + snapshot hash + diff.
- `repo.py` — Data Store persistence (process singleton, monotonic id
  allocation, soft-delete, append-only activity) + `board_cache()` singleton.
- `schemas.py` — typed request/response models.
- `guards.py` — role gates + synthetic write guard + fresh-confirmation gate.
- `service.py` — transactional-ordered mutations (domain write → append-only
  activity → version bump → post-commit signal), CRUD, branch, search-around.
- `searcharound.py` — capped graph expansion (reuses `app.graph.queries`) + cache
  + `benchmark_two_hop`.
- `promote.py` — hypothesis → review proposal (enum-safe best-effort AlertHistory).
- `export.py` — JSON export + PDF manifest to private Stratus + JSON import.
- `presence.py` — ephemeral presence (NoSQL doc + TTL, throttled).
- `router.py` — 34 routes; registered in `services/ml/app/main.py`.
- `signals.py` — added `EVENT_BOARD_ACTIVITY = "board.activity"`.

### 1.3 Frontend — `web/src/`
- `api/endpoints/board.ts` (+ `api/index.ts`, `api/client.ts` per-request headers).
- `config/destinations.tsx` (+ `App.tsx` routes + `BoardGate`).
- `components/board/*` — `BoardCanvas.tsx` (React Flow), `nodes/BoardNodes.tsx`,
  `panels/{SelectionInspector,ObjectPalette,HelperDrawer}.tsx`,
  `dialogs/{RationaleDialog,SearchAroundDialog}.tsx`, `SendToBoard.tsx`,
  `boardEncoding.ts`.
- `routes/board/*` — `MyBoards.tsx`, `BoardWorkspace.tsx`, `BoardTimeline.tsx`,
  `EvidenceTrail.tsx`, `useBoard.ts`.
- Integrations: `components/shell/PeekRail.tsx` (universal Send to Board),
  `routes/network/modes/ExploreMode.tsx`, `routes/cases/CaseFile.tsx`.

### 1.4 Datagen
- `datagen/investigation_board.py` + generated
  `datagen/fixtures/golden-001/investigation_board.json`.

### 1.5 Tests
- `services/ml/tests/test_board_datastore.py` (10 tests)
- `services/ml/tests/test_board_api.py` (26 tests)

---

## 2. Data Store tables & Catalyst service collections

### 2.1 Data Store tables (6, Data Store-native)
`InvestigationBoard`, `BoardNode`, `BoardEdge`, `BoardAnnotation`,
`BoardCollaborator`, `BoardActivity` (append-only).

Indexes (Prompt 16 §A.9), from `board_schema.py`:
- `BoardID` on every child table;
- `(RefTable, RefID)` and `CanonicalEntityID` reverse lookup on `BoardNode`;
- `(BoardID, BoardActivityID)` activity ordering for reconnect/replay;
- `OwnerActor`, `Status`, `CaseMasterID`, `ParentBoardID` on `InvestigationBoard`;
- unique `(BoardID, Actor)` on `BoardCollaborator`.

ExternalID prefixes: `board`, `bnode`, `bedge`, `bann`, `bcollab`, `bact`.

### 2.2 Other Catalyst application services used
| Service | Use | Config |
|---|---|---|
| NoSQL | `Presence` (ephemeral cursors/selections, TTL 30s); `BoardLayout` reserved for view prefs | `nosql/segments.json` |
| Cache | `idempotency` (safe retry), `lookup` (Search-Around results + export metadata), `ratelimit` (presence throttle) | `cache/namespaces.json` |
| Stratus | `report` bucket — private, presigned, versioned export objects (metadata/hash only) | `stratus/buckets.json` |
| Signals | `board.activity` published **after** the Data Store commit; data-minimised payload | `jobs/signals-rules.json` |
| AWS RDS (protected) | Search Around graph expansion + read-only reference hydration | `db.ro_conn()` |

---

## 3. API routes (34, prefix `/boards`)

CRUD/lifecycle: `POST /boards`, `GET /boards`, `GET /boards/{id}`,
`PATCH /boards/{id}`, `POST /boards/{id}/archive`, `POST /boards/{id}/lock`,
`POST /boards/{id}/branch`.
Nodes/edges/annotations: `POST|PATCH|DELETE /boards/{id}/nodes[/{nid}]`,
`.../edges[/{eid}]`, `.../annotations[/{aid}]`.
Collaboration: `GET|POST|DELETE /boards/{id}/collaborators[/{cid}]`,
`POST|GET /boards/{id}/presence`.
Analysis: `POST /boards/{id}/search-around`, `POST /boards/{id}/import/subgraph`,
`POST /boards/{id}/promote-edge/{eid}`.
Helpers: `GET /boards/{id}/activity`, `/table`, `/timeline`, `/diffs`,
`/benchmark/search-around`, `GET /boards/references/{ref_table}/{ref_id}`,
`GET /boards/meta/object-kinds`.
Export/import: `POST /boards/{id}/export`, `GET /boards/{id}/export/{export_id}`,
`POST /boards/import`.

Every mutating route enforces: coarse role gate (policymaker denied) + synthetic
write guard + resolved demo actor + optional `X-Idempotency-Key` + `If-Match`
version; lock/promotion/export additionally require a fresh confirmation.

---

## 4. Two-hop Search Around benchmark

Measured locally against the retained serving-subset AWS-RDS PostgreSQL via
`db.ro_conn()` (Windows dev host, single TestClient/uvicorn process, in-memory
Catalyst Cache fake). Command: `app.board.searcharound.benchmark_two_hop`.

| Run | Focal entity | Cap | Nodes | Edges | Latency | Cached |
|---|---|---|---|---|---|---|
| Cold | 2032 (degree 18) | 2 hops, top-15 fan-out | 19 | 171 | **443 ms** | no |
| Warm | 2032 | 2 hops, top-15 | 19 | 171 | **0 ms** | yes |

Target ≈ 2000 ms — **met** (443 ms cold, well under). Fan-out is capped to the
top-15 heaviest neighbours per hop (recursive-CTE `LIMIT`), so a two-hop import
stays legible (19 nodes) rather than a hairball. Expansion is over the id-keyed
canonical `EntityGraph`/`NetworkEdge` only — **no name matching**. Results are
cached in Catalyst Cache keyed by the graph model version (`drishti-graph@1.0.0`)
so a graph rebuild naturally invalidates them.

---

## 5. Collaboration test (activity replay + presence)

- **Correctness path — activity replay:** `GET /boards/{id}/activity?after_id=N`
  returns only committed events with `BoardActivityID > N`, strictly increasing.
  Test `test_after_id_replay_returns_only_new_events` proves a reconnecting client
  receives exactly the missed events (no committed change lost). The frontend
  `useBoardActivityPoll` polls every 4s and, on new committed activity, replays by
  re-syncing the board and shows a non-destructive "synced a change from X" notice.
- **Presence:** `POST /boards/{id}/presence` records an ephemeral, throttled
  (≤1 / 2s) cursor/selection into the NoSQL `Presence` segment as a single
  JSON document with a 30s TTL; `GET` prunes stale entries and returns the active
  roster. Presence is never written to the append-only activity history.
- **Broadcast:** `board.activity` is published to Catalyst Signals only **after**
  the Data Store mutation commits, carrying `{board_id, board_activity_id,
  version, kind, target, actor}` — never a full snapshot. Signals is a backend
  notification path; Data Store activity replay/polling remains the correctness
  path (WebSocket/SSE is an optional deployed transport gated behind a
  short-lived, Origin/BoardID-bound token — documented, not required for the demo).
- **Concurrency:** semantic edits use board `Version` / `If-Match` (409 on stale);
  node moves are last-writer-wins (no false conflict).

---

## 6. Export sample

`POST /boards/{id}/export {format:"json", confirm:true}` →
```
{ "export_id": "<hex>", "format": "json",
  "object_key": "board/<id>/export/<export_id>.json",
  "download_url": "<private presigned GET>", "expires_in_s": 900,
  "sha256": "<64 hex>", "watermark":
  "SYNTHETIC DEMO — DRISHTI Investigation Board — not real investigative data",
  "size_bytes": <n> }
```
The JSON document is the DRISHTI board schema (board header + version/time,
node inventory with provenance, evidence edges + sources, hypothesis edges with
rationale/author, source-version trail, activity digest). A `pdf` export returns
the same manifest for the deployed SmartBrowz Job to render to the same private
Stratus key. `GET /boards/{id}/export/{export_id}` re-presigns a fresh
short-lived URL. `POST /boards/import` reconstructs a board and **validates every
reference against the whitelist** — an arbitrary/unknown table name in the
document is dropped (test `test_import_rejects_arbitrary_table_in_document`).
Verified: `sha256` is 64 hex chars; watermark present; URL expires (900s).

---

## 7. RLS-disabled verification

AWS PostgreSQL **RLS and FORCE RLS remain disabled** as requested. The board adds
**no RLS policy** and **no operational PG migration** (board tables are Data
Store-native — `board-tables.schema.json` records `pg_migration: NONE`). The
access boundary is the **Catalyst-authenticated API**: `gateway_context.py`
verifies the signed context and `gateway_enforcement.py` injects the
server-trusted role; `app/board/guards.py` then enforces IO/Analyst/Supervisor
allow + policymaker denial + share/lock/promote permissions for every read,
mutation, collaboration and export route. Verified by
`test_board_datastore.py::test_provisioning_dict_documents_rls_disabled` and the
RBAC matrix in `test_board_api.py`.

---

## 8. Test results

```
python -m pytest tests/test_board_datastore.py tests/test_board_api.py -q
  -> 36 passed
python -m pytest --co -q  -> 400 tests collected (no import breakage)
web: npm run typecheck -> clean ; npm run build:fast -> built (3744 modules)
```
Coverage highlights (all passing):
- Data Store schema/index/search + AWS RLS-disabled posture + prefix uniqueness.
- Whitelisted reference hydration + **injection rejection** (arbitrary ref table
  → 422/404; unknown table pin → 422; tampered import node dropped).
- **RBAC matrix**: policymaker denied everywhere; IO owns own board; analyst
  blocked until explicitly shared; analyst cannot share; supervisor shares/locks/
  promotes. **Out-of-scope share** blocked (409) unless acknowledged.
  **Fresh-confirmation** required for lock/promote/export (428).
- Mutation + append-only `BoardActivity` (ids strictly increasing; repo refuses
  UPDATE/DELETE of an activity row); reconnect `after_id` replay.
- **Evidence-edge immutability** (PATCH 409) vs hypothesis editability; **rationale
  required** on create and **before promotion** (422). Promotion raises a review
  proposal and never creates a confirmed `NetworkEdge`.
- Optimistic concurrency (stale `If-Match` 409) + idempotent replay (same
  activity id).
- Locked-board rejection (423) + branch success (copies nodes, links parent,
  unlocked).
- Capped Search Around (hops >3 rejected at the boundary; fan-out ≤ cap;
  imported evidence edges carry `NetworkEdge:` id provenance — no name links).
- Live/snapshot/superseded-hash + reverse reference lookup.
- Export sha256 + synthetic watermark + retrievable short-lived URL; golden
  fixture import recreates 7 nodes / 3 evidence + 2 hypothesis edges.

---

## 9. Definition of Done — verification

| DoD item | Evidence |
|---|---|
| Create board, pin live objects, move/group/style, annotate, persist | `test_io_creates_and_reads_own_board`, canvas move persistence (`is_move_only`), annotations |
| Evidence & hypothesis edges visibly + structurally distinct | dashed vs solid renderer; `edge_class` column; immutability tests |
| Selection, Search Around, Table, History, Timeline helpers | inspector + `/table` `/activity` `/timeline` + Search-Around dialog |
| Send to Board from cases, entities, graph, map, analytics | PeekRail (universal) + CaseFile + ExploreMode |
| Capped 2-hop import performant, no hairball | §4 (443 ms, 19 nodes) |
| Concurrent users see committed edits + recover missed events | §5 replay + `after_id` test |
| Locking, branching, private source-linked export | §6 + lock/branch tests |
| IO/Analyst/Supervisor perms + policymaker denial via Catalyst API (PG RLS off) | §7 + RBAC tests |
| Every mutation attributable via append-only BoardActivity | append-only tests |
| Runs through Catalyst Auth/Gateway/Slate/AppSail with DS/NoSQL/Cache/Signals/Stratus | §2 + gateway middleware |
| AWS RDS retained only for protected graph/analytics; RLS stays disabled; no OCR / no direct browser-DB | §4, §7; browser calls Catalyst APIs only |

---

## 10. Palantir-reference compliance

Behavioural reference only: object-centric analysis, cross-application object
transfer (Send to Board), canvas helpers (Table/History/Timeline/Search Around),
history and source-linked exports. **No** Palantir names, branding, screenshots,
icons, layouts, proprietary text or visual assets are used — everything renders
with DRISHTI's Calm Authority tokens and iconography (lucide).

---

## 11. Screenshots

Screenshots are captured from the running dev app (`npm run dev` +
`uvicorn app.main:app`) and attached to the submission deck rather than committed
to the repo (the repo keeps no binary UI assets). Reproduce:
`/board` (My Boards + templates), `/board/{id}?tab=canvas` (four-region
workspace), `?tab=timeline` (scrub replay), `?tab=evidence` (Evidence Trail +
export). Focus mode: press `F`.

---

## 12. Limitations & deferrals

- **Optional grounded board assist** ("Explain this board" / "What am I missing?")
  is **not** enabled — it depends on the Prompt 11 / optional Prompt 15 RAG
  contract. The board is fully functional without it; when enabled, suggestions
  must be ghost nodes/edges that acceptance turns into a **hypothesis** (never a
  fact), each carrying source record ids + model/version.
- **`news_event`** node kind exists but is **not** a whitelisted reference table
  (the governed OSINT/News module — Prompt 8 — does not exist yet). When added it
  must render as unverified open-source material with source/version.
- **OCR / transcription / file-content extraction**: deferred. Evidence/document
  nodes expose metadata/provenance only; file **bytes are never read, parsed or
  copied** into board JSON.
- **PDF rendering** returns a manifest for the deployed SmartBrowz Job; byte
  rendering runs in Catalyst (not in the dev fake, which records metadata/hash).
- **Presence cursors** are recorded/rostered server-side (NoSQL/TTL) and surfaced
  as a live "N here" roster; pixel-level remote cursor overlays on the canvas are
  a visual enhancement left for polish.
- **Multi-instance id allocation**: board ids are allocated from a per-process
  monotonic counter seeded from the current max. Correct for the single-AppSail
  demo; a production multi-instance deployment would use a Data Store sequence.
- **WebSocket/SSE transport** is documented (short-lived Origin/BoardID-bound
  token) but not deployed; Data Store activity replay/polling is the correctness
  path used by the demo.

---

## 13. Exact Prompt 17 (Disaster Response) prerequisites

Prompt 17 can build directly on this phase. Concretely:
1. **Board object contract is extensible.** Add `hazard_event`, `risk_zone`,
   `resource`, `shelter`, `allocation` by (a) appending `RefSpec`s to
   `services/ml/app/board/references.py::_SPECS` (with correct PG tables +
   label/summary columns) and (b) adding the matching node kinds to `NODE_KINDS`
   and `NODE_KIND_STYLE` (frontend `boardEncoding.ts`). No board schema change is
   required to pin them.
2. **Disaster namespace still reserved.** `datastore/mapping.py`
   `RESERVED_NAMESPACES[Domain.DISASTER_RESPONSE]` + `RESERVED_EXTERNAL_ID_PREFIXES`
   still hold `HazardType/HazardEvent/HazardPrediction/HazardRiskZone/
   HydroMetReading/Resource/ReliefShelter/ResourceAllocation/EvacuationRoute/
   ResponsePlan/ResponseTask` — Prompt 17 promotes them (as Prompt 16 did for the
   board) and adds `board_schema`-style definitions if any are Data Store-native.
3. **`AlertHistory` reuse.** Promotion already writes enum-safe `AlertHistory`
   review items; Prompt 17's hazard alerts reuse the same table via its planned
   additive nullable `HazardEventID` (already noted in the mapping).
4. **Datagen.** Add a disaster-review board fixture alongside
   `datagen/investigation_board.py` (same deterministic pattern) — a board pinning
   a `HazardEvent` + its allocated resources for a multi-agency review.
5. **Map integration.** Map extract nodes + `Send to Board` from Map/Hotspots
   (via the universal PeekRail path) already work; a hazard risk-zone feature
   pins the same way once its RefSpec exists.


---

## Prompt 23 live-evidence addendum (2026-07-23) — additive, historical text unchanged

Live on Catalyst (see `docs/phase-reports/PHASE_23_REPORT.md`):

- The Investigation Board tables are **provisioned in Catalyst Data Store** (live):
  `InvestigationBoard`, `BoardNode`, `BoardEdge`, `BoardAnnotation`, `BoardCollaborator`,
  `BoardActivity`.
- The **Data Store operational path is proven live** (insert + Signal-driven update on
  `PredictionRequest`), which is the same Catalyst Data Store the board uses at runtime.
- **Honest caveat (report §5):** a dedicated Board *business* API operation was not
  separately API-captured this session — the board is a Data Store-backed UI feature
  exercised through the live Slate frontend (`https://drishti-uryfmaue.onslate.in/`).
  No board behaviour was faked.


### Update (2026-07-23) — Board is now fully live on Catalyst

The earlier addendum's caveat ("a dedicated Board business API operation was not
separately API-captured") is **resolved**. Live Board CRUD is proven end-to-end on the
deployed AppSail over Catalyst Data Store: `GET /boards` → 200, `POST /boards` → 201
(`board_id 90005`), `GET /boards/{id}` → 200, `POST /boards/{id}/annotations` → 201 (JSON
columns round-trip), `policymaker → 403`. See `docs/phase-reports/PHASE_23_REPORT.md` §3.9
and `artifacts/phase-23/board-disaster3.log`. The fixes that unblocked it (ZCQL ≤300
pagination, Catalyst datetime format, dict/list↔JSON round-trip) are in
`services/ml/app/datastore/repository.py`.
