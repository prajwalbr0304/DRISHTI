# PHASE 04 REPORT — Canonical identity and entity-resolution workflows

Status: **Complete**
Date: 2026-07-17
Target: **AWS RDS PostgreSQL 17.10** — database `drishti`, owner/app role
`drishti_admin`, read-only role `drishti_readonly`. Hackathon access mode
(RLS disabled, API-only, synthetic marker `synthetic_hackathon`).

> No secret values are printed, logged, or committed. `DATABASE_URL` is resolved
> at runtime; only the masked target (`aws-rds:host/db`) is ever logged.

---

## 1. Outcome summary

Built the **canonical identity + entity-resolution** layer on top of the Phase 1
schema: a typed FastAPI `identity` module (person/organisation/entity CRUD +
search, governed aliases/identifiers/contacts/addresses, case-party roles,
candidate generation, human review, and **reversible** merge/split), a migration
that backfills legacy person FKs from canonical linkage (never names) and proves
every graph-person node is canonically linked, and the removal of **all four**
name-equality identity joins from the read paths. A React entity-resolution
review inbox + canonical profile page complete the workflow.

| Definition of Done | Result |
|---|---|
| Stable canonical identities power case and graph relationships | **Verified** — 100% of graph-person nodes link to a `CanonicalEntity`; case links now go through `CasePartyRole.CanonicalPersonID`; risk features map entities to accused via canonical ids |
| Name-based case linking is removed | **Verified** — 4 name-equality joins replaced with canonical joins; `rg` + a code-scan test confirm none remain |
| Entity merges are reviewed, audited, and reversible | **Verified** — candidates are proposals only (never auto-merged); merge repoints references + records `EntityMergeHistory`; unmerge restores the exact references (tested) |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/012_identity_resolution.sql` — idempotent Phase 4 migration:
  - backfills `Accused`/`Victim`/`ComplainantDetails.CanonicalPersonID` from
    `CasePartyRole` (via `CasePartyRoleID` / `LegacyRefTable`+`LegacyRefID`) —
    **canonical linkage, never names**;
  - `fn_assert_graph_persons_linked()` — raises unless every `EntityGraph`
    person node links to a `CanonicalEntity` (or is explicitly
    `synthetic_unverified`);
  - `fn_identity_link_stats()` — canonical coverage stats (admin/report);
  - `vw_related_cases_by_person` — cases related through a **shared canonical
    accused person** (replaces `AccusedName`-equality joins);
  - seeds up to 15 **pending** `EntityResolutionCandidate` rows (same display
    label / distinct persons) for the review inbox — proposals only;
  - indexes `gin_canonperson_label_trgm`, `idx_canonperson_status`,
    `idx_erc_pair` for fast search + candidate generation at 200k+ rows;
  - ends with `fn_disable_rls_all_app()` + `fn_assert_rls_disabled()`.

### New backend module `services/ml/app/identity/`
- `schemas.py` — typed request/response models.
- `service.py` — internal `_fn(conn, ...)` helpers + public wrappers (open
  `rw_conn`/`ro_conn`). Person/org CRUD + search; alias/identifier/contact/
  address add/delete (sensitivity-classified); case-party role add/update/
  remove; **targeted** candidate generation (`_candidate_pairs_for_person`
  trigram + exact-first ordering, `_candidate_pairs_duplicate_labels`);
  `_review_candidate` (accept→merge / reject / create_new); reversible
  `_merge`/`_unmerge` via `_repoint_person_refs`/`_restore_person_refs` that
  store the exact moved PK ids in `EntityMergeHistory.BeforeState`. Every
  mutation writes a same-transaction audit event.
- `router.py` — 23 endpoints under `/identity` (reuses the intake read/write
  guards: localhost + synthetic-DB, role gates). Registered in `main.py`.

### Modified backend (name-equality joins → canonical joins)
- `app/risk/features.py` — the `EntityGraph.Label = Accused.AccusedName`
  `ROW_NUMBER` rank-match is replaced by
  `EntityGraph.CanonicalEntityID → CanonicalEntity.CanonicalPersonID →
  CasePartyRole(accused) → MIN(LegacyRefID)` (0.7s, 16,246 entities mapped).
- `app/cases/explorer.py` `case_network` — related cases now come from a shared
  **canonical** accused person (`CasePartyRole`), "via" = person label/ref.
- `app/geo/service.py` `case_links` — map arcs use the same canonical shared-
  person join.
- `app/graph/explorer.py` `entity_detail` — criminal history via the entity's
  `CanonicalEntityID → CanonicalPersonID → CasePartyRole → cases`; the
  name-match fallback is removed (a direct `AccusedMasterID` link remains as a
  legacy-only fallback).

### New tests
- `services/ml/tests/test_identity.py` — 14 integration tests (rolled back).

### New / modified frontend (`web/`)
- `src/api/endpoints/identity.ts` (23 methods) + `src/api/types.ts` `Identity*`
  types + wired `api.identity` into `src/api/index.ts`.
- `src/routes/review/entities/EntityResolution.tsx` — review inbox.
- `src/routes/entities/CanonicalProfile.tsx` — canonical profile + merge/unmerge.
- `src/routes/review/entities/EntityResolution.test.tsx` — component test.
- `src/App.tsx` — routes `/review/entities`, `/people/canonical/:cpid`.
- `src/routes/cases/subpages/PeoplePage.tsx` — canonical cards link to profiles.
- `src/routes/entities/EntityExplorer.tsx` — "Entity resolution" link.

---

## 3. Database objects added (migration 012)

- Functions: `fn_assert_graph_persons_linked()`, `fn_identity_link_stats()`.
- View: `vw_related_cases_by_person`.
- Indexes: `gin_canonperson_label_trgm`, `idx_canonperson_status`, `idx_erc_pair`.
- Data: up to 15 seeded pending `EntityResolutionCandidate` rows (idempotent —
  only when the inbox is empty).
- Applied to AWS RDS and re-applied (idempotent). NOTICEs on re-run:
  `Resolution inbox already has 15 pending candidate(s); no seed.` ·
  `IDENTITY CHECK PASSED: all graph-person nodes are canonically linked...` ·
  `HACKATHON RLS CHECK PASSED`.

---

## 4. API endpoints added (prefix `/identity`, 23 routes)

Reads (any role except policymaker): `GET /stats`, `GET /persons`,
`GET /persons/{id}`, `GET /organisations`, `GET /resolution/candidates`.

Writes (localhost + synthetic guarded): `POST /persons`, `PATCH /persons/{id}`,
`POST/DELETE /persons/{id}/aliases`, `.../identifiers`, `.../contacts`,
`.../addresses`, `POST /organisations`, `POST /cases/{id}/parties`,
`PATCH/DELETE /parties/{id}`, `POST /resolution/generate`.

Review-role writes (supervisor/super_admin): `POST /resolution/candidates/{id}/review`,
`POST /persons/{id}/merge`, `POST /persons/{id}/unmerge`.

## 5. Screens added / changed

- `/review/entities` — **entity-resolution review inbox**: pending candidates
  shown **side-by-side** (Person A vs Person B, method, score, match feature)
  with *Same person → merge into A* / *Different people* / *Reject*; a *Generate
  candidates* action; a canonical-coverage stats panel; and a person search +
  create-person panel.
- `/people/canonical/:cpid` — **canonical profile**: identity summary, case
  roles (linked to case files), aliases/identifiers/contacts/addresses (each
  with a **sensitivity** badge) + add-alias, and a Resolution panel with
  merge-by-id and the **merge/split history** including an **Unmerge** (reverse)
  action.
- Per-case People cards link to the canonical profile; the People explorer links
  to the resolution inbox.

---

## 6. Commands run and results

| Command | Result |
|---|---|
| Apply `012_identity_resolution.sql` (AWS RDS, ×3 incl. idempotency) | PASS — backfill + graph-link check + RLS check pass; seed idempotent |
| Build identity indexes (standalone) | `gin_canonperson_label_trgm` 0.8s, `idx_canonperson_status` 0.4s, `idx_erc_pair` 0.0s |
| `pytest tests/test_identity.py` | **14 passed** (~26s) |
| `pytest` (cases, graph, geo, contract, identity, intake, hackathon) | **91 passed, 3 failed, 1 skipped** — the 3 failures are the pre-existing empty-derived-data cases (hotspots / emerging alerts / graph-hidden feed), unrelated to Phase 4 |
| Risk canonical accused-map join (timed) | 0.7s, 16,246 entities mapped |
| `npm run typecheck` (web) | PASS |
| `npx vitest run` (web) | **23 passed** (6 files) |
| `npm run build` (web) | PASS (bundle emitted) |
| Bundle secret scan (`web/dist`) | PASS — no secret / Supabase / DB-URL |

### `test_identity.py` coverage (14)
Person create/get/search/idempotent · alias/identifier/contact/address with
sensitivity (+ invalid sensitivity rejected) · organisation create/search ·
case-party add/update/remove (+ unknown-party allowed, identity-or-unknown
required) · **same name / different person stays separate** (candidate proposed,
neither merged) · review-reject keeps persons distinct · **merge moves refs +
unmerge restores** (case-party role + alias repointed then restored) · review-
accept merges · merge rejects self / already-merged · **case_network links via a
shared canonical person** · `fn_assert_graph_persons_linked` passes · **no
name-based identity linking remains** (source scan).

---

## 7. Migration counts + graph-link proof (AWS RDS, `fn_identity_link_stats()`)

| Metric | Value |
|---|---:|
| CanonicalPerson | 210,883 |
| — resolution_status = merged | 10 |
| CanonicalOrganisation | 60 |
| CanonicalEntity | 223,161 |
| CasePartyRole | 374,272 |
| **EntityGraph person nodes** | **205,610** |
| **EntityGraph person nodes canonically linked** | **205,610 (100%)** |
| NetworkEdge | 2,411 |
| NetworkEdge with provenance status | 2,411 (100%) |
| Accused total | 164,860 |
| Accused with CanonicalPersonID | 147,926 |
| Accused without CanonicalPersonID (unknown/unidentified party) | 16,934 |
| Pending resolution candidates (seeded) | 15 |
| Merge/split history rows | 13 |

**Proof (DoD):** `fn_assert_graph_persons_linked()` returns without raising —
every `EntityGraph` person node links to a `CanonicalEntity` (or is explicitly
`synthetic_unverified`). The 16,934 Accused rows without a `CanonicalPersonID`
are **genuinely unidentified** (their `CasePartyRole` is an unknown party) — the
canonical backfill correctly leaves them unlinked rather than inventing an
identity. No row is linked by name.

---

## 8. Security + data-quality checks

- **No name-based identity linking**: all four name-equality joins removed and
  guarded by a code-scan test; cross-case links go through canonical identity.
- **Never auto-merge**: `EntityResolutionCandidate` rows are proposals; a merge
  happens only through an explicit reviewer action (accept / merge endpoint).
  Same-name/different-person persons stay separate (tested).
- **Reversible + audited merges**: `_merge` records the exact repointed PK ids in
  `EntityMergeHistory.BeforeState`; `_unmerge` restores them and removes the
  merge alias; both write `audit_logs` events (same transaction).
- **Sensitivity classification**: identifiers/contacts/addresses carry a
  `Sensitivity` (default `restricted`); the profile UI shows it; invalid values
  are rejected.
- **Protected attributes**: `IsJuvenile` is surfaced as protected and is not a
  resolution/merge input; caste/religion are not part of the identity schema.
- **Hackathon access mode preserved**: migration re-asserts RLS disabled + NO
  FORCE; all writes remain localhost + synthetic-DB guarded; no secret in the
  frontend bundle; browser → FastAPI only.

---

## 9. Known limitations

1. **Cross-unit filtering is presentation-only**: the demo view/role gates
   (policymaker blocked from identity screens) are UX simulation, consistent in
   the UI, but per-unit/case authorization is deferred to the auth phase (not a
   security boundary).
2. **Candidate generation is name-similarity based** (exact label + pg_trgm
   fuzzy) as a *review signal*. It deliberately avoids identifier/phone equality
   as an automatic identity key; richer blocking features are future work.
3. **Merge repointing** covers the core identity FK tables (case-party roles,
   canonical entity, legacy Accused/Victim/Complainant, aliases/identifiers/
   contacts/addresses, statements, bail, property, gang membership). Any table
   added later that references `CanonicalPersonID` must be added to
   `_PERSON_FK_TABLES` to remain merge-reversible.
4. **AWS RDS is small**: unbounded self-joins over the 210k-person table are slow
   — identity search + candidate generation are deliberately targeted/indexed.
5. **Risk offender scoring remains synthetic-demo-only** (Phase 1 rule): the
   canonical join fixes *how* entities map to accused, but the offender risk
   batch is not re-run operationally (deferred to Phase 13).

---

## 10. Next-phase (Prompt 5) prerequisites

- Canonical identity is stable and API-exposed; Prompt 5 (digital evidence
  upload → S3) can link `EvidenceItem`/`EvidenceEntityLink` to
  `CanonicalEntity`/`CanonicalPerson` created here.
- `EvidenceEntityLink` (migration 007) already references `CanonicalEntity`;
  Phase 4 guarantees those entities exist and are linked.
- Hackathon access mode (RLS disabled + verified, API-only, synthetic guard,
  audit) is intact; new evidence writes reuse the same guards + audit helper.
- Migrations 005/007/011/012 own the repeatable RLS + graph-link + grant
  verification; new migrations must keep those assertions passing.

---

## 11. Definition of Done — verification

- [x] Stable canonical identities power case and graph relationships (100% graph-person linked; case/geo/risk read paths canonical).
- [x] Name-based case linking is removed (4 joins replaced; code-scan test passes).
- [x] Entity merges are reviewed, audited, and reversible (candidate review → merge; `EntityMergeHistory`; unmerge restores refs — tested).
