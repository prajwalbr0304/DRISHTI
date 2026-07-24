# DRISHTI — Phase / Prompt 25 Report

**Integrated security, scale, recovery and final hackathon release**

- Phase: 25 · Status: **PENDING** (strict acceptance non-zero — one mandatory live gate open)
- Date: 2026-07-24 · Project: **DHRISTI** `48361000000030003` (India DC) · AWS acct `…5713` (ap-south-1)
- Release label: **HACKATHON-DEMO (synthetic) on Zoho Catalyst — never production**

---

## 0. Executive summary (honest)

Almost everything Prompt 25 asks for is **genuinely proven**: the full local test tiers,
the security/authorization *logic*, the real AWS TabFM/TimesFM execution + cleanup, the
bounded live load with an honest capacity model, the investigation-time metric, and the
backup/recovery/rollback drills are all green, and the strict local release gate is
**16/16 RELEASE_CANDIDATE**.

**Prompt 25 nonetheless remains PENDING** because one mandatory *live* requirement is not
met at the deployed edge: the deployed `gateway_api` runs with **`DRISHTI_DEMO_AUTH=true`**,
which mints a full-access `super_admin` context for **any sessionless caller** (verified:
unauthenticated `GET /api/cases` returns synthetic case data). So live **per-role deny** and
real Catalyst Authentication are **not enforced** in the current deployment. Per the release
rule, a mandatory live gate that is not proven keeps the phase Pending. Remediation is
precise and small (see §J / `POST_HACKATHON_BACKLOG.md` RB-1..RB-4).

This report **does not** declare production readiness and does **not** yet declare
hackathon-demo readiness under strict acceptance.

---

## A. Full test separation (run + reported separately)

| Suite | Env | Result | Evidence |
|---|---|---|---|
| Unit / component (frontend) | local | **65 passed** (21 files) | `artifacts/phase-25/test-runs/frontend-vitest.log` |
| Backend API + repository contract (DB-free mandatory tier) | local | **378 passed, 211 skipped** | `…/backend-offline-full.log` |
| Disposable integration (synthetic RDS, rollback) | local+RDS | **578 passed, 7 skipped, 4 deselected(slow)** | `…/backend-db-integration-final.log` |
| Live Catalyst integration | live | **PARTIAL** — health/frontend/bypass/CORS pass; edge authz fails (DEMO_AUTH) | `artifacts/phase-25/live-catalyst-boundary.json` |
| Live AWS model integration | live | **PASS** — TabFM+TimesFM on Tesla T4 + cleanup | `live-integration-reproof.log`, `forecast-timesfm-only.log`, `aws-inventory.json` |
| Browser E2E | local (deterministic) | **27 passed** | `artifacts/phase-22/release-gate-logs/e2e.log` |
| Authorization / security | local | **PASS** — 34-case matrix + gateway tests + scans | `artifacts/phase-21/authorization-verification.json` |
| Synthetic data quality / lineage | local+RDS | **PASS** (scenarios/governance/geo-jurisdiction/canonical) | in DB suite |
| Performance / load | live (bounded) | **PASS** — 12 workloads, 0 err @ c=6 | `artifacts/phase-25/load/load-results.json` |
| Backup / recovery / rollback | local+live | **PASS** | `artifacts/phase-25/recovery/recovery-exercise.json` |
| Cost / cleanup | live | **PASS** — 0 SageMaker endpoints | `artifacts/phase-25/aws-inventory.json` |

**Regressions fixed this phase (root-caused, not weakened):**
1. `test_internal_functions.py` ×2 — asserted `record['State']` but production `service.py` intentionally uses lowercase `state` (live Catalyst Data Store rejects capitalized columns; Signals filter on `state`). Fixed the tests to the live schema.
2. `test_gateway_authz.py::test_appsail_pinned_to_single_instance` — asserted the old `must_not_set_for_crud` DB-free posture; Prompt 23 Option A moved `DATABASE_URL` to optional. Fixed to the real **DB-free-boot** invariant (`DATABASE_URL` not required + present as optional).
3. `preflight_deploy.py` — same stale `must_not_set_for_crud` block; fixed to the DB-free-boot invariant (the pipeline can deploy again).
4. `app/forecast/backtest.py` — **real bug**: the rolling-origin backtest scored empty future/partial months (2026-01..07, past the data end 2025-12) as actuals once wall-clock advanced, giving `WAPE=2442`. Added `_trim_incomplete_tail` so only real observed months are scored → forecast suite 24 passed, `beats_all_baselines` restored.
5. `artifacts/phase-24/model-runs/baseline-compare.json` — was UTF-16 (BOM), failing the JSON validity check; re-encoded to UTF-8.

