# PHASE 03 REPORT — Hackathon access mode, API-only DB access, RLS disabled, audit

Status: **Complete**
Date: 2026-07-17
Target: **AWS RDS PostgreSQL 17.10** — database `drishti`, app/owner role
`drishti_admin`, read-only role `drishti_readonly`
(`drishti-db.<...>.ap-south-1.rds.amazonaws.com`). Marker
`synthetic_meta.app_environment = synthetic_hackathon`.
Mode: synthetic hackathon demo only.

> No secret values (DB password, AWS/Supabase keys, tokens) are printed, logged,
> returned, committed, or reproduced in this report or the code. `DATABASE_URL`
> is resolved at runtime; the masked DB target logged at startup shows only
> `kind:host/db` (never the user or password).

---

## 0. Important environment finding (actioned)

The workspace has **migrated off Supabase to AWS RDS**. The repo-root `.env`
`DATABASE_URL` (active line) correctly targets AWS RDS; the old Supabase URL is
commented out.

During the pre-change audit I found a **stale process-scoped OS environment
variable `DATABASE_URL`** still pointing at the old Supabase project. Because
pydantic-settings prioritises OS environment variables over `.env`, a shell that
inherits this variable would connect the app to **Supabase instead of AWS RDS**.

- Scope: **Process only** (not User, not Machine) — a fresh terminal reads the
  correct AWS URL from `.env`. It is a transient session artifact.
- Action taken this session: pointed `DATABASE_URL` at the AWS RDS URL from
  `.env` so every migration/test targeted AWS RDS.
- **User action required:** clear the stale variable in any long-running shell
  (`Remove-Item Env:DATABASE_URL`) and confirm new terminals resolve AWS RDS.
- The masked DB target is now logged at FastAPI startup so a mis-route is
  obvious (`[startup] hackathon mode OK — synthetic DB confirmed (aws-rds:…)`).

The Phase 3 spec is written in Supabase terms (anon/authenticated/PostgREST).
On AWS RDS those Supabase roles **do not exist** and there is **no PostgREST**,
so the intent was adapted: RLS stays disabled (a PostgreSQL concept, still
applies), and the "revoke browser grants" step revokes from the PUBLIC
pseudo-role and — defensively, only if present — from anon/authenticated/
service_role. On AWS these are no-ops; the end-state verification still holds.

---

## 1. Outcome summary

Implemented DRISHTI **hackathon access mode**: an explicit synthetic-only
posture, an **API-only** data path (Browser → FastAPI → PostgreSQL/S3, no direct
DB access and no embedded secrets), **RLS disabled + verified** on every
application table, browser/PostgREST-style DML grants revoked, a **demo-actor
audit trail** for sensitive actions, and **network guardrails** (restricted
CORS, request-size + rate limits, sanitised errors). FIR/intake writes are now
**enabled** behind the localhost + synthetic-DB guards.

| Definition of Done | Result |
|---|---|
| RLS and FORCE RLS disabled on every application table | **Verified** — 116/116 tables `relrowsecurity=false` and `relforcerowsecurity=false`; `fn_assert_rls_disabled()` passes; 0 RLS policies |
| Browser has no direct DB path or embedded secret | **Verified** — no Supabase client in source; built bundle scanned clean; `.env`/creds server-side only |
| All application reads/writes go through FastAPI | **Verified** — single server-side `DATABASE_URL` path; React calls typed endpoints only |
| Only a synthetic-marked DB can run in hackathon mode | **Verified** — startup guard raises on a reachable non-synthetic/missing-marker DB |
| Synthetic demo writes work and sensitive actions create audit events | **Verified** — intake create/submit/approve/reject/return + case events + model run write same-transaction `audit_logs` rows |
| Supabase Auth/JWT/RLS production security clearly deferred | **Documented** — migration 011 footer + this report §9 |

---

## 2. Files and migrations changed

