# DRISHTI — Catalyst Live Inventory & Deployment Runbook (Prompt 23)

> **Synthetic Karnataka Police hackathon demo — never production.** This file is
> the single reviewed source for the *live* Zoho Catalyst deployment of DRISHTI
> into the existing project. It records the pre-deploy inventory, the exact
> interleaved CLI + Console runbook, and the live resource IDs/URLs as they are
> created. **No secrets, tokens, credentials or emails are recorded here.**

| Field | Value |
|---|---|
| Project | **DHRISTI** |
| Project ID | `48361000000030003` |
| Organization | `60075362708` |
| Data center | India (IN) |
| Environment | Development |
| Dev domain (from `.catalystrc`) | `dhristi-60075362708.development` |
| CLI | Catalyst CLI `1.27.0`, authenticated (project owner) |
| Budget baseline | ~INR 1,800 (INR 1,500 Basic + INR 300 Free), 17 Jul – 17 Aug 2026 |
| Inventory captured | 2026-07-21 |
| **Live status** | **PARTIALLY DEPLOYED** — API Gateway enabled; 9 Functions live; AppSail live (health 200). Env config, Data Store/Stratus provisioning, Slate, identities, Signals/cron pending. |

## Live resources captured (2026-07-21)

| Resource | Live ID / URL | Status |
|---|---|---|
| Serverless domain (functions + Gateway) | `dhristi-60075362708.development.catalystserverless.in` | live |
| API Gateway | ENABLED (`catalyst apig:status`) | live; routes pending Console |
| Function `gateway_api` | `https://dhristi-60075362708.development.catalystserverless.in/server/gateway_api/` | live (503 until env set — expected) |
| Function `channel_token` | `https://dhristi-60075362708.development.catalystserverless.in/server/channel_token/` | live |
| Event functions | `evidence_event`, `datastore_event`, `prediction_event`, `report_event`, `notify_dispatch` | live (inactive until Signals+flags) |
| Cron functions | `cron_reconcile`, `cron_forecast` | live (inactive until cron+flag) |
| AppSail `drishti-api` | `https://drishti-api-50044118953.development.catalystappsail.in` | live; `/health/live`=200, `/health/ready`=200 |
| Analytics DB (source for serving export) | reachable; `CaseMaster`=100000, `Employee`=12000, `District`=32 (140 tables) | available (RDS/local, adapter-only) |

> AppSail is currently in the **pre-config** state: `gateway_auth: not_required`
> (`DRISHTI_REQUIRE_GATEWAY_CONTEXT` unset) and the in-memory Data Store fallback.
> Setting the env vars (§3 Stage 3) switches it to the secure Catalyst Data
> Store/Stratus mode and enforces the signed-context boundary.

---

## 0. Preflight (COMPLETE — green)

| Check | Result | Evidence |
|---|---|---|
| CLI installed + version | `1.27.0` | `artifacts/phase-23/catalyst-preflight.json` |
| Authenticated (project owner) | yes (`catalyst project:list` from bound dir → exit 0) | `artifacts/phase-23/catalyst-preflight.json` |
| Project binding == DHRISTI/`48361000000030003`/org `60075362708`/IN | yes | `artifacts/phase-23/preflight-deploy.json` |
| Exactly one DHRISTI project (no duplicate) | yes | `preflight_deploy.py --require-live` = PASS |
| Synthetic marker (web + backend) | present | `preflight_deploy.py` detail |
| AppSail posture (single instance, no `DATABASE_URL`, linux/amd64, no wildcard CORS) | ok | `appsail/appsail.deploy.json` |
| `infra/catalyst` placeholder scan | 0 findings | `artifacts/phase-23/catalyst-preflight.json` |
| Docker | `29.6.1` available | AppSail image `drishti-api:appsail` built (701 MB, `81b08d8083a3`) |
| API Gateway | **DISABLED** (not yet enabled) | `catalyst apig:status` |

---

## 1. Deploy-mechanism boundary (what deploys how)

Catalyst exposes a **CLI** for some components and only a **Console/SDK** path for
others. This is a platform fact (see `infra/catalyst/COMPONENTS.md`), not a DRISHTI
limitation. The runbook in §3 respects it.

