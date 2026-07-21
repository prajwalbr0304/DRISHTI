# Phase 22 Report — Local Release Stabilization & Functional Catalyst CI/CD

- Prompt: 3new / Prompt 22
- Date: 2026-07-21
- Branch: `fix/case-overview-location-map`
- Catalyst project: DHRISTI (ID 48361000000030003, org 60075362708, India DC)
- Status: **COMPLETE** — the strict local release gate returns **exit 0 /
  verdict RELEASE_CANDIDATE** with **16/16 mandatory gates PASS**.

Result label: **HACKATHON-DEMO READY** (local release candidate). Not
production-ready. Live cloud proof (deploy/smoke/rollback, real GPU model) is
Prompt 23/24.

---

## 1. Objective recap

Produce a reproducible local release candidate and a pipeline that actually
blocks deployment on failures before spending cloud credits. Everything in this
phase is verifiable offline; the credit-spending deploy stays defined-but-held
for Prompt 23.

The one command:

```
python scripts/release_gate.py      # exit 0 only for a genuine candidate
```

Machine-readable summary: `artifacts/phase-22/release-gate.json`
(`verdict: RELEASE_CANDIDATE`, `mandatory_passed: 16/16`).

---

## 2. Toolchain (A.1–A.2) — pinned & verified

| Tool | Local version | Pinned min (`infra/catalyst/pipelines/toolchain.lock.json`) |
| --- | --- | --- |
| Node | v20.17.0 | 20.17.0 (`web/.nvmrc`) |
| npm | 11.5.2 | 10.0.0 |
| Python | 3.12.10 | 3.12.0 |
| Java (Catalyst CLI runtime) | 21.0.8 | 17.0.0 |
| Docker | 29.6.1 (Linux engine running) | 24.0.0 |
| Catalyst CLI | 1.27.0 | 1.27.0 |
| AWS CLI | 2.17.22 | 2.15.0 |
| AppSail base image | `python:3.12-slim` | — |
| GPU-worker base image | `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` | — |

Docker Desktop's Linux daemon was already running (A.1). The `toolchain` gate
validates every local tool against the pinned minimums and asserts the daemon is
a running Linux engine.

---

## 3. AppSail image (A.4) — build digest, DB-free run, 3 real bugs fixed

- Image: `drishti-api:appsail`, `linux/amd64`, non-root `appuser` (uid 10001),
  port 9000 (`X_ZOHO_CATALYST_LISTEN_PORT`), digest
  `sha256:81b08d8083a33c03e4495046a05da919174503854c5014d0db1172f0c07a4a45`
  (rebuilt deterministically from `services/ml/Dockerfile.appsail`; the release
  gate auto-builds it if Docker Desktop has pruned it).
- Ran locally **without `DATABASE_URL`**:
  - `GET /health/live` → **200** `{"status":"live"}` (liveness).
  - `GET /health/ready` → **200** `ready:true` — `operational_datastore: ok`
    (in-memory Data Store fake), `gateway_auth: not_required`,
    `object_store: not_required`, `analytics_db: unavailable` (advisory-only).
  - Dependency-aware **failure** proven: with `DRISHTI_USE_CATALYST_STRATUS=true`
    and no bucket, `/health/ready` → **503 not_ready** (readiness cannot pass for
    a broken operational plane).
  - **Graceful shutdown**: `docker stop` completes in **~1.4 s** with the full
    `Shutting down → Application shutdown complete` lifespan sequence.

Three real deployment defects were found by actually running the image and are
fixed:

1. `app/datastore/seed.py` used `Path(__file__).resolve().parents[4]` — an
   `IndexError` that **crashed AppSail startup** in the container (app lives at
   `/app`, not the repo tree).
2. `app/disaster/seed.py` had the same `parents[4]` crash.
   Both now use the new `app/datapaths.py::repo_data_path()` (ancestor search;
   returns `None` in the minimal image and degrades gracefully — the deployed
   reference source is Catalyst Data Store, not the repo files).