### New SQL migration
- `services/ml/sql/011_hackathon_access_grants.sql` — idempotent hackathon
  access-mode migration:
  - re-runs `fn_disable_rls_all_app()` + `fn_assert_rls_disabled()` (from 005);
  - adds `fn_revoke_browser_grants()` — revokes `INSERT/UPDATE/DELETE/TRUNCATE/
    REFERENCES/TRIGGER` from `PUBLIC` and (only if present) `anon`,
    `authenticated`, `service_role` (plus their `SELECT`); keeps
    `drishti_readonly` **SELECT-only**;
  - adds `fn_assert_no_browser_dml()` — raises if any of those grantees hold DML
    on a public application table (fails a future regression);
  - executes + verifies; inserts a non-secret `synthetic_meta` row
    `hackathon_access_mode = api_only`;
  - documents the deferred production RLS/auth work in the footer.

### New backend modules (`services/ml/app/`)
- `request_context.py` — `RequestContext` + `ContextVar` +
  `RequestContextMiddleware` (reads `X-Request-ID`/`X-Demo-Actor`/`X-Role`,
  stores `request.state.request_id`, echoes `X-Request-ID`).
- `audit.py` — `Action` constants, `sanitize_detail()` (drops sensitive keys,
  truncates strings, caps size), `record(...)` (same-transaction when a `conn`
  is passed; best-effort background otherwise; resolves demo actor → `user_id`).
- `hardening.py` — `verify_hackathon_startup()`, `masked_db_target()`,
  `read_db_environment_marker()`, `BodySizeLimitMiddleware` (413),
  `RateLimitMiddleware` (429), `install_error_handlers()` (sanitised 500s).

### Modified backend
- `app/config.py` — added `demo_frontend_origin`, `extra_cors_origins`,
  `rate_limit_enabled`, `rate_limit_per_minute`, `max_request_bytes`, and the
  `cors_allow_origins()` helper; **flipped `intake_submit_enabled` → `True`**
  (Phase 3 enables writes after the guards); corrected Supabase→AWS comments.
- `app/main.py` — `lifespan` runs `verify_hackathon_startup()`;
  `install_error_handlers(app)`; middleware stack (outermost→innermost):
  CORS → RequestContext → BodySizeLimit → RateLimit → Honesty; CORS built from
  `settings.cors_allow_origins()` with `allow_credentials=False` + explicit
  methods/headers; `/health` no longer echoes the raw driver error;
  `/demo/risk-score` writes a same-transaction `MODEL_RUN` audit event.
- `app/intake/service.py` — same-transaction `audit.record(...)` on
  `_create_draft`, `_submit`, `_approve`, `_review` (reject/return),
  `_add_case_event`.
- `app/intake/guards.py` — submit-gate message + `hackathon_status()` reason
  text + docstring updated (Phase 3 complete; headers are UX simulation).
- `tests/conftest.py` — session fixture disables the main app's rate limiter for
  the suite (the dedicated test enables it on an isolated app).
- `tests/test_intake.py` — updated the four Phase-2 assertions that assumed
  "submit disabled by default" to the Phase-3 enabled-by-default reality.

### New / modified frontend (`web/`)
- `src/api/client.ts` — sends `X-Request-ID` (per request) and `X-Demo-Actor`
  (display/audit only); added `setActorGetter`.
- `src/providers/RoleProvider.tsx` — wires the demo actor (`demo.<role>`).
- `src/components/shell/ProfileMenu.tsx` — relabelled the role switcher **"Demo
  view"** with a "not login or authentication" note.
- `src/components/shell/SyntheticBadge.tsx` — shows **"… Not for Operational
  Use"**; tooltip states the API-only guarantee.

### New tests + config
- `services/ml/tests/test_hackathon.py` — 22 Phase-3 tests (below).
- Root `.env.example` — documents AWS `DATABASE_URL` + hackathon/CORS/rate flags
  (variable names + placeholder values only; **no secrets**).

---

## 3. Database objects added (migration 011)

