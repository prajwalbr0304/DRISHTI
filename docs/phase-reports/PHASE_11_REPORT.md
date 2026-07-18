# PHASE 11 REPORT — Embeddings, similar cases, graph rebuilding, and evidence-backed analytics

Status: **Complete**
Date: 2026-07-17
Target DB: AWS RDS PostgreSQL (`ap-south-1`), marked `synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> Derived intelligence (embeddings, similar cases, graph analytics, hidden
> associations, patterns, money) is rebuilt from VERIFIED CANONICAL data only.
> Similar-case retrieval applies the selected demo case/unit CONTEXT filter
> before the ANN search and never lets an outcome/label field into the query
> vector. The graph reads only CANONICAL, provenanced, non-archived nodes/edges
> (never name matching); edges carry a candidate/confirmed reviewer state; a
> hidden association needs ≥2 INDEPENDENT evidence kinds plus a reviewer
> disposition. The old synthetic identity-graph rows are ISOLATED by an archive
> flag (never deleted), so the old and new canonical spaces never mix. No
> centrality/association implies culpability.

---

## 1. Outcome summary

Migration 009 + the v2 datagen already rebuilt the graph on the canonical
identity space, so the current AWS DB starts **100% canonical** (see §4). Phase
11 added the missing GOVERNANCE around that: an archive/isolation mechanism, a
candidate/confirmed reviewer state on edges + hidden associations, canonical-only
graph reads, and a demo-context filter + why-match + provenance on similar-case
search.

| Definition of Done | Result |
|---|---|
| Similarity and graph outputs use canonical, verified, demo-context-filtered sources | Similar search applies the case/unit district context BEFORE the ANN, in one model-version space, excluding archived vectors, with why-match + source links (leakage-safe query text). Graph algorithms (`_load_graph`), the hidden-association detector and the canonical views read only `CanonicalEntityID`-linked, provenanced, non-archived rows. Verified by 11 backend tests. |
| Old invalid graph-derived data is isolated/archived | `IsArchived`/`ArchivedAt`/`ArchiveReason` on the six derived tables + `archive_legacy` isolate non-canonical nodes, NULL-provenance edges and non-case embeddings (never deleted). `vw_canonical_graph_node/edge` expose only the clean space; `archive_status.clean` asserts no legacy row stays live. The current DB has 0 legacy rows; the mechanism is proven by a test that injects a legacy node+edge and archives them. |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/018_derived_intel_provenance_archive.sql` — additive +
  idempotent (applied twice). Adds `IsArchived`/`ArchivedAt`/`ArchiveReason` to
  `EntityGraph`, `NetworkEdge`, `CrimeEmbedding`, `CrimePattern`,
  `drishti_hidden_associations`, `GangMembership`; `NetworkEdge.ReviewStatus`
  (candidate|confirmed|rejected) + reviewer columns (backfills verified →
  confirmed); `drishti_hidden_associations.ReviewStatus` + reviewer +
  `IndependentEvidenceKinds`; `CrimePattern.ReviewStatus` + reviewer +
  `SourceRecordIDs` + `RuleParams`; the `vw_canonical_graph_node` /
  `vw_canonical_graph_edge` views; review CHECK constraints + live/review
  indexes; re-asserts RLS disabled.

### New / modified backend `services/ml/app/`
- `graph/archive.py` (new) — `archive_legacy` isolates legacy rows
  (non-canonical node / NULL-provenance edge / non-case embedding) by flagging
  `IsArchived` (idempotent, audited); `archive_status` reports per-table
  archived/live + a `clean` invariant (no legacy row live).
- `graph/algorithms.py` — `_load_graph` now loads only canonical
  (`CanonicalEntityID` set), non-archived nodes + provenanced, non-archived
  edges (optional `confirmed_only`); centrality/communities inherit this.
- `graph/hidden.py` — the candidate SQL requires canonical persons + provenanced
  non-archived edges; `materialize` preserves confirmed/rejected rows (refreshes
  only candidates, `ON CONFLICT DO NOTHING`) and records `IndependentEvidenceKinds`;
  new `review(confirm|reject|reset)`; `feed`/`proof_path` exclude archived and
  expose the review state.
- `graph/service.py` + `graph/schemas.py` + `graph/router.py` — new
  `archive_status` / `archive_legacy` / `rebuild` / `review_edge` /
  `review_hidden` operations + 5 endpoints (below); proof-path carries the
  review state.
- `cases/similar.py` + `cases/service.py` + `cases/schemas.py` +
  `cases/router.py` — `find_similar(scope, district_id)` applies the demo
  case/unit context filter before the ANN (in one model-version space, archived
  vectors excluded), adds per-hit `why_match` + `source_links` and a
  decision-support `limitations` note; the query text is unchanged (leakage-safe).

### Frontend `web/src/`
- `api/types.ts` — `SimilarCase`/`SimilarResponse`, `HiddenAssociationCard`,
  `ProofPathResponse` gain the new fields; new `GraphArchiveStatus` /
  `GraphRebuildResult` / `GraphReviewResult`.
