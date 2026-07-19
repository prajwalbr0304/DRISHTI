# Phase 14 Part F — Secure Catalyst-to-AWS custom analytics/model connectivity

Companion to `PHASE_14_REPORT.md` §F. Status date: 2026-07-18.
Catalyst project: **DHRISTI** (`48361000000030003`), India (IN) DC, Development env.

> **Status legend:** **DONE** — executed + verified here (evidence inline) ·
> **IMPLEMENTED** — code/config written and locally verified (diagnostics /
> `node --check` / functional round-trip) · **HELD** — real artifact ready; the
> only remaining step is credit-spending or a Console/account action, deliberately
> not run without go-ahead.
>
> Part F **hardens and completes** the Catalyst→AWS path that Parts B/D/E
> scaffolded (the signed HTTPS client `app/predict/adapter.py`, the versioned
> `envelope.py`, the AWS `gpu-worker`, the gateway facade + inbound trust
> boundary). Nothing below claims a cloud deployment: the AWS adapter deploy, the
> RDS/API-Gateway/IAM apply and enabling the live SSE channel all spend credits
> or need the account/Console and are **HELD** (§"Held cloud steps"). Every
> offline equivalent is verified against the real code paths.

---

## 0. Item-by-item status (spec Part F, 1–6)

| # | Requirement | State |
|---|---|---|
| 1 | Browser never calls AWS/AppSail-CRUD; Gateway facade is the public boundary; a direct AppSail WS/SSE only via a short-lived audience/board/user-bound token + strict Origin + expiry | **IMPLEMENTED** — facade pre-existing (Part B/D); **new scoped channel** built + verified; live enable HELD (§1) |
| 2 | Keep RDS private — never 5432 to `0.0.0.0/0`; no `DATABASE_URL` in React or on the AppSail CRUD path | **DONE (documented + enforced)** — posture descriptor + runnable browser-leak check; SG/Console apply HELD (§2) |
| 3 | Minimal protected AWS adapter inside the VPC: Catalyst → HTTPS API Gateway → Lambda/ECS → SageMaker/Batch (+ read-only PostGIS/pgRouting only where necessary) | **IMPLEMENTED** — `services/aws-adapter/` + round-trip verified; real deploy HELD (§3) |
| 4 | Catalyst Connections for OAuth where compatible; else short-lived signed service requests with timestamp/nonce replay protection; an API key alone is not authentication | **DONE** — signed verify on both sides (replay/skew/forgery); Connections module pre-existing (§4) |
| 5 | AWS execution roles, least-privilege IAM, request-size/rate limits, TLS, timeouts, circuit breaking, retry with jitter, idempotency, redacted audit logs | **IMPLEMENTED** — client circuit breaker + adapter limits/idempotency/redacted logs verified; IAM/role apply HELD (§5) |
| 6 | Capability-gap justification for every AWS path; do not use AWS to replace a matching Catalyst service | **DONE** — `capability_gaps.py` (5 paths + 9 Catalyst-served) + validator + JSON mirror (§6) |

---

## 1. Browser boundary + scoped SSE/WS channel (item 1 — IMPLEMENTED)

The public HTTP boundary is unchanged and already correct: Browser → Catalyst API
Gateway → `gateway_api` (derives identity server-side, strips spoofable headers,
mints a short-lived signed context) → AppSail; the browser never talks to AppSail
CRUD or AWS directly, and the enforcement middleware (`gateway_enforcement.py`)
rejects unsigned CRUD 401.