- Functions: `fn_revoke_browser_grants()`, `fn_assert_no_browser_dml()`.
- Re-used from 005: `fn_drishti_app_tables()`, `fn_disable_rls_all_app()`,
  `fn_assert_rls_disabled()`.
- `synthetic_meta` row: `hackathon_access_mode = api_only` (non-secret marker).
- Verified idempotent — applied to AWS RDS twice; both runs printed:
  - `HACKATHON RLS CHECK PASSED: RLS disabled + NO FORCE on all app tables.`
  - `HACKATHON GRANT CHECK PASSED: no anon/authenticated/service_role/PUBLIC DML on public tables.`

---

## 4. Endpoints / behaviour changed

No new routes were added. Cross-cutting behaviour added to **every** endpoint:
- `X-Request-ID` echoed on responses (generated if absent).
- Restricted CORS (localhost dev/preview + configured demo origin; no wildcard).
- Request-body size cap (413) and per-IP rate limit (429).
- Sanitised 5xx responses (`{"detail": "...", "request_id": ...}` — no SQL,
  stack trace, or credentials).
- `GET /intake/status` now reports `submit_enabled = true` (synthetic DB
  confirmed), lighting up the FIR wizard submit + inbox approve/return controls.

---

## 5. Commands run and results

| Command | Result |
|---|---|
| Read-only pre-change audit (AWS RDS) | 116 app tables, RLS 0/0, 0 policies, roles `{drishti_admin, drishti_readonly}` only, no anon/authenticated/PUBLIC DML, marker=`synthetic_hackathon` |
| Apply `011_hackathon_access_grants.sql` (×2, AWS RDS) | PASS — RLS + grant checks pass on both runs (idempotent) |
| `pytest tests/test_hackathon.py tests/test_intake.py -q` | **50 passed** (~72s) |
| `pytest -q` (full backend suite) | **178 passed, 11 failed, 2 skipped** — all 11 failures pre-existing data/route conditions unrelated to Phase 3 (see §8) |
| `npm run typecheck` (web) | PASS (`tsc --noEmit`, 0 errors) |
| `npx vitest run` (web) | **22 passed** (5 files) |
| `npm run build` (web) | PASS (3567 modules, dist emitted) |
| Bundle secret scan (`web/dist`) | PASS — no `supabase` / `sb_secret_` / `sb_publishable_` / `SERVICE_ROLE` / `rds.amazonaws.com` / `postgresql://` / `DATABASE_URL` |

> As in Phase 2, PowerShell reports a non-zero exit for `npm`/`npx` whenever a
> tool writes to stderr (deprecation / React-Router future-flag / chunk-size
> warnings) even on success; the authoritative signals are the printed
> `passed` / `built` lines.

### Phase-3 test coverage (`test_hackathon.py`, 22)
- **RLS**: `fn_drishti_app_tables()` shows every table `rls_enabled=false` &
  `rls_forced=false`; `fn_assert_rls_disabled()` passes; `pg_policies` public = 0.
- **API-only grants**: no `anon/authenticated/service_role/PUBLIC` DML;
  `fn_assert_no_browser_dml()` passes; `drishti_readonly` has `SELECT` and no DML.
- **Synthetic marker** present and equals the expected value.
- **Startup guard**: raises for a wrong marker and for a missing marker; passes
  for the synthetic marker; allows (warns) when the DB is unreachable;
  `masked_db_target()` hides user + password.
- **CORS**: allows `http://localhost:5173`; rejects `http://evil.example.com`
  (preflight → 400, no allow-origin echo).
- **Limits**: oversized body → 413; 4th request over a 3/min budget → 429 +
  `Retry-After`.
- **Errors**: an endpoint raising a SQL-like message returns a generic 500 with
  no `SELECT`/`password`/secret/`Traceback` leakage.
- **Frontend**: source scan finds no DB credential / service key / Supabase
  client / direct DB URL.