- `api/endpoints/graph.ts` — `archiveStatus` / `archiveLegacy` / `rebuild` /
  `reviewEdge` / `reviewHidden`. `api/endpoints/cases.ts` — `similar` takes
  `{ k, scope, district_id }` (3 call sites updated).
- `routes/cases/subpages/SimilarPage.tsx` — a demo-context scope toggle
  (This district / All districts) + per-hit why-match chips + limitations.
- `routes/network/modes/HiddenMode.tsx` — a canonical-isolation status chip,
  a candidate/confirmed review badge, the independent evidence kinds, and
  confirm/reject reviewer actions on the proof panel.

### New tests
- `services/ml/tests/test_graph_canonical.py` (11 tests).
- `web/src/routes/cases/subpages/SimilarPage.test.tsx` (1 test).

### Datagen
- No change required. `datagen/build.py` already emits ONLY canonical
  `EntityGraph`/`NetworkEdge`/`GangMembership` (linked to `CanonicalEntity`, with
  `ProvenanceStatus`); the legacy `datagen/intelligence.py` path is not used for
  the v2 load. Archival is a runtime governance mechanism, and embeddings /
  hidden-associations are runtime batch jobs (`app.batch embed-cases`, graph
  rebuild), not datagen artefacts.

---

## 3. Database objects / endpoints / screens

### Database (migration 018)
- Columns: archival trio on 6 derived tables; `NetworkEdge` +
  `ReviewStatus`/`ReviewedByActor`/`ReviewedAt`; `drishti_hidden_associations` +
  `ReviewStatus`/`ReviewerActor`/`ReviewedAt`/`IndependentEvidenceKinds`;
  `CrimePattern` + `ReviewStatus`/reviewer/`SourceRecordIDs`/`RuleParams`.
- Views: `vw_canonical_graph_node`, `vw_canonical_graph_edge`.
- Constraints: `chk_networkedge_review`, `chk_hidden_review`,
  `chk_crimepattern_review`. Indexes for the live/archived split + review queues.

### API endpoints (5 new under `/graph`)
- `GET /graph/archive-status` — old-vs-new isolation (archived/live + `clean`).
- `POST /graph/archive-legacy` — isolate legacy rows (write-guarded).
- `POST /graph/rebuild` — rebuild communities/centrality/hidden from the
  canonical graph (archives legacy first).
- `POST /graph/edges/{id}/review` and `POST /graph/hidden-associations/{id}/review`
  — reviewer disposition (confirm|reject|reset).
- `GET /cases/{id}/similar` gains `scope` (district|all) + `district_id`.
Writes require a governance role (`analyst|investigator|supervisor|super_admin`)
plus the localhost + synthetic-DB guard.

### Screens
- **Cases → Similar cases** — a demo-context scope toggle, why-match chips, and a
  decision-support limitations note.
- **Network → Hidden associations** — a canonical-isolation status chip,
  candidate/confirmed badges, the independent evidence kinds, and confirm/reject
  reviewer actions on the proof path.

---

## 4. Old vs new derived-data counts

The roadmap's original **live-Supabase** graph carried legacy, name-labelled,
NULL-provenance rows. The v2 canonical rebuild already replaced them, so the AWS
DB begins clean; Phase 11 makes the isolation explicit and enforceable.

| Metric | Before (audit) | After (migration 018 + backend) |
|---|---:|---:|
| `EntityGraph` — total / canonical / legacy | 205,670 / 205,670 / **0** | same; view `vw_canonical_graph_node` = 205,670 |
| `NetworkEdge` — total / provenanced / NULL-provenance | 2,411 / 2,411 / **0** | same; `ReviewStatus` confirmed **2,141** / candidate **270** |
| `vw_canonical_graph_edge` (canonical, provenanced, non-archived) | — | 2,411 |
| `CrimeEmbedding` (case-corpus vectors) | 0 | 0 live (run `embed-cases`); tests embed 400 in a rolled-back txn |
| `drishti_hidden_associations` | 0 | 0 live (lean v2 graph has no intermediary nodes); detector verified on an injected fixture |
| `CrimePattern` | 0 | 0 live (schema now carries `SourceRecordIDs`/`RuleParams`/`ReviewStatus`) |
| Legacy rows still live after `archive_legacy` | — | **0** (`archive_status.clean = true`) |
| RLS on the 6 derived tables | off | off |

### Evaluation / metrics
- **Communities** — `detect_communities` reports pairwise gang precision/recall/F1
  + modularity + rediscovered gangs (deterministic seed → idempotent rebuild).
