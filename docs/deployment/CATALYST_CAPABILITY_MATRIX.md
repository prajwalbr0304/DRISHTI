# DRISHTI — Catalyst capability matrix (Prompt 23 D.3/D.4/D.5)

> Honest record of which Zoho Catalyst services DRISHTI **uses**, which are
> **available but deliberately not used** (with the real fallback), and which are
> **unavailable in the India DC**. No third-party substitute is used to "tick a
> row", and no capability is claimed working without evidence. Project DHRISTI
> `48361000000030003`, org `60075362708`, India DC, Development.

## Legend
- **USED** — enabled and exercised live; evidence linked.
- **USED (fallback)** — a bounded, honest substitute is used for a specific,
  documented reason; the Catalyst service is available.
- **NOT USED** — available in the DC but intentionally hidden from the submitted
  demo; the deterministic/offline path serves the feature instead.
- **UNAVAILABLE** — not offered in the India DC; recorded, not replaced by a
  third party.

## Core platform (all USED, proven live)

| Capability | Status | Evidence |
|---|---|---|
| Data Store (operational serving) | **USED** | live ZCQL/row upsert/get/delete; `State` row imported; readiness `operational_datastore: ok` |
| Stratus (evidence/import/report buckets) | **USED** | fixture upload+download sha256 MATCH, versioning, signed-URL expiry — `artifacts/phase-23/stratus-fixture.log` |
| Functions (9: gateway_api, channel_token, 5 event, 2 cron) | **USED** | deployed at `.../server/<fn>/` |
| API Gateway (routes + auth + throttle 600/min) | **USED** | `/api/*` routes; `/api/cases` → 401; `/api/health/*` → 200 |
| AppSail (FastAPI custom container) | **USED** | live `/health/ready` 200; non-root; graceful shutdown |
| Slate (Web Client Hosting) | **USED** | `drishti-frvfpunc.onslate.in` serving the SPA |
| Authentication (embedded IAM login) | **NOT USED (demo)** | **Option B:** the demo login is the offline role-card picker (no IAM widget). See "Demo login (Option B)" below. The IAM→gateway path + 6-role server-side authz are retained in code and were proven live earlier (Prompt 21/23 evidence). |

## Demo login (Option B — synthetic role cards)

The embedded Catalyst Authentication widget proved unreliable to embed in the SPA
(empty box / internal scrollbar / stuck-loading / stale-session `locate` 400s), so
the **submitted demo** replaces IAM login with a synthetic **role-card picker**:
click a role → instant offline sign-in → the app opens with live data.

- **Frontend:** `VITE_AUTH_MODE=offline` → `LoginPage` renders `RolePicker` →
  `signInOffline(role)` (no Catalyst Web SDK, no iframe). Synthetic identities only.
- **API path stays live + still signed:** the `/api/*` Gateway route is set to
  `authentication: optional` and the `gateway_api` function runs in demo mode
  (`DRISHTI_DEMO_AUTH=true`). With no Catalyst session it mints a **full-access
  super_admin HMAC-signed context**, so the AppSail (unchanged) still verifies a
  signed context on every request — the trust boundary is intact; only the
  identity *source* changed.
- **Role cards are a presentation view:** the selected role drives the client
  workspace (sidebar/views/scope labels), exactly like the in-app Demo View; the
  demo session has full data access. Real per-role server enforcement remains in
  code and was proven live via the IAM→gateway path (Prompt 21 authz matrix +
  Prompt 23 §3.12).
- **Blast radius:** the demo API is publicly callable, bounded by exact-origin
  CORS, request throttling, **synthetic data only**, and the AppSail synthetic-DB
  write guard (`synthetic_meta` marker; RLS off by explicit hackathon request).
- **Reversible:** set `VITE_AUTH_MODE=catalyst` + `VITE_API_WITH_CREDENTIALS=true`,
  restore the `/api/*` route to `required`, and unset `DRISHTI_DEMO_AUTH` to return
  to real IAM login. Console steps: `docs/deployment/CATALYST_CONSOLE_SETUP.md` §6.

## Bounded / conditional