- **Audit**: `sanitize_detail` drops `brief_facts`/`password`/`api_key`/`phone`
  and nested secrets, keeps safe ids, truncates long strings; `audit.record`
  writes a same-transaction row with action/resource/resource-id + demo actor;
  a known actor resolves to its `user_id`; an intake create writes an
  `intake.create` audit event.
- **Request context**: `X-Request-ID` echoed (and generated when absent);
  `X-Demo-Actor` exposed to the handler context.

All DB-integrated tests run inside a **rolled-back** transaction (`rw_rollback`)
— nothing is persisted to the synthetic development database.

---

## 6. Table-by-table RLS-disabled verification (AWS RDS)

Verified via `fn_drishti_app_tables()` (owner connection) after all migrations:

| Metric | Value |
|---|---:|
| Application tables (public, owned by `drishti_admin`) | **116** |
| Tables with `relrowsecurity = true` | **0** |
| Tables with `relforcerowsecurity = true` | **0** |
| RLS policies in `public` | **0** |

`fn_assert_rls_disabled()` raises if any application table ever has RLS/FORCE
enabled, so a later migration that accidentally enables RLS will fail the check.

## 7. Grant audit + API-only data-flow proof

| Grantee | DML on public app tables (INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER) |
|---|---|
| `PUBLIC` | none |
| `anon` / `authenticated` / `service_role` | **role does not exist on AWS RDS** (no PostgREST); revoke is a defensive no-op |
| `drishti_readonly` | none (SELECT-only, preserved) |
| `drishti_admin` (app/owner) | full (owner) — server-side only, never exposed to the browser |

API-only data flow: React (`web/src/api/client.ts`) issues typed `fetch` calls
to the FastAPI base URL and nothing else. There is **no** Supabase/publishable
client, **no** `DATABASE_URL`, and **no** direct table query in the source or
the built bundle (grep-verified). The single server-side PostgreSQL path is
`app/db.py` (`rw_conn`/`ro_conn`) via `DATABASE_URL`.

Synthetic-data guard: `verify_hackathon_startup()` refuses to boot in
`HACKATHON_MODE` unless a reachable DB is marked `app_environment =
synthetic_hackathon`; every intake write additionally re-checks the marker per
request (`require_synthetic_db`). CORS rejects unlisted origins (tested).

---

## 8. Full-suite failures — pre-existing, not Phase-3 regressions

The full backend suite reports **11 failures**. Each was confirmed to be a
pre-existing data/route condition, independent of Phase 3:

- **`test_explain::test_contract_audit_every_ai_route_conforms`** — 2
  non-conforming routes: `GET /geo/boundaries/{level}` and `GET /geo/sho-regions`
  lack a `response_model`. Both live in `app/geo/router.py` (an earlier-phase,
  uncommitted change **not touched in Phase 3**). The audit is pure route
  introspection (no DB), so its result is independent of the access-mode work.
- **Derived-analytics data tests** — the derived batches have not been
  regenerated on the freshly migrated AWS RDS (the roadmap defers these to
  Phases 11–13). Confirmed counts (read-only): `CrimeRiskScore = 0`
  (→ `test_risk` bands / by-accused / calibration), `mv_active_hotspots = 0`
  (→ `test_geo` hotspots / emerging alerts), `FinancialTransaction` flagged = 0
  (→ `test_money` flagged / structuring / unified), plus the graph-hidden
  materialised feed and the analytics report matrix.

Phase 3 changes never write or delete this derived data, and migration 011 only
touched grants (a no-op on AWS RDS, which has no anon/authenticated roles).
These failures are therefore out of Phase-3 scope and are recorded for the
relevant analytics/model phases.

---

## 9. Security + data-quality checks

- **RLS** stays disabled + NO FORCE on all 116 tables; verification is
  migration-owned and re-runnable; 0 policies (hackathon design).
- **API-only**: browser → FastAPI only; no browser→DB path; no secret in the
  frontend source or built bundle.
