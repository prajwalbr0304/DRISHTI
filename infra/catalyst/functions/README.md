# infra/catalyst/functions — Serverless Functions (Phase 14 Part B)

Catalyst Serverless Functions are the deployed serverless backend logic and the
public HTTP boundary of DRISHTI. The heavy application logic lives in the AppSail
FastAPI service; these functions are thin, event-driven, and secured.

> **Deploy status:** SCAFFOLDED. Code + per-function `catalyst-config.json` are
> committed. `catalyst deploy --only functions` is a credit-spending step held
> for explicit go-ahead (see `../README.md` runbook). No `node_modules` is
> committed (installed by the CLI at serve/deploy). Node stack `node20`.

## Function inventory

| Folder | Type | Role | Matrix rows | Workflow | Enable flag |
|---|---|---|---|---|---|
| `gateway_api` | advancedio | Authenticated public API facade → signed context → AppSail | 1, 17, 18 | §8.1–8.2 | always on |
| `channel_token` | advancedio | Authenticated mint of a scoped SSE/WS channel token (audience/board/user-bound) | 1 (Part F) | §8.1 | `DRISHTI_STREAM_CHANNEL_ENABLED` (AppSail side) |
| `evidence_event` | event | Evidence security path (quarantine/validate/scan) | 8, 21 | §4 | `DRISHTI_EVIDENCE_SCAN_ENABLED` |
| `datastore_event` | event | Approved canonical change → FeatureSnapshot + staleness | 6, 10, 21, 22 | §3, §6 | `DRISHTI_FEATURE_SNAPSHOT_ENABLED` |
| `prediction_event` | event | Approved PredictionRequest dispatch + result routing | 21, 22 | §7 | `DRISHTI_PREDICTION_DISPATCH_ENABLED` |
| `report_event` | event | `report.ready` → delivery notice | 16, 21 | §11 | `DRISHTI_REPORT_DELIVERY_ENABLED` |
| `notify_dispatch` | event | Data-minimized Mail/Push delivery | 24, 25 | §12 | `DRISHTI_NOTIFY_ENABLED` |
| `cron_reconcile` | cron | Reconciliation/backup/cleanup/health/budget | 20 | §17 | `DRISHTI_RECONCILE_ENABLED` (+ schedule) |
| `cron_forecast` | cron | Scheduled forecast/backfill dispatch | 20 | §9 | `DRISHTI_FORECAST_CRON_ENABLED` (+ schedule) |

`_shared/context.js` is a **reference** copy of the signing/dispatch helpers —
Catalyst deploys each folder independently, so every function inlines the few
lines it needs. `_shared/` is not listed in `catalyst.json` `targets` and is not
deployed.

## Signed internal context (the AppSail trust boundary)

The browser never calls AppSail or AWS directly. Trust flows one way through a
short-lived HMAC-signed context (report §8.2):

- **User context** (`gateway_api`): derives identity from Catalyst Authentication
  (user scope), strips every inbound identity header, resolves the role
  **server-side**, then sends AppSail
  `X-DRISHTI-Context: base64url({user_id,email,role,scope:'gateway',ts,exp,nonce,request_id})`
  and `X-DRISHTI-Signature: HMAC-SHA256(payload, secret)`.
- **Service context** (event/cron): same envelope with `scope:'service'` and a
  `source` field, so AppSail can tell internal calls from user calls.

AppSail verifies signature + scope + expiry + nonce (replay) before trusting the
context. The shared secret is `ZOHO_APPSAIL_SIGNING_SECRET` — configured as an
env var in the console / AppSail configuration, **never committed**. Verification
is implemented in `services/ml/app/gateway_context.py`.

## Required environment variables (configured in the console, never committed)