3. `Dockerfile.appsail` `CMD` gained `exec` so **uvicorn is PID 1** and receives
   SIGTERM directly (was a 10.5 s grace-then-SIGKILL; now a 1.4 s graceful stop).

## GPU worker (A.5) — static/unit/contract only

`py_compile` of all four modules; Dockerfile `docker build --check` (no
warnings); and the wire-contract check `services/gpu-worker/schema.py`
`ENVELOPE_VERSION == services/ml/app/predict/envelope.py` (**1.0.0 == 1.0.0**).
No CUDA image build — real GPU proof is Prompt 24.

---

## 4. Zero unexplained local failures (B)

### Backend

- **DB-free offline suite** (matches the DB-free AppSail; `DRISHTI_DISABLE_DB_TESTS=1`):
  **378 passed, 211 skipped** (`@requires_db`), 0 failed. This is the mandatory
  backend release tier.
- **Full DB pass** (RDS reachable) surfaced 3 failures; 2 were genuine defects
  and are fixed, 1 is classified and deferred:
  - `test_explain.py::test_contract_audit_every_ai_route_conforms` — 2 routes
    (`/chat/capabilities`, `/forecast/horizons`) were newly-added **capability /
    metadata descriptors**, not AI answers. Added to the audit `exempt` set with
    rationale (like the existing `/chat/translate` exemption). FIXED.
  - `test_money.py::test_money_permission_matrix` — the Phase-21 code-based money
    matrix returned Python `None` for `policymaker`, but the authoritative SQL
    seed (`police_fir_extensions.sql`) maps `('policymaker','money_trail','none')`
    and `permission_action_enum` includes `'none'`. Restored the explicit
    `'none'` grant for `policymaker`/`disaster_coordinator`; reconciled the
    contradictory Phase-21 test (`test_operational_datastore_reads.py`, which had
    asserted `is None`) to the SQL-faithful `== "none"` and added an
    unknown-role→`None` case. FIXED (security semantics unchanged: both deny).
  - `test_risk.py::test_full_calibration_report_runs` (`@slow @requires_db`):
    foundation accuracy **0.2525 < 0.3** on deliberately-noisy synthetic labels
    using the **CPU in-context fallback**. Classified ENVIRONMENT/live_aws — the
    real TabFM runs on GPU (Prompt 24); the in-context model is proven `>0.3` on
    clean-signal fixtures (`test_calibration_metrics_and_logic` passes). The
    screen it feeds (Analytics → Explainability) degrades gracefully; `/risk/
    calibration` is RDS-direct so it is not part of the DB-free AppSail demo. The
    test was **not** weakened/xfail'd — it is deferred to Prompt 24. Recorded as
    a known cloud-only item (§9).

### B.2 derived fixtures (non-destructive; recorded)

Serving-export source version `mapping_version 2026.07.18-1`
(exported 2026-07-18; 1500 cases, 3970 persons, 57 orgs). Served projections in
the DB-free subset: CrimePrediction 288, CrimeHotspot 41, NetworkEdge 2411,
GangMembership 524, EntityGraph 5000, FeatureSnapshot 96. The derived
socioeconomic / hidden-association / money-alert / individual-risk tables are
RDS analytics-plane fixtures (`@requires_db`; 0 rows in the DB-free serving
subset). Nothing was regenerated.

### Frontend

| Gate | Command | Result |
| --- | --- | --- |
| Lint | `npm run lint` (eslint 9.39.5 flat config) | **0 errors**, 47 warnings (non-blocking) |
| Typecheck | `npm run typecheck` (`tsc --noEmit`) | PASS |
| Unit/component | `npm run test` (vitest) | **65 passed** (21 files) |
| Production build | `npm run build` | PASS, no secrets in bundle |