**New this part — the one permitted direct channel (F.1's WS/SSE clause).**
`PHASE_14_PARTD_REPORT.md` §10 recorded "no direct WS/SSE channel enabled"; Part F
adds it, fenced exactly as the clause requires:

- **`services/ml/app/channel.py`** — mint + verify a channel token. Scheme mirrors
  `gateway_context.py` (base64url(JSON) + hex HMAC-SHA256 over the payload string,
  ms timestamps). The token binds **audience** (`drishti-channel`, distinct from
  the gateway's `drishti-appsail`), **user**, **board** and **origin**, with a
  short **expiry** (default 5 min). Verify order: secret → fields → signature
  (constant-time) → audience → scope → expiry → user/board binding → **strict
  Origin** (live `Origin` must be allow-listed *and* equal the origin the token
  was minted for). Fail-closed `ChannelError` throughout.
- **`services/ml/app/stream/router.py`** — `GET /stream/predictions`. Returns
  **404** unless `DRISHTI_STREAM_CHANNEL_ENABLED=true` (no surface when off), **400**
  without `board_id`, an opaque **401** on any token/binding failure, else an SSE
  `StreamingResponse` that emits a `ready` event, drains a bounded per-(board,user)
  `ChannelHub` of **data-minimized** notices (ids + template only — never
  scores/PII), heartbeats, and **self-closes at the token expiry** (hard-capped at
  15 min) forcing a re-handshake through the gateway.
- **`infra/catalyst/functions/channel_token/`** — the authenticated Advanced I/O
  minter on the Gateway path: resolves the user from Catalyst Authentication
  server-side (401 otherwise), performs a strict Origin allow-list check (403), a
  server-side board check (`userMayAccessBoard`, 403), then mints the bound token
  and returns `{ token, board_id, expires_at, stream_url }`.
- **Enforcement exemption:** `gateway_enforcement.py` exempts `/stream/*` from the
  signed-gateway-context requirement precisely because the channel token is its
  dedicated, stricter auth — never a blanket bypass.

## 2. Keep RDS private (item 2 — DONE, documented + enforced)

- **`infra/aws/rds-network-posture.json`** — the reviewed required posture: port
  5432 **not** publicly accessible, security-group ingress **SG-to-SG only** from
  the adapter SG, `0.0.0.0/0` on 5432 explicitly forbidden, private subnets, TLS
  required (`rds.force_ssl=1`) + IAM DB auth via `drishti_readonly`, and
  `DATABASE_URL` server-side only (never the CRUD path, never the browser).
- **`infra/aws/check_no_db_url_in_web.py`** — a runnable, source-level guard that
  fails CI if a `postgres://` string, `*.rds.amazonaws.com` host, `:5432` endpoint,
  AWS key, PEM, or a server-only env key (`DATABASE_URL`, signing/adapter secrets,
  AWS keys) leaks into the web env/source. It is careful to ignore the *prose*
  "never put a DATABASE_URL here" mentions in the committed env comments (it checks
  `KEY=VALUE` assignments only on non-comment lines), complementing the existing
  build-time `web/scripts/check-bundle-secrets.mjs` (which scans `dist/`).
- App side (pre-existing, re-confirmed): `config.py` keeps `database_url`
  server-side with `sslmode=require`; `/health/ready` never hard-requires RDS;
  `appsail.deploy.json` lists `DATABASE_URL` in `must_not_set_for_crud`.

## 3. Protected AWS adapter inside the VPC (item 3 — IMPLEMENTED)

**New `services/aws-adapter/`** — the server counterpart of the signed HTTPS client,
a separate deployment (like `gpu-worker`) that carries a self-contained copy of the
wire contract:

- `signing.py` — `verify_request` (secret → fields → envelope-version → signature
  (constant-time) → timestamp skew → replay-nonce, replay checked **last** so a
  failing request never burns a nonce) + `sign_result` (produces exactly what the
  AppSail client's `_verify` accepts) + a TTL `NonceCache`.
- `schema.py` — a thin `RoutingView` + fail-closed `parse_and_validate` (approved
  task/backend/dispatch-mode sets, ≤5000 query rows, ≤5 MB envelope, `timeout_s`
  range, envelope-version match). It forwards the *full* envelope downstream, so it
  is not a third full mirror.
- `dispatch.py` — `ModelDispatcher` ABC + `FakeDispatcher` (offline; TabFM **fails
  closed** with `CUDA_UNAVAILABLE`) + `AwsDispatcher` (lazy boto3; SageMaker
  real-time/async, AWS Batch submit+poll via KMS-encrypted S3 staging; downstream
  circuit breaker + retry-with-jitter; idempotency by `idempotency_key`).
- `handler.py` — transport-agnostic `process_request` + `lambda_handler` (API
  Gateway REST v1 / HTTP v2 proxy) + `create_app` (Flask/ECS). Read-only PostGIS
  is reached only-where-necessary per §6.

## 4. Authentication — signed service requests, not an API key (item 4 — DONE)

Every inbound request carries `X-DRISHTI-Timestamp` + `X-DRISHTI-Nonce` +
`X-DRISHTI-Signature` (HMAC-SHA256 over `ts|nonce|<raw body>`) +
`X-DRISHTI-Envelope-Version`. The adapter verifies signature, skew and replay and
returns an opaque **401** on any failure. An API Gateway API key (in
`adapter-infra.json`) is explicitly documented as a **usage-plan throttle handle
only, not authentication**. The preferred OAuth/OIDC upgrade path (Cognito
authorizer + **Catalyst Connections**, `app/connections.py`) is pre-existing and
recorded honestly as the signed-service-auth gap it closes.

## 5. Hardening (item 5 — IMPLEMENTED)

- **Circuit breaking (new):** `services/ml/app/predict/circuit.py` — a thread-safe
  CLOSED/OPEN/HALF_OPEN breaker, wired into `SignedHttpsAdapter` so a single logical
  request (with its retry loop) records one outcome; repeated AWS failures fail fast
  for a cooldown instead of stampeding. A compact copy guards the adapter's own
  downstream SageMaker/Batch calls.
- **Retry with jitter / timeouts / idempotency (pre-existing + extended):** bounded
  timeout + exponential backoff with full jitter (now no wasted sleep after the last
  attempt) on the client; retry-with-jitter + `IdempotencyStore` on the adapter.
- **Request-size + rate limits:** 5 MB envelope cap + in-process fixed-window rate
  limit on the adapter (API Gateway throttle/WAF is the primary control).
- **Least-privilege IAM (descriptors, apply HELD):** `infra/aws/adapter/iam/` —
  trust policy (lambda assume) + an execution policy scoped to specific DRISHTI
  ARNs (InvokeEndpoint/Async on `endpoint/drishti-*`, transform-job, `SubmitJob` on
  the DRISHTI queue/def, S3 staging `/adapter/*` only, KMS via an `s3` condition,
  `secretsmanager:GetSecretValue` on `drishti/adapter/hmac-*`, own log group,
  optional read-only `rds-db:connect`). The only `Resource:"*"` is `batch:DescribeJobs`
  (no resource-level support) + VPC ENI management delegated to the AWS-managed
  policy — the provisioner's least-privilege check enforces this.
- **TLS + redacted audit logs:** HTTPS-only API Gateway (min TLS 1.2); the adapter
  emits one compact JSON audit line per request (event/request-id/status/latency/
  task/backend/mode) and **never** a body, prediction, secret or PII.

## 6. Capability-gap justification (item 6 — DONE)

`services/ml/app/predict/capability_gaps.py` is the source of truth (mirrored to
`infra/aws/capability-gaps.json`, parity-guarded). It records **5 retained AWS
paths** — TabFM GPU inference, TimesFM GPU inference, ST-GNN GPU inference,
PostGIS/pgRouting analytics RDS (read-only), and the ECR model-artifact workflow —
each with the specific Catalyst capability gap, the Catalyst service(s) checked
first, the AWS runtime, the data-minimized boundary payload, and a
"not-replacing-a-Catalyst-service" attestation. It also lists **9 capabilities
deliberately kept on Catalyst** (Data Store CRUD + search, Stratus, QuickML RAG +
no-code baseline, the CPU near-repeat/KDE/fusion steps, Functions + Job Scheduling).
`validate_capability_gaps()` enforces completeness, uniqueness, an AWS-runtime
check, data-minimization, and an **anti-replace overlap guard** (an AWS path may not
duplicate a Catalyst-served capability).

## 7. Verification evidence

All verification is offline against the real code paths (no committed test files,
per the standing constraint; a throwaway harness was used and removed):

- **F.5 circuit breaker:** open after N failures → fail fast → half-open probe →
  close on success → re-open on a failed probe; `SignedHttpsAdapter._request` fails
  fast (no socket I/O) when the circuit is open.
- **F.3/F.4 adapter round-trip:** a client-signed `POST /predict` is authenticated,
  dispatched (fake), then `GET /predict/{id}` returns a signed result envelope that
  the **AppSail client's `SignedHttpsAdapter._verify` accepts**; TabFM comes back
  `state=failed`/`CUDA_UNAVAILABLE` and `is_authentic_backend(TABFM)` is False.
- **F.4/F.5 boundary rejections:** replayed nonce → 401, forged signature → 401,
  oversize → 413, unapproved task → 400, health → 200 (no signature), missing
  secret → 503 (fail closed). Audit lines emitted are redacted JSON.
- **F.1 channel token:** happy path binds user/board/origin/expiry; wrong origin,
  empty allow-list, board mismatch, expiry, bad signature and wrong audience are all
  rejected. SSE endpoint (via `TestClient`, rejection paths only): disabled → 404,
  no token → 401, no board → 400, wrong Origin → 401. `/stream/*` confirmed exempt
  from gateway-context enforcement. **Node→Python interop:** a token minted by a
  Node replica of `channel_token` verifies in `channel.py`.
- **F.2:** `check_no_db_url_in_web.py` — clean on the real `web/` (219 files, 0
  leaks) and catches a planted `DATABASE_URL=postgresql://…rds…:5432` (5 findings,
  exit 1).
- **F.6:** `validate_capability_gaps()` → `{aws_paths: 5, catalyst_served: 9}`;
  JSON mirror in parity; anti-replace negative test rejects a duplicated capability.
- **Static:** `get_diagnostics` clean on all 14 new/edited Python files; `app.main`
  imports and registers `/stream/predictions`; `node --check` clean on
  `channel_token/index.js`; all new/edited JSON parses; `provision_adapter.py`
  plan exits 0 with the least-privilege check passing.

## 8. Held cloud steps (ordered; run only with go-ahead)

1. `python infra/aws/adapter/provision_adapter.py --commit --profile <p>` — create
   the least-privilege role + inline policy, package + deploy the adapter Lambda in
   private subnets, then create the HTTP API (HTTPS-only, throttle, usage plan,
   redacted access logging).
2. Create the HMAC secret in Secrets Manager (`drishti/adapter/hmac-*`) and set
   `DRISHTI_AWS_ADAPTER_SECRET_ARN` on the Lambda; put the SageMaker/Batch endpoint
   names + `DRISHTI_ADAPTER_S3_STAGING` in the Lambda env.
3. On AppSail (Console): set `DRISHTI_AWS_ADAPTER_URL` (the API Gateway invoke URL)
   + `DRISHTI_AWS_ADAPTER_SECRET`; for the channel set
   `DRISHTI_STREAM_CHANNEL_ENABLED=true`, `DRISHTI_CHANNEL_SIGNING_SECRET`,
   `DRISHTI_CHANNEL_ALLOWED_ORIGINS` (the exact Slate origin). On the `channel_token`
   function set the same signing secret + `DRISHTI_APPSAIL_STREAM_URL`.
4. `catalyst deploy --only functions` (adds `channel_token`); in the Console add the
   `/api/channel-token` API Gateway route (auth required).
5. Lock down the analytics RDS security group per `rds-network-posture.json` (drop
   any `0.0.0.0/0`, allow only the adapter SG on 5432; enable `rds.force_ssl`).

## 9. Honest gaps / limitations

- **In-process replay/rate state:** the adapter nonce cache + rate limiter and the
  SSE hub are per-instance. In deployment a shared TTL store (DynamoDB/ElastiCache)
  should back replay, and API Gateway throttling/WAF is the primary rate control;
  the durable notice source is the Catalyst Signals → notify path (the hub only
  buffers for a currently-open stream).
- **Board membership is a placeholder:** `channel_token`'s `userMayAccessBoard`
  currently allows any authenticated user their own board channel; a real deployment
  resolves board membership from Data Store here.
- **Live cloud not executed:** the adapter deploy, IAM/API-Gateway/RDS apply, the
  Secrets Manager secret and enabling the SSE channel all spend credits / need the
  account or Console and are HELD; every offline equivalent is verified.
- **gpu-worker result signing:** the worker's `_sign_result` uses a slightly
  different canonicalisation; the adapter is authoritative for the client-facing
  signature (`signing.sign_result` matches the client verifier exactly), and the
  adapter re-signs results for the client, so the client contract is unaffected.
