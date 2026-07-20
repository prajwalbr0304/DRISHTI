# Phase 14 Part D — FastAPI deployment to Catalyst AppSail

Companion to `PHASE_14_REPORT.md` (matrix rows 2 + 3). Status date: 2026-07-18.
Catalyst project: **DHRISTI** (`48361000000030003`), India (IN) DC, Development env.

> **Status legend:**
> **DONE** — executed + verified here (evidence inline) · **IMPLEMENTED** — code/config
> written and locally verified (diagnostics / node --check / functional check) ·
> **HELD** — real artifact ready; the single remaining step is credit-spending or a
> console action, deliberately not run without go-ahead.
>
> Nothing below claims a cloud deployment. The image build needs Docker (absent on this
> machine) and `catalyst deploy appsail` spends credits; both are HELD (§11).

> **CORRECTION ADDENDUM (2026-07-20, Prompt 18).** "Docker (absent on this machine)"
> is **stale**: the Docker **CLI is installed** (`docker --version` → 29.6.1); only
> the **Linux daemon is not running** (`docker info` fails on the Desktop Linux
> engine pipe). The image build is unblocked once Docker Desktop's Linux engine is
> started (see `prompt3.md` Prompt 22). Historical text retained unchanged below.

---

## 0. Item-by-item status (spec Part D, 1–12)

| # | Requirement | State |
|---|---|---|
| 1 | Lightweight API Dockerfile separate from the GPU worker | **DONE** (§1) |
| 2 | Exclude CUDA/TabFM/TimesFM training packages from the AppSail image | **DONE** (§1) |
| 3 | Build an OCI linux/amd64 image (`buildx --platform linux/amd64 --load`) | **HELD** — Dockerfile + `deploy.ps1` ready; Docker absent (§8/§11) |
| 4 | Non-root, bind 0.0.0.0, AppSail port 9000, `/health/live` + `/health/ready` | **DONE** (§2) |
| 5 | CLI-driven local OCI deploy (exact installed-CLI syntax) | **IMPLEMENTED** — `deploy.ps1`; execution HELD (§8) |
| 6 | ECR alternative (immutable digest, no exposed creds) | **DONE (documented)** — local OCI preferred; ECR is the GPU-worker path (§8) |
| 7 | Server-only env/secrets; no `DATABASE_URL` on the CRUD path | **IMPLEMENTED** (§7) |
| 8 | Memory/disk/instances, health checks, structured redacted logs, scale-to-low | **IMPLEMENTED**; instance sizing applied at deploy (§5/§9) |
| 9 | Custom domain → gateway/function facade; restrict direct AppSail access | **IMPLEMENTED** (enforcement); custom domain HELD (console) (§9) |
| 10 | No CORS as auth; reject unauthenticated browser CRUD; scoped WS/SSE token | **IMPLEMENTED** (§3); no direct WS/SSE channel enabled (§10) |
| 11 | Catalyst SDK (Data Store/Stratus/NoSQL/Cache/Jobs/Circuits) + narrow fakes | **DONE** (§6); Circuits N/A in IN DC (documented) |
| 12 | Gateway derives identity, strips headers, signs context; AppSail verifies sig/audience/expiry/replay | **DONE** (§3/§4) |

---

## 1. Image: lightweight, GPU-free, separate from the worker (items 1, 2 — DONE)

- **API image:** `services/ml/Dockerfile.appsail` + `requirements.appsail.txt`. It installs
  only FastAPI/uvicorn/pydantic/psycopg2/`zcatalyst-sdk`/boto3 + the light CPU analytics
  stack (numpy/scipy/scikit-learn/networkx/shapely). It **excludes** torch, CUDA, TabFM,
  TabPFN, TimesFM, torch-geometric and sentence-transformers.
- **Worker image (separate):** `services/gpu-worker/Dockerfile` is the ONLY image with
  CUDA + torch + foundation weights; it runs on external AWS GPU and is pushed to a private
  ECR repo by immutable digest (item 6). The two images share no base and no build context.