ESLint was previously **unconfigured** (the `eslint .` script existed but no
ESLint was installed). Restored a locked flat-config stack (eslint 9.39.5,
`@eslint/js` 9.39.5, typescript-eslint 8.65.0, eslint-plugin-react-hooks 5.2.0,
eslint-plugin-react-refresh 0.4.26, globals 15.15.0). Fixed **6 real lint
errors**: 5 × `react-hooks/rules-of-hooks` (a `useQuery`/`useMutation` called
after a policymaker early-return in `CaseFile`, `EntityExplorer`, `EntityProfile`,
`IntakeInbox` — hooks moved above the return and gated with
`enabled: role !== "policymaker"`) and 1 × `no-unused-expressions` in
`ExploreMode` (a `&&`-chain used as a statement → proper `if`).

### B.5 release API-URL guard

`web/scripts/check-bundle-secrets.mjs` gained a **release mode** (`--release` /
`DRISHTI_RELEASE_BUILD=1`): the unconfigured `REPLACE-WITH-CATALYST-API-GATEWAY-
ORIGIN` placeholder is now **FATAL** (was a warning), and the build-time
`VITE_API_BASE_URL` must be a valid https Catalyst API-Gateway origin routing
`/api` — never empty, http, localhost, an AWS URL, or a raw AppSail URL. Proven
both ways: a release check with the placeholder/unset/http/AWS/appsail/missing-
`/api` URL **fails**; a valid `https://…/api` URL **passes**. New scripts
`build:release` / `check:bundle:release`.

---

## 5. Browser E2E harness (C)

Playwright `@playwright/test@1.61.1` (chromium). One set of journey specs runs
in two targets: **local** (default — `vite preview` of the offline-auth build +
`page.route` fixture stubbing, fully deterministic, no backend) and **live**
(`E2E_TARGET=live E2E_BASE_URL=<gateway>` for Prompt 23, no stubbing).

**27 passed / 0 failed** (`npm run test:e2e`; artifacts in
`artifacts/phase-22/e2e/`).

| Journey | Spec | States covered | A11y |
| --- | --- | --- | --- |
| (a) Login & role context | `auth-role.spec.ts` | unauthorized→/login, responsive (390×844) | keyboard reach, visible focus, Enter-activate, labeled landmarks |
| (b) FIR intake | `intake-fir.spec.ts` | data, empty, error, unauthorized | table + column headers, named actions |
| (c) Evidence metadata | `evidence-metadata.spec.ts` | data, empty, unauthorized | accessible table |
| (d) Ask DRISHTI | `ask-drishti.spec.ts` | loading (thinking), data | Enter submits, `role=table` fallback under the chart |
| (e) Case investigation | `case-investigation.spec.ts` | data, empty, error, unauthorized, responsive | sub-nav roles |
| (f) Investigation Board | `investigation-board.spec.ts` | data, empty, unauthorized | roles/text/toolbar (no pixel snapshot of the dynamic canvas) |
| (g) Emergency Response | `emergency-response.spec.ts` | data, empty, **stale feed**, read-only crime role | KPI text/labels |

Reduced motion is honoured globally; dynamic maps/graphs use role/text/structure
assertions, never pixel snapshots. Real router paths were used
(`/er`, evidence as the `/cases/:id?tab=evidence` tab, `/board`).

---

## 6. Real security / build gates (D)

| Gate | Script | Result |
| --- | --- | --- |
| Secret scan (D.1) | `scripts/security/secret_scan.py` | **PASS** — 954 tracked text files, 0 committed secrets, 0 forbidden secret files (redacted output; `.env`/`.env.local` never read — only git-tracked files) |
| Dependency audit (D.2) | `scripts/security/dep_audit.py` | **PASS** — `npm audit --omit=dev` **0 vulns** (shipped bundle); pip-audit on the AppSail runtime: 0 un-accepted |
| Static/config/policy (D.3–D.5) | `scripts/security/static_checks.py` | **PASS (8/8)** |
| Web bundle URL/secret (D.5) | `infra/aws/check_no_db_url_in_web.py` | **PASS** — 270 web files, no DB/AWS URL or server secret |
| Route data-boundary (D.5) | `services/ml/tools/route_data_boundary.py --check` | **PASS** — 335 routes, 0 unclassified |