| Var | Used by | Purpose |
|---|---|---|
| `ZOHO_APPSAIL_BASE_URL` | all | HTTPS base URL of the AppSail FastAPI service |
| `ZOHO_APPSAIL_SIGNING_SECRET` | all | HMAC secret for the signed internal context |
| `DRISHTI_GATEWAY_PATH_PREFIX` | gateway_api | public path prefix to strip (default `/api`) |
| `DRISHTI_GATEWAY_TIMEOUT_MS` | gateway_api | upstream timeout (default 25000; aio hard cap 30s) |
| `DRISHTI_NOTIFY_FROM_EMAIL` / `DRISHTI_NOTIFY_DEFAULT_TO` | notify_dispatch | Mail sender / fallback recipient |
| `DRISHTI_CHANNEL_SIGNING_SECRET` | channel_token | HMAC secret for the channel token (falls back to `ZOHO_APPSAIL_SIGNING_SECRET`) |
| `DRISHTI_CHANNEL_ALLOWED_ORIGINS` | channel_token | comma-separated exact browser origins (strict Origin check at mint) |
| `DRISHTI_APPSAIL_STREAM_URL` | channel_token | HTTPS base URL of the AppSail SSE endpoint returned to the browser |
| `DRISHTI_CHANNEL_TTL_MS` | channel_token | channel-token lifetime (default 300000 = 5 min) |
| `DRISHTI_*_ENABLED` | events/crons | per-scaffold enable flags (default off = cost-free) |

## Scoped SSE/WS channel token (Part F item 1)

`channel_token` is the one authenticated path that mints a **short-lived,
audience/board/user-bound** token (`aud:'drishti-channel'`, distinct from the
`drishti-appsail` gateway audience). The browser uses it to open ONE **direct**
AppSail SSE stream (`/stream/predictions`) — the only permitted non-facade
browser→AppSail connection. AppSail verifies the token signature, audience,
board+user binding, expiry and a **strict Origin** check before opening the
stream, which self-closes at the token expiry. Minting + verification share the
scheme in `services/ml/app/channel.py`; the stream lives in
`services/ml/app/stream/router.py` and is OFF unless
`DRISHTI_STREAM_CHANNEL_ENABLED=true`.

## API Gateway route table (matrix row 18)

`catalyst apig:enable` puts the gateway in front of the functions (it disables
the default Security Rules, so every public route must be declared). Routing,
Catalyst authentication and sliding-window throttling are configured in the
console (or `catalyst-user-rules.json`). AppSail is **not** a native gateway
target, so the gateway fronts `gateway_api`, which securely invokes AppSail.

| Path pattern | Target | Auth | Throttle (general / IP) |
|---|---|---|---|
| `/api/*` | `gateway_api` | required | 600 rpm / 120 rpm |
| `/api/channel-token` | `channel_token` | required | 120 rpm / 30 rpm |
| `/api/public/health` | `gateway_api` | optional | 120 rpm / 60 rpm |

CORS for the deployed Slate origin is handled by **Authorized Domains**, not in
function code (function code sets CORS only for `localhost`). See
`../api-gateway/routes.json` for the committed route design (`catalyst pull`
generates the canonical `catalyst-user-rules.json` from the console config).

## Signals rule map (configured in the console — Signals has no SDK)

| Publisher | Event | Target function | Dispatch | Notes |
|---|---|---|---|---|
| Stratus | `stratus_object_uploaded` (evidence prefix) | `evidence_event` | Instant | security scan only |
| Data Store | `row_inserted` / `row_updated` on `CaseVersion` | `datastore_event` | Instant | approved rows only |
| Data Store | `row_inserted` on `PredictionRequest` | `prediction_event` | Instant | approved only |
| Data Store | `row_inserted` on `PredictionResult` | `prediction_event` | Instant | notify path |
| Custom `drishti-app` | `report.ready` | `report_event` | Instant | |
| Custom `drishti-app` | `notify.requested` | `notify_dispatch` | Instant | Mail/Push |

Retry is auto (exponential backoff, max 20 attempts); undelivered events move to
Dropped after the 24h TTL — the Signals-native DLQ equivalent. See
`../jobs/signals-rules.json` for the committed descriptor.