| Component | Mechanism | Who can do it | Credit-spending |
|---|---|---|---|
| Functions (9) | `catalyst deploy --only functions` | agent (CLI) | pay-per-invocation (≈0 at rest) |
| API Gateway enable | `catalyst apig:enable` | agent (CLI) | usage-based |
| API Gateway **routes + throttle** | Console → API Gateway | **owner (Console)** | — |
| AppSail (custom OCI image) | `catalyst deploy appsail …` | agent (CLI) | **continuous compute** |
| AppSail **env vars / secrets** | Console → AppSail → Configuration | **owner (Console)** | — |
| Slate (web hosting) **first-time activation** | Console → Slate → Start Exploring | **owner (Console, one-time)** | — |
| Slate deploy | `catalyst deploy client` / `catalyst deploy slate` | agent (CLI) | hosting/bandwidth |
| Authorized Domains + **CORS** | Console → Authentication → Authorized Domains | **owner (Console)** | — |
| Authentication **demo users + role attributes** | Console → Authentication → Users | **owner (Console)** | — |
| Data Store **table creation** | Admin SDK (`provision_*_tables.py --apply`) — needs SDK creds **or** deployed AppSail runtime | **owner (Console creds) / runtime** | — |
| Data Store **import** (curated subset) | `catalyst ds:import <csv> --config <cfg>` | agent (CLI, after tables exist) | usage-based |
| Stratus buckets (evidence/import/report) | Console → Stratus (**no CLI verb**) | **owner (Console)** | storage |
| NoSQL / Cache | Console/SDK (no CLI verb) | **owner (Console)** | usage-based |
| Signals rule `prediction-requested` | Console → Signals (**console-only**; CLI only generates test payloads) | **owner (Console)** | per-event |
| Cron `drishti-forecast-daily` | Console → Job Scheduling / SDK | **owner (Console)** | per-run |
| QuickML LLM Serving | Console/QuickML | **owner (Console)** | inference |
| Budget alerts | Console → Billing | **owner (Console)** | — |

**Conclusion:** a fully autonomous CLI-only deployment is **not possible**. The
agent drives every CLI step; the project owner performs the Console/secret/identity
steps. The runbook below interleaves them in dependency order.

---

## 2. Target component inventory (fill live IDs during deploy)

> Status legend: `PENDING` = not yet deployed this phase · `LIVE` = deployed +
> verified (record ID/URL) · `N/A` = not used (record why).

| # | Component | Artifact | Status | Live ID / URL (no secrets) |
|---:|---|---|---|---|
| 1 | Authentication | `functions/gateway_api` + `app/gateway_context.py` | PENDING | — |
| 2 | API Gateway | `api-gateway/routes.json` (`/api/*` → `gateway_api`) | PENDING | — |
| 3 | Function `gateway_api` | `functions/gateway_api` | PENDING | — |
| 4 | Function `channel_token` | `functions/channel_token` | PENDING | — |
| 5 | Function `prediction_event` | `functions/prediction_event` | PENDING | — |
| 6 | Function `cron_forecast` | `functions/cron_forecast` | PENDING | — |
| 7 | Functions (evidence/datastore/report/notify/reconcile) | `functions/*` | PENDING | — |
| 8 | AppSail `drishti-api` | `services/ml/Dockerfile.appsail` + `appsail/appsail.deploy.json` | PENDING | — |
| 9 | Slate web client | `client/` + `web/dist` | PENDING | — |
| 10 | Data Store (operational tables) | `services/ml/app/datastore/*` + `ds-schema/*` | PENDING | — |
| 11 | Data Store import (curated subset) | `ds-import/configs/*` (106) | PENDING | — |
| 12 | Stratus buckets (evidence/import/report) | `stratus/buckets.json` | PENDING | — |
| 13 | Signal `prediction-requested` | `jobs/signals-rules.json` | PENDING | — |
| 14 | Cron `drishti-forecast-daily` | `jobs/cron-schedules.json` | PENDING | — |
| 15 | Cache (nonce/segment) | `cache/namespaces.json` | PENDING (optional) | — |
| 16 | NoSQL segments | `nosql/segments.json` | PENDING (optional) | — |

---