## B. Mandatory end-to-end journeys

Full per-journey live/offline status is in **`HACKATHON_DEMO_CHECKLIST.md`**. Summary:
**Live (full/partial):** 1, 5, 9, 10 (model), 12, 13, 15. **Offline-proven (logic+tests green,
live-edge gap):** 2, 3, 4, 6, 7, 8, 11, 14. **Open live gaps:** RB-1 (edge authz → journeys
1/2), RB-2 (live NL query `/api/ask` 502 → journey 7), RB-3 (deployed AppSail→adapter → journey 10).

## C. Security and authorization

- **Full role/rank/unit/resource/action matrix:** 34 cases exercised through the real
  `app.org.scope` decision model — **PASS** (`artifacts/phase-21/authorization-verification.json`).
- **Boundary tests:** unsigned/expired/tampered/forged/replay/unknown-role/scope-spoof/
  header-strip are covered by `test_gateway_authz.py` + `test_internal_functions.py` (in the
  offline suite) and the **live** direct-AppSail bypass is refused (401) + foreign-origin CORS
  rejected (`live-catalyst-boundary.json`).
- **Scans:** secret_scan **PASS**; static_checks **8/8 PASS**; dep_audit **PASS** (npm prod 0
  high/critical; pip 0 un-accepted, 9 accepted-exceptions not expired — the starlette
  cross-major upgrade stays a documented accepted exception to protect the working backend,
  tracked in the backlog); route/data-boundary **PASS** (336 routes, 0 violations).
- **RLS/FORCE RLS remains DISABLED** by explicit synthetic-hackathon decision; **server-side
  role + scope authorization is therefore MANDATORY**. This is exactly why the live
  `DEMO_AUTH` bypass (RB-1) is a blocker — it removes that mandatory server-side enforcement
  at the edge.
- **CRITICAL live finding:** `gateway_api` `DRISHTI_DEMO_AUTH=true` → super_admin for
  sessionless callers. **RB-1.**

## D. Data and model integrity

- **TabFM** real result on `DeviceKind.CUDA` / Tesla T4, artifact digest `928cb350…`
  (verified at load; fail-closed on mismatch). **TimesFM** real forecast, 32 districts,
  intervals, digest `2f776efe…`. Both digests match DECISIONS.md.
- Canonical identity, spatial-containment (valid-geography exclusion), category/lifecycle
  consistency, evidence version/activity, synthetic markers and source/model/schema lineage
  are covered by the DB integration suite (scenarios/governance/geo-jurisdiction/graph-canonical).
- **No individual synthetic person-risk prediction is presented as operational** (aggregate
  district risk only; TabFM weights are Non-Commercial — evaluation only).
- Baseline comparison, confidence/abstention, stale behavior, reviewer state and
  backend/device/artifact digests are carried in the prediction envelope (v1.0.0).

## E. Performance and scale (bounded, honest)

- Bounded live load through the **actual Catalyst gateway** (`scripts/load_test.py`, c=6):
  **12 workloads, 0 errors**; latency p50 **167ms–1600ms**. **Slow-op finding:**
  `forecast_freshness` p50 ~13s, p99 ~25s, ~20% gateway 504 under load (SCALE-3).
- **Transparent capacity model** (`scripts/capacity_model.py`): required peak ≈ **300 rps**
  (100k users × 3% concurrent × 6 req/min); single-instance blended ≈ **14.2 rps** →
  **~30–82 AppSail instances** at 70% headroom, gated by the single-instance pin + heavy-read
  optimization. **No certification is claimed from extrapolation** — target-scale/HA
  certification is `POST_HACKATHON_BACKLOG` SCALE-1.
- Server-side pagination/aggregation present; ZCQL page-cap and bounded graph fan-out noted.

## F. Investigation-time demo metric

- `scripts/investigation_metric.py`: 4 golden tasks return a grounded, cited answer through
  the live path in **0.3–1.1s** (median). **Observed DRISHTI time only** — no manual baseline
  was measured, so **no percentage-reduction is claimed** (`investigation-time-metric.json`).

## G. Backup, recovery and rollback

`scripts/recovery_exercise.py` — all PASS: backup export+hash (200 rows, sha256 `17d749e3…`),
failed serving-job → controlled replay recovery, idempotent rerun preserving history,
failed-import rejected-row recovery, labelled model-version/fallback rollback.
**Live-proven elsewhere:** application rollback (Phase 23 `rollback-proof.log`), Stratus
object versions (Phase 23), **AWS GPU stopped** (this phase, zero endpoints). Deterministic
demo reset via `seed_demo_board.py` + disaster demo seed. Full procedures:
**`DISASTER_RECOVERY_RUNBOOK.md`**.