## 2. Runtime contract (item 4 — DONE)

- **Non-root:** `USER appuser` (uid 10001).
- **Bind:** `uvicorn app.main:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-${APP_PORT:-9000}}`.
  Catalyst injects `X_ZOHO_CATALYST_LISTEN_PORT`; 9000 is the local fallback and matches
  `--port 9000`.
- **Health:** `GET /health/live` (process-only liveness, no external deps → never trips a
  restart loop) and `GET /health/ready` (readiness; RDS is advisory only and never
  hard-required — the operational CRUD path uses Catalyst Data Store).

## 3. Inbound trust boundary — reject unauthenticated CRUD (items 10, 12 — the core new work)

The deployed path is Browser → API Gateway → `gateway_api` function → AppSail. Part B built
the signer (`gateway_api`) and the verifier (`app/gateway_context.py`), but only
`/internal/ping` exercised it — the **operational CRUD routes did not verify the signed
context**, so this part closes that gap.

- **New:** `services/ml/app/gateway_enforcement.py` —
  `GatewayContextEnforcementMiddleware`. When `DRISHTI_REQUIRE_GATEWAY_CONTEXT=true`
  (deployed only) it verifies the signed context on every non-health request *before* the
  handler runs and returns an opaque **401** for a missing/forged/expired/replayed/
  wrong-audience context. So unauthenticated browser CRUD sent straight at the AppSail URL
  is refused (item 10). CORS is never treated as authentication.
- **Server-trusted role:** on success the middleware strips client identity headers
  (`x-role`, `x-demo-actor`, `x-user-*`, `x-forwarded-user`) and injects the role from the
  **verified** context, so the existing per-domain role gates (`_resolve_role(x_role)`) act
  on the trusted identity — never a spoofable client value. In deployment the gateway
  already strips `X-Role`, so this bridge is what makes the trusted role reach the gates.
- **Single nonce consumption:** the middleware stashes the verified context on
  `request.state`; the `require_gateway_context` / `require_service_context` dependencies
  reuse it instead of re-verifying, so a nonce is consumed exactly once (a second request
  with the same nonce is correctly rejected as a replay).
- **Off by default:** with the flag unset the middleware is a transparent no-op, so local
  dev and the test suite (where `X-Role` is display-only) are unchanged.
- **Placement:** middleware order is `AccessLog → CORS → GatewayEnforcement → RequestContext
  → BodySize → RateLimit → Honesty → routes`, so enforcement runs just inside CORS
  (preflight still works) and just outside the request-context/role layer.

## 4. Audience claim (item 12 — DONE)

The signed context now carries an `aud` claim. AppSail verifies **signature → audience →
scope → expiry → replay** (replay checked last so a request that fails an earlier check
never burns a nonce). Audience is configurable via `DRISHTI_CONTEXT_AUDIENCE` (default
`drishti-appsail`; empty string disables).

- Every context minter embeds `aud:'drishti-appsail'`: `gateway_api` (user scope), the 5
  event functions + 2 cron functions (service scope), the `_shared/context.js` reference,
  and the `pipelines/smoke_test.py` signer.
- Verified end-to-end: a Node-minted context (base64url + HMAC-SHA256 + `aud`) is accepted
  by the Python verifier with audience enforcement on; a mismatched audience is rejected.

## 5. Structured, redacted logs (item 8 — IMPLEMENTED)

- **New:** `services/ml/app/obs.py` — `AccessLogMiddleware` emits one compact JSON line per
  request to stdout (Catalyst captures stdout): `event, request_id, method, path (no query
  string), status, latency_ms, scope, role, client_ip`. It logs **no** bodies, headers,
  query strings or secrets, so it cannot leak evidence/PII/credentials/`DATABASE_URL`. Error
  bodies are already redacted by `app.hardening.install_error_handlers`.
- Gated by `DRISHTI_ACCESS_LOG_ENABLED` (on in deployment, off for the quiet test suite).

