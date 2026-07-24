# DRISHTI — Catalyst + AWS Service Inventory (Prompt 25)

> Consolidated inventory of every cloud service DRISHTI uses, its live ID/URL, status and
> cost/cleanup state. Synthetic hackathon demo. No secrets/tokens/emails recorded.
> Live-verified 2026-07-24 (`artifacts/phase-25/aws-inventory.json`, `live-catalyst-boundary.json`).

Project **DHRISTI** `48361000000030003` · org `60075362708` · India DC · AWS acct `…5713` ap-south-1.

## 1. Zoho Catalyst (public app + operational serving/object data)

| # | Service | Live ID / URL | Status | Used? | Cost/cleanup |
|--:|---|---|---|---|---|
| 1 | **Slate** (web hosting) | `https://drishti-frvfpunc.onslate.in/` (canonical; stale `drishti-uryfmaue` to be decommissioned) | LIVE (SPA 200) | Used | hosting/bandwidth |
| 2 | **API Gateway** | `/api/*` → `gateway_api` (exact-origin CORS) | LIVE (ENABLED) | Used | usage-based |
| 3 | **AppSail** `drishti-api` | `https://drishti-api-50044118953.development.catalystappsail.in` | LIVE (`/health/live`+`/health/ready`=200) | Used | 1 instance (min=max=1) |
| 4 | **Authentication** | Catalyst IAM (role attributes) | LIVE (⚠ `DEMO_AUTH` on — RB-1) | Used | — |
| 5 | **Function** `gateway_api` | serverless domain `dhristi-60075362708.development.catalystserverless.in` | LIVE | Used | per-invocation |
| 6 | **Functions** `prediction_event`,`cron_forecast`,`cron_reconcile`,`evidence_event`,`datastore_event`,`report_event`,`notify_dispatch`,`channel_token` | serverless domain | LIVE | Used | per-invocation |
| 7 | **Data Store** | `PredictionRequest` table `48361000000043006` (+ Board/Disaster/reference tables) | LIVE | Used | usage-based |
| 8 | **Stratus** `drishti-evidence` | `https://drishti-evidence-development.zohostratus.in` (private, versioned) | LIVE (sha256 verified) | Used | storage |
| 9 | **Signals** `prediction-requested` | Row-insert on `PredictionRequest` (state==approved) → `prediction_event` | LIVE (delivery Success) | Used | per-event |
| 10 | **Cron** `drishti_forecast` | daily → `cron_forecast`; exec `48361000000061010` | LIVE | Used | per-run |
| 11 | **Cache** (nonce/segment) | replay-guard defence-in-depth | Enabled (bounded) | Used | usage-based |
| 12 | **QuickML LLM Serving** (Ask planner) | — | ⚠ live `/api/ask` 502 (RB-2) | Intended / labelled fallback | inference |
| 13 | **Zia** STT/TTS/translation | — | **Platform Unavailable** (IN DC) → browser Web Speech (labelled) | Not Used | — |
| 14 | **Zia** OCR/face/object/evidence extraction | — | Out of scope (`EVIDENCE_EXTRACTION_ENABLED=false`) | Not Used | — |
| 15 | **SmartBrowz / Mail / Push** | — | Enable only if a visible demo capability; in-app notifications always work | Optional | — |
| 16 | **NoSQL / Circuits / Zia AutoML** | — | Not Used / Platform Unavailable (IN DC) | Not Used | — |

## 2. AWS (bounded, protected custom-ML + synthetic analytics corpus)

Live read-only inventory 2026-07-24 (`artifacts/phase-25/aws-inventory.json`):

| # | Service | Live ID | Status | Cost/cleanup |
|--:|---|---|---|---|
| A1 | **SageMaker** async endpoint (T4) | — | **STOPPED** — 0 endpoints / 0 transform jobs (torn down after proof) | **cost-controlled** (ephemeral) |
| A2 | **Lambda** `drishti-aws-adapter` | present | LIVE (protected adapter; + Secrets Manager + DLQ) | ~0 at rest |
| A3 | **ECR** `drishti-gpu-worker` | `@sha256:a2944b79…` (tag 0.2.3) | present | storage (retained for redeploy) |
| A4 | **S3 + KMS** (model weights) | present | present (KMS-encrypted, versioned) | storage |
| A5 | **RDS Postgres** (synthetic analytics) | `drishti-db…ap-south-1` | reachable (AppSail server-to-server only) | compute |
| A6 | **CloudWatch alarm** | `drishti-gpu-async2-invocations` | present | — |
| A7 | **Budget** (~INR baseline) | Console | monitored | — |

## 3. Third-party-vs-Catalyst justification

- **AWS GPU (SageMaker T4)** is used for TabFM/TimesFM because Catalyst does not offer the required CUDA/foundation-model serving in the IN DC. This is the only capability delegated off-Catalyst, it is reached server-to-server, and it is torn down after proof.
- **RDS** holds the large synthetic analytics corpus read by AppSail server-to-server (documented Prompt 23 Option A). Operational serving/object data (Board, Disaster, PredictionRequest, evidence) is **Catalyst-native** (Data Store + Stratus).
- Everything user-facing (hosting, auth, gateway, app, operational data/objects, events, jobs) is **on Catalyst**.

## 4. Cleanup posture

- SageMaker endpoint **deleted** after proof — **verified zero** live.
- Exactly **one** Signal + **one** cron active; all other rules/crons `active=false`.
- AppSail pinned `min=max=1`. Disable any canary/duplicate after evidence capture.