`static_checks.py` (8/8): `json_yaml_valid` (172 files), `function_syntax`
(10 Catalyst Node functions via `node --check`), `dockerfile_check`
(2 Dockerfiles via `docker build --check`), `env_key_schema` (every production
`VITE_*` key documented in `.env.example`), `cors_policy` (no wildcard production
CORS; the opt-in `cors_allow_all` defaults False and is never set in the deployed
AppSail descriptor), `browser_db_client` (the web bundle imports **no** DB
client), `synthetic_marker` (present), `python_compile` (254 backend modules).

### Dependency findings

- **python-dotenv 1.0.1 → 1.2.2** (fixes CVE-2026-28684 / PYSEC-2026-2270 in
  `set_key`/`unset_key`; DRISHTI only reads `.env`). Applied to both requirements
  files; verified safe.
- **starlette 0.41.3** — 9 advisories (transitive via `fastapi==0.115.6`, which
  pins `starlette<0.42`). Recorded as **accepted exceptions** in
  `docs/deployment/security-exceptions.json` with per-CVE applicability (the
  StaticFiles UNC SSRF is Windows-only and we deploy linux; the multipart /
  `request.form` / FileResponse-Range advisories don't apply to a JSON API with
  no untrusted upload surface; the Host/path `request.url` reconstruction is
  behind the API Gateway and unused for authz), an owner, an expiry (2026-09-30)
  that fails the gate on lapse, and the fix path (fastapi≥0.139 / starlette≥1.3.1
  — a cross-major upgrade deferred to Prompt 25 to avoid destabilizing the
  378-test backend). The 5 npm findings are **dev-toolchain only**
  (vite/vitest/esbuild) and never reach the shipped bundle.

---

## 7. Catalyst pipeline corrections (E)

`infra/catalyst/pipelines/catalyst-pipelines.yaml` rewritten to a lean, blocking
6-stage sequence: **validate → build → security → preflight → deploy_dev →
smoke** (with a retained `rollback_dev`).

| Prompt-22 requirement | Correction |
| --- | --- |
| E.1 working dirs / paths | frontend builds from `web` (`build:release`); every `catalyst` command runs from `infra/catalyst`; AppSail deploys the intended linux/amd64 image (`docker-archive://`) |
| E.2 lean sequence | install → lint/type/test → build → security scans → deploy dev → Auth/Gateway/AppSail/Slate/Data Store/prediction smoke → retain rollback |
| E.3 no `\|\| true` | removed from the dependency audit, deploy, smoke and rollback steps (verified: 0 occurrences in jobs) |
| E.3 real scans | the echo-only "secret scan" is replaced by the executable `scripts/security/*` gates — identical to the local release gate |
| E.4 smoke via Auth+Gateway | `smoke_test.py --gateway-url` smokes `/api/health/{live,ready}` (Gateway→AppSail) and asserts an unauthenticated `/api/cases` is refused (401/403), not only the direct AppSail URL |
| E.5 mandatory preflight | new `preflight_deploy.py --require-live` gate before deploy: project/env == DHRISTI 48361000000030003 (India DC), synthetic marker, DB-free AppSail posture, no-duplicate |
| E.6 GPU separate | a `gpu_worker_static` job static-checks the GPU Dockerfile/contract only; the GPU image is built/pushed and its endpoint registered separately (Prompt 24) |

---

## 8. Strict local release gate (F)

`scripts/release_gate.py` runs 16 mandatory gates and writes
`artifacts/phase-22/release-gate.json`. It exits non-zero for **any** mandatory
failure, skipped gate (e.g. `--only`), invalid production URL, missing build
artifact, or unclassified route — proven: a `--only` subset run correctly exits
1 because the unselected mandatory gates are `SKIPPED`.

Final run: **16/16 PASS, exit 0, verdict RELEASE_CANDIDATE**
(started 2026-07-21T18:40:57+05:30, ~7 min).