## 6. Catalyst SDK data/component layer (item 11 — DONE)

Each Catalyst component has a **narrow interface + in-memory fake (tests/local) +
`zcatalyst-sdk` implementation (deployed)**, selected by a `DRISHTI_USE_CATALYST_*` flag; the
SDK import is deferred so the modules stay importable/testable without the SDK:

| Component | Module | Fake | Notes |
|---|---|---|---|
| Data Store | `app/datastore/repository.py` | `InMemoryDataStore` | operational CRUD by `ExternalID` (idempotent upsert) |
| Stratus | `app/stratus.py` | `InMemoryStratus` | presigned exact-object transfer; versioned metadata only |
| NoSQL | `app/nosql.py` | `InMemoryNoSQL` | bounded semi-structured/ephemeral state only |
| Cache | `app/cache.py` | `InMemoryCache` | idempotency / rate / nonce / lookups (bounded TTL) |
| QuickML RAG | `app/quickml.py` | `OfflineRag` (refusing) | approved-text RAG; disabled by default |
| Connections | `app/connections.py` | `NullConnections` | OAuth token lifecycle; honest signed-service-auth gap |

- **Job Scheduling:** Catalyst cron functions (`functions/cron_reconcile`, `cron_forecast`)
  + `jobs/cron-schedules.json` (all `enabled:false` until owning phases).
- **Circuits:** verified **unavailable in the IN/EU/AU/JP/SA/CA DCs**; the design uses the
  documented idempotent Functions + Job Scheduling fallback. Recorded honestly in the matrix.

## 7. Server-only config; no `DATABASE_URL` on the CRUD path (item 7 — IMPLEMENTED)

- Config keys (never values) are the single reviewed source in `appsail.deploy.json`
  → `env_var_keys`: the HMAC signing secret, the enforcement + audience flags, the Data
  Store / Stratus enablement flags + Stratus bucket names, the AWS adapter URL/secret,
  optional Connections id, feature flags. Values are set **Console-side**; this script and
  repo never echo or commit them.
- **`DATABASE_URL` is in `must_not_set_for_crud`.** The deployed operational CRUD path uses
  Catalyst Data Store; `/health/ready` never hard-requires RDS. RDS remains only an optional
  read-only analytics adapter and is never shipped to the browser.
- New Part D flags read via `os.getenv` (matching the existing `DRISHTI_*` SDK-flag
  convention): `DRISHTI_REQUIRE_GATEWAY_CONTEXT`, `DRISHTI_CONTEXT_AUDIENCE`,
  `DRISHTI_ACCESS_LOG_ENABLED`.

## 8. CLI-driven build + deploy (items 3, 5, 6 — IMPLEMENTED; execution HELD)

- **New:** `infra/catalyst/appsail/deploy.ps1` — preflight (docker/buildx/catalyst) →
  `docker buildx build --platform linux/amd64 --load` → (opt-in `-Deploy`)
  `catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000`,
  run from `infra/catalyst`. Without `-Deploy` it builds and prints the exact deploy command
  (never spends credits on its own).
- **Verified CLI syntax (item 5):** installed **catalyst 1.27.0**. `catalyst deploy appsail`
  supports `--name --build-path --stack --platform --command --source --port` and has **no
  `standalone` subcommand** — so the brief's `... appsail standalone ...` form is NOT used;
  the flags above are the exact supported call. (`catalyst deploy appsail --help` was
  inspected before writing the script.)
- **ECR alternative (item 6):** the API prefers the local OCI standalone deploy (no registry
  needed). ECR-by-digest is the separate GPU-worker path (`services/gpu-worker`), which
  records the immutable image digest and never exposes ECR credentials.

## 9. Instances / scaling / domain (items 8, 9)

- **Descriptor (`appsail.deploy.json`):** memory 512 MB, disk 256 MB, instances min 1 /
  max 2, scale-up at 80% — conservative for the finite hackathon budget (scale-to-low).