- **Grants**: browser/PostgREST DML revoked from PUBLIC + Supabase roles (if
  present); `drishti_readonly` SELECT-only; app connects server-side.
- **Startup guard**: refuses a non-synthetic / missing-marker reachable DB in
  hackathon mode; logs a masked (credential-free) DB target.
- **Audit**: sensitive actions (intake create/submit/approve/reject/return, case
  events, model run) write append-only `audit_logs` rows with request id, demo
  actor, action, resource, resource id, ip, timestamp. `sanitize_detail`
  guarantees no secrets/narratives/PII/file contents are logged.
- **Network**: restricted CORS (no wildcard), request-size cap (413), per-IP
  rate limit (429), sanitised 5xx responses (no SQL/stack/credentials).
- **Demo actor / X-Role / X-Demo-Actor** are explicitly UX simulation, not
  authentication — labelled in the UI and documented server-side.

---

## 10. Known limitations

1. **Not production security** (by design): no Supabase Auth/Cognito JWT, no RLS
   policies, no per-unit/case authorization. Role/actor headers are editable and
   are display/audit only.
2. **App connects as the RDS master role** `drishti_admin`. A dedicated
   least-privilege login role is recommended but deferred (it needs a new secret
   + `DATABASE_URL` rotation); documented in migration 011 + §11.
3. **Rate limit is per-process/in-memory** — adequate for a localhost/single-edge
   demo; a shared store (e.g. Redis) is needed for multi-instance production.
4. **`/demo/risk-score`** is a committing endpoint (writes + matview refresh) and
   is intentionally **not** exercised by automated tests (no-mutation rule); its
   audit wiring mirrors the tested `audit.record(conn=...)` helper.
5. **Legacy Supabase project** still carries the old broad anon/authenticated DML
   grants. It is no longer the source of truth; recommend pausing/deleting it or
   revoking its grants (see §11).
6. **Startup guard fails open on DB unreachability** (logs a warning) so a
   transient blip does not hard-crash the demo; per-request write guards remain
   fail-closed.

---

## 11. Deferred production security (do NOT implement in the hackathon)

- Re-enable + FORCE RLS and author per-table policies scoped to unit/case/role.
- Configure real identity (Supabase Auth or Cognito) + JWT verification;
  replace editable `X-Role`/`X-Demo-Actor` with verified identity.
- Provision a least-privilege FastAPI DB login role; rotate `DATABASE_URL`.
- Put the API behind HTTPS/API Gateway (or equivalent) with WAF; keep the DB
  port private.
- Rotate any credential ever shared outside the secret store; retire/pause the
  legacy Supabase project (or revoke its anon/authenticated grants).

---

## 12. Next-phase (Prompt 4) prerequisites

- Hackathon access mode is in force: RLS disabled + verified, API-only, audit,
  synthetic guards — Prompt 4 (canonical identity / entity resolution) can build
  on the intake canonical records created on approval.
- Migrations 005 + 011 own the repeatable RLS/grant verification; new migrations
  must keep RLS disabled (the assertion will fail otherwise).
- **User action:** clear the stale process `DATABASE_URL` so the app targets AWS
  RDS (fresh terminals already do); optionally set `INTAKE_SUBMIT_ENABLED`
  explicitly and `DEMO_FRONTEND_ORIGIN` for a deployed demo.

---

## 13. Definition of Done — verification

- [x] RLS and FORCE RLS disabled on every DRISHTI application table (116/116; 0 policies).
- [x] The browser has no direct Supabase/database data path or embedded secret (source + bundle verified).
- [x] All application reads/writes go through FastAPI (single server-side `DATABASE_URL`).
- [x] Only a database explicitly marked synthetic can run in hackathon mode (startup guard tested).
- [x] Synthetic demo writes work and sensitive actions create audit events (same-transaction, tested).
- [x] Supabase Auth/JWT/RLS production security is clearly listed as deferred (§11).