## 3. Interleaved deployment runbook (execute in order)

> `$` = credit-spending. `[AGENT]` = Kiro runs a CLI/SDK command. `[OWNER]` = you
> perform a Console/secret/identity action (I cannot click the Zoho Console or set
> server-side secrets). After each `[OWNER]` step, tell me and I resume.

### Stage 1 — Console prerequisites (owner, one-time)
1. `[OWNER]` Console → **Slate** → *Start Exploring* (activate Slate for the project).
2. `[OWNER]` Decide the shared signing secret `ZOHO_APPSAIL_SIGNING_SECRET` (a strong
   random string; keep it only in the Console — never in the repo/chat).

### Stage 2 — API Gateway + Functions (agent CLI)
3. `[AGENT]` `catalyst apig:enable` → capture the Gateway origin (from Console → API Gateway).
4. `[AGENT] $` `catalyst deploy --only functions` (from `infra/catalyst`).
5. `[OWNER]` Console → API Gateway: declare routes from `api-gateway/routes.json`
   (`/api/*` → `gateway_api`, auth required; `/api/channel-token`; `/api/public/health`)
   + throttling (600/min general, 120/min per-IP).

### Stage 3 — AppSail (agent CLI + owner env)
6. `[AGENT] $` `catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000`
   → capture the AppSail URL.
7. `[OWNER]` Console → AppSail `drishti-api` → Configuration: set env keys from
   `appsail/appsail.deploy.json` (`required` set), notably:
   `ZOHO_APPSAIL_SIGNING_SECRET`, `DRISHTI_REQUIRE_GATEWAY_CONTEXT=true`,
   `DRISHTI_CONTEXT_AUDIENCE=drishti-appsail`, `DRISHTI_USE_CATALYST_DATASTORE=true`,
   `DRISHTI_USE_CATALYST_STRATUS=true`, `DRISHTI_STRATUS_*_BUCKET` (from Stage 4).
   **Do not set `DATABASE_URL`.**
8. `[OWNER]` Console → Functions `gateway_api` (and event/cron functions) →
   Configuration: set `ZOHO_APPSAIL_BASE_URL` = the AppSail URL from step 6 and the
   same `ZOHO_APPSAIL_SIGNING_SECRET`.

### Stage 4 — Data Store + Stratus (owner creds/console + agent import)
9. `[OWNER]` Console → **Stratus**: create the 3 private, versioned buckets
   (evidence/import/report) per `stratus/buckets.json`; give me the bucket names.
10. `[OWNER]` Provide Catalyst **Admin SDK credentials** (client id/secret) *or* run
    the provisioners yourself:
    `DRISHTI_USE_CATALYST_DATASTORE=true python infra/catalyst/ds-schema/provision_board_tables.py --apply`
    and `… provision_disaster_tables.py --apply`; the operational reference tables
    are created the same way. (Alternatively the deployed AppSail can self-provision
    at runtime with its injected creds.)
11. `[AGENT] $` `catalyst ds:import serving-export/<Table>.csv --config ds-import/configs/<Table>.import.json`
    for the curated subset (idempotent upsert by `ExternalID`); record imported/rejected
    counts + source SHA-256 per table. At minimum import the readiness-probe reference
    table (`State`) + the golden-journey tables.
12. `[AGENT] $` copy one synthetic evidence fixture into the evidence bucket; verify
    hash/version/presign expiry.

### Stage 5 — Frontend (agent CLI + owner CORS)
13. `[AGENT] $` rebuild the web bundle **once** with the real Gateway origin:
    `VITE_API_BASE_URL=https://<gateway-origin>/api npm --prefix web run build:release`
    then `npm --prefix web run check:bundle:release` (must pass).
14. `[AGENT] $` `catalyst deploy client -m "drishti web (dev)"` (Slate).
15. `[OWNER]` Console → Authentication → Authorized Domains: add the exact Slate origin
    (enable CORS for it).

### Stage 6 — Identities + capabilities (owner console)
16. `[OWNER]` Console → Authentication → Users: create 6 demo users and set the
    `drishti_role` custom attribute (+ `district_id`/`unit_id` where scoped) for
    investigator, analyst, supervisor, policymaker, disaster_coordinator, super_admin.