- **Domain / access (item 9):** public access is via API Gateway `/api/*` → `gateway_api`
  → AppSail (`api-gateway/routes.json`, auth=required + sliding-window throttle). A custom
  API domain maps to the Gateway/Function facade **if available**, else the generated
  Catalyst API URL is used. AppSail is treated as a server-side endpoint; direct access is
  restricted as far as AppSail permits — since AppSail offers no network ACL on this plan,
  the enforcement middleware (§3) is the effective control: direct unauthenticated CRUD is
  rejected 401.

## 10. WebSocket/SSE (item 10 — N/A, documented)

DRISHTI enables **no direct browser WebSocket/SSE channel**; all traffic flows through the
authenticated Gateway → `gateway_api` → AppSail facade. The item-10 clause for a direct
real-time channel (allow only exact Catalyst frontend origins + validate a short-lived
scoped handshake token) therefore has no enabled surface. If one is added later, it must
reuse the signed-context primitives in `app/gateway_context.py` for the handshake token.

## 11. Verification evidence (item K)

- **Python diagnostics:** clean on `gateway_context.py`, `gateway_enforcement.py`, `obs.py`,
  `main.py`.
- **Middleware order** confirmed: `AccessLog → CORS → GatewayContextEnforcement →
  RequestContext → BodySize → RateLimit → Honesty`.
- **Functional enforcement (8/8):** health exempt; unsigned CRUD → 401; trusted role
  overrides client `X-Role`; audience mismatch → 401; bad signature → 401; service
  `/internal/ping` → 200 via state reuse; replayed nonce → 401; enforcement OFF is a no-op.
- **Node↔Python interop:** a Node-signed service context (with `aud`) verifies in Python
  with audience enforcement on.
- **Node syntax:** `node --check` clean on all 8 changed functions. **JSON:**
  `appsail.deploy.json` parses. **PowerShell:** `deploy.ps1` parses.
- Not run (no committed test files added per the task constraint): the full pytest suite —
  it hangs on live-DB connects unrelated to this change; targeted verification was used
  instead.

## 12. Held cloud steps (ordered; run only with go-ahead)

1. Install Docker Desktop (with Buildx) on the build machine / CI runner.
2. `cd infra/catalyst/appsail; ./deploy.ps1` (build only) → confirm the image builds
   linux/amd64 and the printed deploy command is correct.
3. `catalyst login` (if needed), then `./deploy.ps1 -Deploy` → `catalyst deploy appsail
   --name drishti-api --source docker://drishti-api:appsail --port 9000`.
4. Console → AppSail → drishti-api → Configuration: set the `env_var_keys` values
   (incl. `DRISHTI_REQUIRE_GATEWAY_CONTEXT=true`, `DRISHTI_CONTEXT_AUDIENCE=drishti-appsail`,
   `ZOHO_APPSAIL_SIGNING_SECRET`, Data Store/Stratus flags + bucket names,
   `DRISHTI_ACCESS_LOG_ENABLED=true`); confirm `DATABASE_URL` is NOT set. Set memory/disk/
   instances (512/256/min1/max2).
5. `catalyst apig:enable`; ensure `/api/*` routes to `gateway_api`; set the same signing
   secret + `ZOHO_APPSAIL_BASE_URL` on `gateway_api`.
6. `python infra/catalyst/pipelines/smoke_test.py --base-url https://<appsail-url>` →
   expect health 200/200, unsigned `/internal/ping` 401, signed 200.

## 13. Honest gaps / limitations

- **Cross-instance replay:** `gateway_context.py` uses a best-effort in-process nonce cache.
  With AppSail capped at max 2 instances and a 60s context TTL the exposure is small, but a
  nonce is not yet shared across instances via Catalyst Cache (the module documents this as
  the intended hardening). Not implemented here because it cannot be verified without the
  deployed Cache.
- **Build/deploy not executed:** Docker is absent on this machine and the deploy spends
  credits; both are HELD (§12). Everything up to the build is code-complete and locally
  verified.