| # | Gate | Tier | Result |
| --- | --- | --- | --- |
| 1 | toolchain | unit | PASS (all ≥ pinned mins; docker linux) |
| 2 | frontend_lint | unit | PASS (0 errors) |
| 3 | frontend_typecheck | contract | PASS |
| 4 | frontend_test | unit | PASS (65) |
| 5 | backend_offline | integration | PASS (378 passed, 211 skipped) |
| 6 | frontend_build | build | PASS (no bundle secrets; artifacts present) |
| 7 | release_url_guard | security | PASS (rejects unset/invalid release URL) |
| 8 | appsail_image | build | PASS (linux/amd64, appuser, 9000; auto-builds if absent) |
| 9 | secret_scan | security | PASS |
| 10 | dep_audit | security | PASS |
| 11 | static_checks | security | PASS (8/8) |
| 12 | web_no_db_url | security | PASS (270 files) |
| 13 | route_boundary | contract | PASS (335 routes, 0 unclassified) |
| 14 | gpu_contract | contract | PASS (1.0.0 == 1.0.0) |
| 15 | deploy_preflight | contract | PASS (DHRISTI binding + synthetic + no-dup) |
| 16 | e2e | e2e | PASS (27) |

---

## 9. Definition of Done

| DoD item | Status |
| --- | --- |
| Backend, frontend, lint, build and mandatory static/security checks green | **MET** (release gate 16/16) |
| AppSail Linux AMD64 image runs locally without operational PostgreSQL | **MET** (live/ready 200 DB-free; graceful shutdown) |
| Browser E2E covers every mandatory local demo journey | **MET** (7 journeys, 27 tests) |
| Release build cannot contain an invalid API URL or secret | **MET** (release guard + bundle scan, proven both ways) |
| Catalyst Pipeline uses correct paths and cannot pass failed mandatory stages | **MET** (paths corrected; no `\|\| true`; real blocking gates; preflight) |
| Strict local release command returns zero only for a genuine candidate | **MET** (exit 0 for 16/16; subset run exits 1) |

---

## 10. Remaining cloud-only checks (Prompt 23/24)

These are intentionally NOT provable locally and are held for the live phases:

- **Live Catalyst deploy / smoke / rollback** (functions, client/Slate, AppSail,
  API Gateway, Data Store) — Prompt 23. The pipeline stages and `smoke_test.py
  --gateway-url` / `acceptance_check.py` are ready; live URLs come from the
  Console after `apig:enable` + first deploy.
- **Live no-duplicate project/service check** — the preflight's `--require-live`
  path runs on the bound, authenticated runner (locally the CLI is interactive,
  so it reports `inconclusive`; the offline binding/synthetic/no-dup config
  checks are mandatory and pass).
- **Real TabFM / TimesFM on AWS GPU** + the risk-calibration accuracy floor —
  Prompt 24. Locally the CPU in-context fallback stands in.
- **Browser E2E against the live Catalyst URL** (`E2E_TARGET=live`) — Prompt 23.

---

## 11. Key files changed / added

Added: `scripts/release_gate.py`, `scripts/security/{secret_scan,dep_audit,
static_checks}.py`, `docs/deployment/security-exceptions.json`,
`infra/catalyst/pipelines/{toolchain.lock.json,preflight_deploy.py}`,
`services/ml/app/datapaths.py`, `web/eslint.config.js`, `web/.nvmrc`,
`web/playwright.config.ts`, `web/e2e/**` (7 specs + fixtures/support).

Modified: `services/ml/Dockerfile.appsail` (exec CMD),
`services/ml/app/{datastore/seed.py,disaster/seed.py,explain/service.py,
money/permissions.py}`, `services/ml/requirements{,.appsail}.txt`
(python-dotenv 1.2.2), `services/ml/tests/test_operational_datastore_reads.py`,
`web/package.json`, `web/scripts/check-bundle-secrets.mjs`, 5 web route hook
fixes, `infra/catalyst/pipelines/{catalyst-pipelines.yaml,smoke_test.py,
README.md}`, `prompt3new.md` (status table), `EXECUTION_STATE.json`.

No secrets, `.env` values, credentials or raw records appear in code, logs,
artifacts or this report. RLS/FORCE RLS remain disabled per the synthetic-
hackathon request; server-side role/scope authorization is unchanged.