| Capability | Status | Decision & evidence |
|---|---|---|
| **Cache (NoSQL/Cache)** | **USED (fallback)** | In-process cache on the **single-instance** AppSail (idempotency/nonce/rate-limit are correct for one instance). Catalyst Cache is available but needs per-segment provisioning; the code is REST-ready (`CatalystCache` + `DRISHTI_CATALYST_CACHE_SEGMENTS`) to switch on when segments exist. Not a duplicate of Data Store records. |
| **Signals** | **USED** (pending live exec, Task 9/D1) | The one mandatory `prediction.requested` Signal = `drishti_datastore` publisher, `row_inserted`, filter `table=PredictionRequest AND state=approved` → `prediction_event` (`infra/catalyst/jobs/signals-rules.json`). Fires from a Data Store row insert. Custom `drishti_app` publisher is optional (Phase 15/16 events), gated off. |
| **Cron** | **USED** (pending live exec, Task 9/D1) | Scheduled forecast → `cron_forecast` → AppSail `/internal/forecast/run` (idempotent by window, bounded 3× retry). |
| **QuickML (RAG / no-code baseline)** | **NOT USED (deferred)** | Available in IN DC (LLM serving). The "Ask DRISHTI" assistant currently uses the deterministic **OfflineRag** that refuses unless an approved-SOP KB is loaded (safe, cost-free). Enabling it requires building the approved-SOP KB + a deployed endpoint + a minimal-scope Connection (`QuickML.rag.READ`/`endpoints.READ`), then the fixed evaluation — a deliberate, separate step, not faked. |

## Unavailable in the India DC (recorded, not substituted)

| Capability | Status | DRISHTI handling |
|---|---|---|
| **Zia STT/TTS / translation** | **UNAVAILABLE** | Kannada/English **voice query** uses the browser **Web Speech API**, clearly labelled as a browser fallback (not a Catalyst service). OCR/evidence extraction stays out of scope. Voice transcription is never conflated with evidence extraction. |
| **Zia AutoML** | **UNAVAILABLE** | The eligible no-code tabular baseline is placed on **QuickML** instead (documented in `services/ml/app/quickml.py`); no third-party AutoML is substituted. |
| **Circuits** | **UNAVAILABLE** | Not used; orchestration stays in Functions + the AppSail. No third-party workflow engine substituted. |

## Deliberately hidden from the submitted demo (available, NOT USED)

| Capability | Status | Reason & fallback |
|---|---|---|
| **SmartBrowz (pdfshot)** | **NOT USED** | Report export uses a deterministic server-side path; the SDK-based `smartbrowz.py` is not REST-migrated for the custom container. Hidden from the demo; marked Not Used rather than fake a watermarked-PDF render. |
| **Mail (Email)** | **NOT USED** | Notifications are **in-app, data-minimized** records (`/internal/notify` → Data Store). No external email is sent in a synthetic-data demo (avoids mailing real addresses). Hidden. |
| **Push (web/mobile notifications)** | **NOT USED** | Same as Mail — the demo surfaces notifications in-app only. Hidden. |

## Operational data plane (Prompt 23 Option A — documented deviation)

The deployed operational data is split across two server-side stores; the
**browser never reaches either directly** (always browser → API Gateway →
`gateway_api` → signed context → AppSail):

| Domain group | Live source | Notes |
|---|---|---|
| Board, Disaster, Search, Scenarios, Internal | **Catalyst Data Store** (native) | The prompt-aligned operational serving source; no `DATABASE_URL` needed. |
| FIR/intake, cases, casework, evidence-metadata, chat, imports, notifications, reports, org, admin, governance, livefeed, investigate | **AWS RDS `drishti-db`** (synthetic, ap-south-1) via **AppSail server-to-server** | Still `rds_backed_migration_pending` (Data Store migration is the target). Served live via `DATABASE_URL` on the AppSail for demo completeness. |
| Heavy analytics (graph, geo, forecast, risk, money, workload, explain, predict, performance) | **AWS RDS via protected adapter** | Adapter-only; never a generic SQL proxy. |

**Deviation, stated honestly:** giving the AppSail a `DATABASE_URL` makes RDS the
operational serving source for the migration-pending domains instead of the
Catalyst Data Store. It preserves browser↔DB isolation, is bounded to a
**synthetic** DB (startup enforces the `synthetic_meta` marker; RLS off by
explicit hackathon request), and is reverted by removing `DATABASE_URL`. Chosen
so all five mandatory journeys run on the live deployment; the Data Store
migration of these domains remains the post-hackathon target. See
`infra/catalyst/appsail/appsail.deploy.json` → `database_url_policy` and
`services/ml/app/deployment_boundary.py`.

## Notes
- "Hidden" means the capability is not surfaced as a control in the submitted
  demo UI, so acceptance never shows a non-functional button.
- Every "NOT USED" here has a working deterministic/offline fallback so the
  corresponding feature still functions in the demo without the paid/region
  service.
- Availability of Zia ML / Circuits reflects the India DC component list recorded
  during Phase 14/21; QuickML LLM serving is available in the India DC.