## H. Required artifacts (all created)

`docs/phase-reports/PHASE_25_REPORT.md` (this) · `HACKATHON_DEMO_CHECKLIST.md` ·
`HACKATHON_DEMO_RUNBOOK.md` · `DISASTER_RECOVERY_RUNBOOK.md` · `MODEL_RELEASE_CHECKLIST.md` ·
`POST_HACKATHON_BACKLOG.md` · `docs/deployment/FINAL_ARCHITECTURE.md` (Mermaid) ·
`docs/deployment/CATALYST_AWS_SERVICE_INVENTORY.md` ·
`docs/deployment/ORGANIZER_CAPABILITY_EVIDENCE.md` ·
`docs/deployment/ORGANIZER_NOTES_COVERAGE.md` · `docs/deployment/FINAL_TEST_SUMMARY.json` ·
`docs/deployment/SCREENSHOT_VIDEO_EVIDENCE.md` (+ `artifacts/phase-25/evidence-media-hashes.json`).

## I. Post-hackathon backlog

See **`POST_HACKATHON_BACKLOG.md`** — every item classified (Deferred / Platform Unavailable /
External Access Required / Optional Future) with owner, dependency and acceptance criterion,
including production RLS/authz/privacy, secret-rotation/pentest/IR, official feeds/licensing,
production speech/translation + localization, OCR pilots, directory/SSO/rank sync, offline
mobile capture, real historical validation + fine-tuning, 1M-case/100k-user HA certification,
governed RAG expiry + drift review, full Board snapshots/collaboration/multi-tenancy, and the
optional analytics items.

## J. Release declaration

**Strict acceptance (`scripts/release_accept.py`) returns non-zero → Prompt 25 stays PENDING.**

Decisive blocker and exact remediation:
- **RB-1** — set `DRISHTI_DEMO_AUTH=false` on `gateway_api`; create the 6 Catalyst users with
  `drishti_role`/`district_id`/`unit_id`; re-run the **live** six-role allow/deny matrix through
  `/api/*` (unauth `/api/*` must return 401; each role sees only its scope).
- **RB-2** — restore the live NL-query path (`/api/ask` 502): enable QuickML LLM Serving or wire
  the labelled deterministic planner on AppSail.
- **RB-3** — set `DRISHTI_AWS_ADAPTER_URL`/`SECRET` on the deployed AppSail so the
  Approved-FIR→Signal→AppSail→adapter→TabFM chain runs without a driver.
- **RB-4** — automate the interactive IAM login for a fully-automated live browser E2E.

When RB-1..RB-3 are closed and `scripts/release_accept.py` returns zero, declare **only**:
> "DRISHTI is ready for a synthetic hackathon demonstration on Zoho Catalyst."

**Never** declare production readiness.

---

## Evidence index (this phase)

- Tests: `artifacts/phase-25/test-runs/` (frontend-vitest, backend-offline-full, backend-db-integration-final)
- Local release gate 16/16: `artifacts/phase-22/release-gate.json`
- Live boundary: `artifacts/phase-25/live-catalyst-boundary.json`
- AWS model + cleanup: `artifacts/phase-25/{live-integration-reproof,forecast-timesfm-only,t4-teardown-after-e2e}.log`, `aws-inventory.json`
- Load + capacity: `artifacts/phase-25/load/{load-results,capacity-model}.json`
- Investigation metric: `artifacts/phase-25/investigation-time-metric.json`
- Recovery: `artifacts/phase-25/recovery/{recovery-exercise,serving-rows-backup}.json`
- Security scans: `artifacts/phase-25/{secret-scan,static-checks,dep-audit}.json`
- Authz matrix: `artifacts/phase-21/authorization-verification.json`
- Strict acceptance: `artifacts/phase-25/release-audit.json`, `evidence-manifest-p25.json`, `release-requirements-p25.json`
- Media hashes: `artifacts/phase-25/evidence-media-hashes.json`

> **Manifest note:** the full `artifacts/evidence-manifest.json` retains all p18–p25 records.
> Hashes for the phase-22 gate artifacts + the re-encoded phase-24 baseline were refreshed this
> session because they were legitimately regenerated (16/16 gate re-run / UTF-8 re-encode).
> Residual p23/p24 documentation-hash + missing-`resource_id` drift in the full manifest is
> **pre-existing** and is left for the **Prompt 26** independent evidence reconciliation
> (its explicit remit); the Prompt-25 strict gate audits the phase-scoped
> `evidence-manifest-p25.json`.