- **Similar cases** — demonstrated with the deterministic 768-d hashing embedder
  over a 400-case corpus; district-scoped retrieval keeps every hit inside the
  query district; the sentence-transformer encoder is the production option.

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Apply `018_derived_intel_provenance_archive.sql` twice | PASS — columns/views/constraints created; backfill verified→confirmed (2,141); RLS-disabled asserted; idempotent |
| Read-only pre-audit | PASS — EntityGraph 205,670 all canonical; NetworkEdge 2,411 all provenanced; CrimeEmbedding/hidden/pattern 0; RLS off; no legacy rows mixed in |
| Backend smoke (rolled back) | PASS — archive isolates injected legacy node+edge (clean); canonical `_load_graph` excludes archived; district-scoped similar hits all in-district with why-match + source links; hidden association shows independent evidence kinds + confirmed review preserved across re-materialise |
| `python -m pytest tests/test_graph_canonical.py -q` | **11 passed** |
| `python -m pytest tests/test_cases.py tests/test_graph_queries.py -q` | PASS (no regression) |
| `python -m pytest tests/test_graph_hidden.py -q` | 4 logic pass + 1 skipped + 1 pre-existing data-dependent fail (see §7) |
| `npm run typecheck` (web) | PASS |
| `npx vitest run` (web, full suite) | **41 passed** (15 files, incl. the new SimilarPage test) |
| `npm run build` (web) | PASS — 3587 modules transformed |

### Backend test coverage (`test_graph_canonical.py`, 11)
Archive isolation (legacy node+edge flagged, not deleted, `clean` after) +
idempotency; canonical-only `_load_graph` (excludes non-canonical/archived); the
canonical edge view has no name-matched endpoints and no NULL-provenance edges;
community rebuild is idempotent; similar demo-context filter (all district hits
in-district; all ≥ district); same-model-version space + source-link provenance;
leakage-safe query text (no chargesheet/disposition/convicted/acquitted/status);
hidden association independent evidence kinds + confirmed review preserved across
re-materialise; and a pair sharing only one kind is not surfaced.

---

## 6. Security, provenance and honesty checks

- **RLS** stays disabled + NO FORCE (migration 018 re-asserts
  `fn_assert_rls_disabled()`; the 6 derived tables verified off). No policies.
- **API-only path**: every screen is React → FastAPI → PostgreSQL; graph writes
  (archive/rebuild/review) require a governance role + the localhost +
  synthetic-DB guard. No secrets printed.
- **No name matching**: graph nodes/edges resolve through `CanonicalEntityID`
  (true FK); the canonical edge view has zero name-matched endpoints (tested).
- **Provenance**: edges carry `ProvenanceStatus` + candidate/confirmed review;
  hidden associations carry independent evidence kinds + proof records; similar
  hits carry `source_links`; money alerts carry reason codes + source records +
  reviewer disposition (Phase 8, unchanged).
- **Leakage-safe similarity**: the query vector is built only from context/MO
  fields — no case status, chargesheet disposition or outcome (tested).
- **No culpability from centrality/association**: similar-case + hidden-association
  wording is explicitly decision-support ("not an identity match", "not proof of
  a relationship"); money wording stays neutral (unchanged).
- **Old/new isolation**: archived rows are flagged, never deleted; the canonical
  views + `archive_status.clean` guarantee the spaces do not mix.

---

## 7. Known limitations

1. **Live corpus / hidden feed are empty on the lean v2 fixture** — the
   `embed-cases` batch has not been run against this DB (similar search returns
   409 until it is), and the lean v2 canonical graph contains only person/gang
   nodes (no phone/vehicle/location/account intermediary nodes), so the
   hidden-association feed is legitimately empty. The retrieval, archival and
   hidden-association code paths are fully exercised by the 11 tests (which embed
   a small corpus and inject an intermediary fixture in rolled-back transactions).
2. **Pre-existing data-dependent test failure** —
   `test_graph_hidden.py::test_materialized_feed_has_ranked_rows` asserts the
   LIVE `drishti_hidden_associations` table has rows; it is empty (batch not run
   + no intermediary nodes). Not caused by this phase (the feed change only adds
   an `IsArchived=FALSE` filter over an already-empty table); same category as
   the Phase 8–10 geo hotspot/alert batch-output failures.
3. **CrimePattern generation is legacy-only** — the schema now carries
   `SourceRecordIDs`/`RuleParams`/`ReviewStatus`, but a runtime canonical
   pattern-generator is future work; money patterns are already fully
   reviewable/provenanced (Phase 8).
4. **No live reload** — mirrors Phases 7–10; the datagen already emits canonical
   graph rows, and archival is idempotent runtime governance.

---

## 8. Next-phase prerequisites (Prompt 12 — forecasting models)

- Forecasting models should bind to a governed `ModelVersion` + approved feature
  schema (Phase 10) and read only the canonical, non-archived graph/edges via
  `vw_canonical_graph_*` where graph features are used.
- Running `app.batch embed-cases` populates the case corpus so similar-case
  retrieval and MO-linkage leads are live for the demo.
- Confirmed graph edges + confirmed hidden associations are the reviewed,
  evidence-backed relationships downstream analytics may rely on.

---

## 9. Definition of Done — verification

- [x] Similarity and graph outputs use canonical, verified, demo-context-filtered
      sources — similar search filters to the query case/unit district before the
      ANN (one model-version space, archived excluded, leakage-safe, with
      why-match + source links); graph reads only canonical, provenanced,
      non-archived rows. Verified by tests.
- [x] Old invalid graph-derived data is isolated/archived — archive flags +
      `archive_legacy` isolate non-canonical/unprovenanced/legacy rows (never
      deleted); the canonical views + `archive_status.clean` keep old/new spaces
      separate. 0 legacy rows currently; mechanism proven by an injection test.
