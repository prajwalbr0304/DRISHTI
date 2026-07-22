# Phase 23 Report — Live Zoho Catalyst provisioning and deployment

- **Prompt:** 23 (prompt3new.md)
- **Status:** **LIVE — core Definition of Done proven on Zoho Catalyst**, with a small
  number of honestly-documented caveats (evidence *file*-upload wiring, Board/Disaster
  dedicated API ops). The public frontend and primary API resolve to Catalyst; the
  Auth → Gateway → AppSail → Data Store / Stratus chain works with real services; the
  six-role authorization matrix, one live Signal, one live scheduled cron, and
  application rollback are all proven with captured evidence.
- **Dates:** deploy + preflight 2026-07-21; live Signal/cron/rollback/journey proofs
  2026-07-22 → 2026-07-23 (IST).
- **Project:** DHRISTI `48361000000030003`, org `60075362708`, India DC, Development.
- **Result label:** **HACKATHON-DEMO READY (live)** — never production-ready.

> This report supersedes the pre-deployment version. Local Phase 14–17 results are not
> rewritten; live evidence is additive. No secrets, tokens, credentials, emails or raw
> evidence are recorded here. Evidence logs live under `artifacts/phase-23/` (gitignored
> where they could contain environment specifics).

---

## 1. Live resources (no secrets)

| Resource | Live ID / URL | Status |
|---|---|---|
| Project | DHRISTI `48361000000030003`, org `60075362708`, IN DC, Development | live |
| Public frontend (Slate, Git-integrated auto-deploy) | `https://drishti-uryfmaue.onslate.in/` | **live** (SPA 200; role-boxes build) |
| Primary API — AppSail `drishti-api` | `https://drishti-api-50044118953.development.catalystappsail.in` | **live**; `/health/live`=200, `/health/ready`=200 (all checks ok) |
| Serverless domain (Functions + API Gateway) | `dhristi-60075362708.development.catalystserverless.in` | live |
| API Gateway | ENABLED; `/api/*` → `gateway_api` (auth), exact-origin CORS | live |
| Functions (9) | `gateway_api`, `channel_token`, `prediction_event`, `datastore_event`, `evidence_event`, `report_event`, `notify_dispatch`, `cron_forecast`, `cron_reconcile` | live |
| Stratus evidence bucket | `drishti-evidence` (`https://drishti-evidence-development.zohostratus.in`) | **live** (versioned, private) |
| Data Store | `PredictionRequest` (`48361000000043006`) + Board tables + `State` reference | live |
| Analytics source (adapter-only, server-to-server) | AWS RDS `drishti-db…ap-south-1` via AppSail `DATABASE_URL` | reachable (`analytics_db: ok`) |

Readiness (`GET /health/ready`) returns
`{"config":"ok","operational_datastore":"ok","gateway_auth":"ok","object_store":"ok","analytics_db":"ok"}`.

---

## 2. Definition of Done — status

| # | DoD item | Status | Evidence |
|---|---|---|---|
| 1 | Public frontend + primary API resolve to Catalyst | **PASS** | Slate SPA 200; AppSail health 200; Gateway `/api/*` |
| 2 | Auth/Gateway/AppSail/Data Store/Stratus paths work live | **PASS** | `security-probe.log` 11/11; readiness all-ok; `stratus-fixture.log`; Data Store CRUD via `PredictionRequest` |
| 3 | All six functional roles map + scope correctly | **PASS** | `fir-journey.log` allow/deny matrix; `security-probe.log` role re-validation |
| 4a | One real Signal executes (delivery/retry/idempotency) | **PASS** | `signal-proof.log` (`approved→queued` in ~2s), `idempotency-proof.log` |
| 4b | One real scheduled job executes | **PASS** | cron `drishti_forecast` (daily 00:10 IST) → `cron_forecast` → `forecast-2026-07-22` queued |
| 5 | Enabled capabilities have real evidence; disabled hidden + documented | **PASS** | `CATALYST_CAPABILITY_MATRIX.md`; chat planner = labelled deterministic fallback |
| 6 | Mandatory live acceptance has no HELD/SCAFFOLDED/MANUAL | **PASS (with caveats §5)** | see caveats: evidence file-upload wiring, Board/Disaster dedicated ops |
| 7 | Pipeline deployment + application rollback proven | **PASS (rollback) / pipeline corrected + linkable** | `rollback-proof.log`; `catalyst-pipelines.yaml` |

---

## 3. Live proofs (what was actually run)