17. `[OWNER]` Console → Signals: create the `prediction-requested` rule
    (`drishti_datastore` `row_inserted`, filter `PredictionRequest AND state==approved`
    → `prediction_event`); set AppSail `DRISHTI_PREDICTION_DISPATCH_ENABLED=true`.
18. `[OWNER]` Console → Job Scheduling: create cron `drishti-forecast-daily`
    (`0 0 3 ? * *` → `cron_forecast`); set AppSail `DRISHTI_FORECAST_CRON_ENABLED=true`.
19. `[OWNER]` (optional) QuickML LLM Serving deployment for the Ask DRISHTI planner.

### Stage 7 — Live verification (agent)
20. `[AGENT]` `python infra/catalyst/pipelines/smoke_test.py --base-url <appsail-url> --gateway-url <gateway-origin>`.
21. `[AGENT]` `python infra/catalyst/verification/acceptance_check.py --base-url <appsail-url> --web-url <gateway-origin> --read-endpoint /api/cases?limit=1`.
22. `[AGENT]` parameterized Playwright E2E against the Slate URL.
23. `[AGENT]` six-role allow/deny live matrix; Signal + cron execution proof (delivery,
    retry, idempotency); Data Store row + Stratus object metadata checks; CORS/replay/
    rate-limit/direct-AppSail-bypass checks.
24. `[AGENT]` capture all IDs/URLs/digests/counts + credit snapshot here and in the
    evidence manifest; disable any unused/canary resources.

### Stage 8 — Pipeline + rollback (agent + owner runner)
25. `[OWNER]` Console → Pipelines: link the repo runner; set runner variables
    `VITE_API_BASE_URL`, `DEV_APPSAIL_URL`, `DEV_GATEWAY_URL`.
26. `[AGENT]` run `pipelines/catalyst-pipelines.yaml`; prove a redeploy + AppSail
    rollback to the prior version (data retained).

---

## 4. Capability enablement matrix (enabled vs Not Used / Unavailable)

| Capability | Decision | Basis |
|---|---|---|
| Functions, API Gateway, AppSail, Data Store, Stratus, Authentication | **ENABLE** (mandatory demo) | organizer-hosting requirement |
| Signal `prediction-requested` (1) | **ENABLE** | Prompt 23 D.1 |
| Cron `drishti-forecast-daily` (1) | **ENABLE** | Prompt 23 D.1 |
| QuickML LLM Serving (Ask planner) | **ENABLE if available** in IN DC; else labelled deterministic fallback | Prompt 19 decision |
| Cache (nonce/segment) | ENABLE (bounded) | replay guard defence-in-depth |
| NoSQL | Optional — only if an enabled feature needs it | avoid duplicating Data Store |
| Zia STT/TTS/Translation (voice) | **NOT USED — Unavailable in IN DC** → browser Web Speech (labelled) | `COMPONENTS.md`; Zia catalogue has no speech |
| Zia OCR/face/object/evidence extraction | **NOT USED — out of scope** (`EVIDENCE_EXTRACTION_ENABLED=false`) | scope freeze |
| SmartBrowz (watermarked report) | Enable **only if** a visible demo capability; else Not Used | Prompt 23 D.4 |
| Mail / Push | Enable **only if** a visible demo capability; else Not Used (in-app notifications always work) | Prompt 23 D.4 |
| Circuits | **Unavailable in IN DC** → Functions + Jobs fallback | `COMPONENTS.md` |
| Zia AutoML | **Unavailable in IN DC** | `COMPONENTS.md` |

---

## 5. Cost & teardown notes

- AppSail is pinned to **one instance** (`min=max=1`) for correctness + cost.
- Only **one** Signal and **one** cron are enabled; every other rule/cron stays
  `active=false`/`enabled=false`.
- Disable any canary/duplicate resource immediately after evidence capture.
- Monitor spend in Console → Billing against the ~INR 1,800 baseline; no CLI billing
  verb exists in 1.27.0.
- GPU/model compute is **not** here — it is the separate AWS plane (Prompt 24).

---

*Live IDs/URLs, table/object counts, Signal/job execution IDs, test timestamps and
the credit snapshot are appended to this file as each stage completes.*