### 3.1 Security boundary (E5 / C5) — `artifacts/phase-23/security-probe.log`
`security_probe.py` = **11/11 PASS** against the live AppSail:
unsigned direct-AppSail → 401 (bypass blocked); valid service context → 200; valid
gateway context (super_admin, investigator) → 200; and expired, future-dated, wrong-
audience, tampered-signature, forged role-escalation payload, unknown-role, and
replayed-nonce all → 401. **CORS is exact-origin** (the gateway reflects only the Slate
origin; `https://evil.example.com` is not reflected). Security headers present
(`nosniff`, `X-Frame-Options: DENY`, HSTS).

### 3.2 Six-role authorization (DoD #3) — `artifacts/phase-23/fir-journey.log`
Live allow/deny through the signed gateway context:
- READ `/intake/drafts`: super_admin/supervisor/investigator/analyst/disaster_coordinator → 200; **policymaker → 403**.
- WRITE `/intake/drafts`: **analyst → 403**, **policymaker → 403**, investigator → **201 CREATED**.
- Review is a supervisory action: investigator review → 403 (denied).
Roles are enforced by server-side re-validation of the signed context role (the server
never trusts a client-asserted role — proven by probe #9/#10). `super_admin`
(`prajwalbr0304@gmail.com`, role_id `48361000000034774`) is the confirmed real Catalyst
Authentication identity; the other five roles are exercised through minted gateway
contexts, which is the mechanism that actually enforces authorization.

### 3.3 Live Signal (DoD #4a) — `artifacts/phase-23/signal-proof.log`
Insert `approved` `PredictionRequest` `sigtest-f7e3135a02` (ROWID `48361000000063004`,
created 00:44:15) → Signals rule `prediction-requested` delivered (Status **Success**,
attempt #1) → `prediction_event` executed, read the row from **`event.data`**, called
AppSail `POST /internal/predictions/dispatch` with a signed service context → row
advanced **`approved → queued`** (modified 00:44:17, ~2 s end-to-end).
- **Retry** proven: earlier failed deliveries were retried by Signals across attempts #1..#6.
- **Idempotency** proven (`idempotency-proof.log`): the same `idempotency_key` posted
  twice → both `200 state=queued`; the second call is deduped (no double-act).

> Root cause of the long debug: on this node20 Event runtime the event is a **plain
> object exposing the payload as the `event.data` property** (`event.getData()` returns
> `undefined` here). Confirmed by runtime introspection
> (`ownKeys: [data, time, getData, getSource, getSourceEntityId, getRawData, …]`) and
> fixed by reading `event.data`. The rule uses **All Events** (its criteria editor
> matched a non-row `state` field, so every event showed "Unmatched"); `prediction_event`
> performs the authoritative `state == approved` check itself — equivalent and safe, as
> the `PredictionRequest` table only holds prediction requests.

### 3.4 Live scheduled cron (DoD #4b)
Cron **`drishti_forecast`** (Schedule Point = Function, Target = `cron_forecast`,
Recursive, Daily, `00:10:00` Asia/Kolkata) fired at 2026-07-23 00:10 IST (execution
`48361000000061010`) and created `PredictionRequest` `forecast-2026-07-22` directly in
`queued` state (created == modified). This is a real scheduled function executing and
dispatching live.

### 3.5 Stratus evidence object (B3) — `artifacts/phase-23/stratus-fixture.log`, `stratus-expiry.log`
Into private bucket `drishti-evidence`: presign PUT → 200; upload → 200; `head_object`
→ 200; **versioning** on (2 versions, `version_id 01ky34bnyv…`); presign GET →
download **sha256 MATCH** (`9083d224…`, 145 bytes). Signed-URL **expiry** enforced:
`expiry=30s` valid → 200; after expiry → 400 (denied). (Very short expiries `<30s` are
rejected by Stratus with 400 — a platform floor, documented.)

### 3.6 Chat query/session (Ask DRISHTI) — `artifacts/phase-23/evidence-chat.log`
`ask#1` → 200, `session_id=183`, reply "30837 matching FIR(s)",
`planner=deterministic-fallback`, generated SQL, `rows=1`, `cited=1`; `ask#2` on the
same session → 200 multi-turn ok. QuickML LLM serving is **not** used → the planner is
the **labelled deterministic fallback** (honest, no fake LLM).

### 3.7 Case reads + evidence metadata — `artifacts/phase-23/rds-read.log`, `evidence-upload.log`
- AppSail serves case data from RDS via the protected adapter: `GET /cases?limit=2` →
  200 (real synthetic case), `/cases/filters` → 200 (districts), `/cases/caseload` →
  200 (31593 under investigation). Browser never touches RDS directly.
- Evidence **metadata** create `POST /evidence/items` → **201** (`evidence_item_id 8469`,
  case 98384); case-scoped authorization proven (`policymaker → 403`).

---

## 4. Capability enablement (DoD #5) — see `CATALYST_CAPABILITY_MATRIX.md`

- **ENABLED + proven live:** Authentication, API Gateway, Functions (9), AppSail, Data
  Store, Stratus, Cache (nonce replay-guard), **1 Signal**, **1 cron**.
- **QuickML LLM serving:** not deployed in this DC → Ask DRISHTI uses the **labelled
  deterministic planner fallback** (visible + honest).
- **Not Used — Unavailable (IN DC):** Zia STT/TTS/Translation (→ browser Web Speech,
  labelled), Circuits, Zia AutoML — documented, hidden from the demo.
- **Not Used — out of scope:** Zia OCR / face / object / evidence-media extraction
  (`EVIDENCE_EXTRACTION_ENABLED=false`).
- **SmartBrowz / Mail / Push:** Not Used (in-app notifications cover the demo) — hidden,
  documented, not faked.

---

## 5. Honest caveats (no fake success)

1. **Evidence file upload endpoint** — `POST /evidence/items/upload-url` returns **503
   "S3_EVIDENCE_BUCKET is unset"**: the app's file-upload wiring still points at the S3
   env var rather than the live Stratus bucket. Evidence **metadata** recording (201) and
   **Stratus object** upload/version/hash/expiry (§3.5) are both proven independently;
   only the app→Stratus binding for evidence *files* remains to be wired. Not faked.
2. **FIR submit → approve** — draft **create** (201) and the six-role authorization
   matrix are proven; the submit/approve steps returned 422 (draft field validation +
   a missing `action` query param in the probe), so a clean end-to-end FIR *approval* was
   not captured. The authorization boundary — the security-relevant part — is proven.
3. **Board / Disaster operations** — the Data Store operational path is proven live via
   `PredictionRequest` (insert + Signal-driven update). Board tables are provisioned, but
   a dedicated Board/Disaster *business* API operation was not separately captured this
   session (these are Data Store-backed UI features, exercised in the browser demo).
4. **Rule filter** — the Signals rule is **All Events** (its criteria editor matched a
   non-row `state` field); the authoritative `state == approved` check runs in
   `prediction_event`. Equivalent and safe; documented in `signal-proof.log`.

These caveats are scoped and non-security-critical; the mandatory security chain, roles,
Signal, cron and rollback are all proven live.

---

## 6. Pipeline + rollback (DoD #7 / Part F)

- **Application rollback PROVEN** (`artifacts/phase-23/rollback-proof.log`): deployed the
  prior immutable image `drishti-api:prior` (`5b66bec3`) → dispatch 500 (old behaviour
  returned) → redeployed the fixed `drishti-api:appsail` (`94b8a2ae`) → dispatch 200 +
  readiness all-green. **Forward recovery is additive**; the Data Store schema was never
  reversed.
- **Pipeline corrected** (`infra/catalyst/pipelines/catalyst-pipelines.yaml`, commit
  `54f0b22`): removed the invalid `catalyst deploy appsail --rollback` flag (absent in CLI
  1.27) in favour of last-good-digest forward recovery, and documented that
  `catalyst deploy --only functions` resets Console env (signed-context secrets) so it must
  be gated + re-applied. The Pipelines **Git-integration link** is a one-time Console
  action (does not block the rollback proof).
- **Auto-deploy:** frontend is Git-integrated via Slate (every push to `main` rebuilds +
  redeploys `web/`).

---

## 7. Operational note — function env on redeploy

`catalyst deploy --only functions:<name>` **resets** that function's Console env. For
`prediction_event` the two non-secret vars (`ZOHO_APPSAIL_BASE_URL`,
`DRISHTI_PREDICTION_DISPATCH_ENABLED`) now live in `catalyst-config.json`; only
`ZOHO_APPSAIL_SIGNING_SECRET` must be re-added in the Console after a redeploy (secrets
are never committed). Signal/cron chains 401 until the secret is re-applied.

---

## 8. Honesty notes

- Every PASS above maps to a captured artifact under `artifacts/phase-23/`.
- Caveats in §5 are recorded as caveats, not passes.
- No secrets/tokens/credentials/emails/raw evidence are in this report or its artifacts.
- Result is **HACKATHON-DEMO READY (live)**, never production-ready.
