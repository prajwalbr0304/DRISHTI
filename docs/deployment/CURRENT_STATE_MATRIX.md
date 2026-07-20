# DRISHTI Current-State Matrix

Generated: 2026-07-20 (Prompt 18 — truth reconciliation).
Branch: `fix/case-overview-location-map`. Catalyst project: **DHRISTI**
(`48361000000030003`, India DC). This is a **synthetic hackathon demo** — never
production.

This is the single evidence-backed inventory of every submitted route and
capability, its current vs. target home, its verified local-test state, its
(un)proven live-cloud state, and the future prompt that owns closing the gap. It
supersedes scattered status claims in the phase reports and prompts.

---

## 1. State vocabulary (never collapsed into "Complete")

| State | Meaning |
|---|---|
| **Implemented Locally** | Code + config exist and pass local tests against the synthetic AWS-RDS dev DB or in-memory Catalyst fakes. **Not deployed.** |
| **Deployed** | Pushed to a live Catalyst/AWS resource but not yet end-to-end verified by a real invocation. |
| **Live Verified** | Proven by a real deployed invocation (request/response, row write, signal delivery, GPU device). |
| **Disabled Optional** | Feature-flagged OFF and hidden from the submitted demo; recorded honestly, tested only when enabled. |
| **External Access Required** | Needs a credential/registration/licence this environment does not have. |
| **Post-Hackathon** | Deliberately out of the hackathon build. |

> As of Prompt 18 **nothing is Live Verified** — no Catalyst/AWS deployment has
> been performed yet. Everything mandatory is **Implemented Locally**; live
> verification is owned by Prompts 23 (Catalyst) and 24 (AWS ML). The strict
> acceptance gate (`acceptance_check.py --strict`) correctly reports BLOCKED.

Scope legend: **M** mandatory demo · **O** optional differentiator · **D** deferred/post-hackathon.

---

## 2. Environment snapshot (re-verified 2026-07-20)

| Tool | Version | Note |
|---|---|---|
| Python | 3.12.10 | FastAPI backend + datagen |
| Node.js / npm | v20.17.0 / 11.5.2 | web build, Catalyst Functions |
| Catalyst CLI | 1.27.0 | logged in (India DC) |
| AWS CLI | 2.17.22 | SSO profile `drishti`, ap-south-1 |
| git | 2.47.1 | |
| Docker | **CLI 29.6.1 installed**; **Linux daemon NOT running** | corrects the stale "Docker absent" claim; build unblocks once Desktop's Linux engine starts (Prompt 22) |
| Analytics DB | AWS RDS PostgreSQL (`drishti-db….ap-south-1.rds.amazonaws.com`) | writable; 100k cases loaded; Supabase fully retired |

---

## 3. Platform / foundation capabilities

| Capability | UI route | API route | Current repository | Target repository/service | Local-test | Live-cloud | Scope | Blocker | Owner |
|---|---|---|---|---|---|---|---|---|---|
| Public frontend hosting | all `/*` | — (static) | `web/` Vite build (local dev) | Catalyst **Slate**/Web Client | build+41 tests PASS | Implemented Locally / **Not deployed** | M | credit-spending deploy | P23 |
| Authentication / session | `/login` | Catalyst Auth | `web/src/auth/` + `app/gateway_context.py` (offline demo identity) | Catalyst **Authentication** | offline identity PASS | Implemented Locally / **Not proven** | M | live auth flow | P23 |
| API routing / throttling | all `/api/*` | API Gateway | `infra/catalyst/api-gateway/routes.json` (descriptor) | Catalyst **API Gateway** | JSON valid | Implemented Locally / **Not deployed** (apig disabled) | M | `apig:enable` + role mapper | P21/P23 |
| Backend application | all | all FastAPI routes | `services/ml/` FastAPI on AWS RDS (local) | Catalyst **AppSail** (Data Store) | 26/27 modules PASS | Implemented Locally / **Not deployed** | M | image build (Docker daemon) + data boundary | P21/P22/P23 |
| Operational relational store | (all data) | (all reads/writes) | **AWS RDS PostgreSQL** (direct, local) | Catalyst **Data Store** | repo abstraction + fakes | Implemented Locally / **Not imported** | M | route→DS migration + import | P21/P23 |
| Application object store | evidence/report | `/evidence`,`/reports`,`/boards/*/export` | AWS S3 (evidence) + in-mem Stratus fake | Catalyst **Stratus** | fake verified | Implemented Locally / **Not provisioned** | M | bucket provisioning + copy | P21/P23 |

---

## 4. Feature capabilities (mandatory demo set + important coverage)

| Capability | UI route | API route | Current repository | Target repository/service | Local-test | Live-cloud | Scope | Blocker | Owner |
|---|---|---|---|---|---|---|---|---|---|
| Command Center overview | `/command` | `/cases/caseload`, `/geo/coverage`, `/analytics/*`, `/forecast/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_cases`,`test_geo` PASS | Implemented Locally | M | freshness flow (P20) + deploy | P20/P23 |
| Approved FIR / structured case intake | `/intake/*` | `/intake/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_intake` 28 PASS | Implemented Locally | M | data boundary + deploy | P21/P23 |
| Evidence upload (manual metadata, **no extraction**) | `/cases/:id` (evidence) | `/evidence/*` | AWS S3 + AWS RDS | Stratus + Data Store | `test_evidence` 25 PASS | Implemented Locally | M | Stratus provisioning | P21/P23 |
| Structured import (with rejected rows) | `/imports`, `/intake/imports` | `/imports/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_imports` 18 PASS | Implemented Locally | M | data boundary | P21/P23 |
| Case decision-support (summary/similar/leads/MO) | `/cases/:id` | `/cases/*` | FastAPI + AWS RDS + embeddings | AppSail + Data Store + AWS adapter | `test_cases` 12 PASS | Implemented Locally | M | investigation-assistant journey (P20) | P20/P23 |
| Bilingual conversational query (Ask DRISHTI) | `/ask` | `/chat/*` + NL→SQL engine | FastAPI + AWS RDS + LLM (Groq, provider-neutral) | AppSail + **QuickML** semantic serving | `test_nlsql` 63 PASS (live LLM) | Implemented Locally | M | semantic planner + typed viz (P19) + voice | P19/P23 |
| Network / graph link-analysis | `/network` | `/graph/*` | FastAPI + AWS RDS (recursive-CTE graph) | AppSail + AWS adapter (graph) | `test_graph_*` PASS | Implemented Locally | O→M | curated DS projection vs adapter (P21) | P20/P21/P23 |
| Investigation Board | `/board`, `/board/:id` | `/boards/*` (34 routes) | Data Store-native (in-mem fakes) + AWS RDS (Search Around) | Catalyst **Data Store/NoSQL/Cache/Stratus/Signals** | `test_board_*` 36 PASS | Implemented Locally | M | DS provisioning + deploy | P21/P23 |
| Map / hotspots / heatmap | `/map` | `/geo/*` | FastAPI + AWS RDS + PostGIS | AppSail + AWS adapter (PostGIS) | `test_geo`,`test_geo_jurisdiction` PASS | Implemented Locally | M | deploy | P23 |
| Analytics / trends / socioeconomic / explainability | `/analytics` | `/analytics/*`, `/explain/*`, `/forecast/*` | FastAPI + AWS RDS | AppSail + AWS adapter | `test_analytics`,`test_explain` PASS | Implemented Locally | O→M | deploy | P20/P23 |
| Supervisor workload / performance | `/command` (supervisor) | `/workload/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_workload` 15 PASS | Implemented Locally | M | station/officer perf metrics (replaces placeholder) | P20 |
| Identity resolution / canonical profile | `/people/*`, `/review/entities` | `/identity/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_identity` 14 PASS | Implemented Locally | O→M | rank/scope mapping (P20) | P20/P23 |
| Money-trail analysis | `/network?mode=money` | `/money/*` | FastAPI + AWS RDS | AppSail + AWS adapter | `test_money` 9 PASS (+@slow PASS) | Implemented Locally | O | deploy | P23 |
| Casework (statements/property/court/lifecycle) | `/cases/:id` subpages | `/casework/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_casework` 16 PASS | Implemented Locally | M | data boundary | P21/P23 |
| Admin / governance console | `/admin`, `/governance` | `/admin/*`, `/governance/*` | FastAPI + AWS RDS | AppSail + Data Store | `test_phase15` 31, `test_governance` 11 PASS | Implemented Locally | O | deploy | P23 |
| Reports (watermarked, hashed) | `/admin` (reports) | `/reports/*` | FastAPI + in-mem SmartBrowz/Stratus fake | AppSail + **SmartBrowz** + Stratus | `test_phase15` PASS | **Disabled Optional** (`DRISHTI_REPORT_DELIVERY_ENABLED`) | O | enable + deploy | P23 |
| Notifications / work tasks / escalation | in-app + `/notifications` | `/notifications/*` | FastAPI (in-app always) | AppSail + **Mail/Push** (gated) | `test_phase15` PASS | in-app Implemented Locally; Mail/Push **Disabled Optional** | O | `DRISHTI_NOTIFY_ENABLED` + deploy | P23 |
| Approved-text RAG assistant | `/ask` (optional) | `/rag/*` | FastAPI + offline approved-text fake | **QuickML** RAG | `test_phase15` PASS | **Disabled Optional** (`DRISHTI_QUICKML_RAG_ENABLED`) | O | QuickML availability | P19/P23 |
| Disaster Response (replay/forecast/approval/routing) | `/er`, `/er/live`, `/er/forecast`, `/er/resources`, `/er/plans` | `/disaster/*` (31 routes) | Data Store-native (in-mem fakes); optional AWS PostGIS mirror `sql/023` | Catalyst **Data Store/Stratus/Signals** + AWS adapter | `test_disaster` 31 PASS | Implemented Locally | M | DS provisioning + deploy | P21/P23 |
| Live crime feed (read-only) | `/er` | `/disaster/*` (Open-Meteo) | Open-Meteo connector (CC BY 4.0, no key) | AppSail outbound (gated) | live smoke verified in P17 | Implemented Locally / live weather feed works | O | ops kill-switch | P23 |

---

## 5. ML / prediction plane

| Capability | UI/trigger | API route | Current repository | Target repository/service | Local-test | Live-cloud | Scope | Blocker | Owner |
|---|---|---|---|---|---|---|---|---|---|
| Governed prediction runtime (routing/lineage/validation) | approved FIR → PredictionRequest | `/predict/*` | `app/predict/*` (governed runtime; adapter contract) | Catalyst Function/AppSail → protected **AWS adapter** | `test_predict_runtime` 5 PASS, 1 skip | Implemented Locally | M | AWS adapter deploy | P24 |
| **TabFM** workload band (aggregate station review) | `/predict/jobs`, `/workload/*` | `/workload/*`, `/predict/*` | in-context/TabPFN CPU (local) | **AWS SageMaker async GPU** (TabFM CUDA) | `test_workload` 15 PASS (CPU) | Implemented Locally / **real TabFM CUDA NOT proven** | M | GPU plane + weights | P24 |
| **TimesFM** aggregate forecast | scheduled forecast | `/forecast/*` | statistical baselines (local) | AWS batch/async (TimesFM) | `test_forecast` 24 PASS (baselines) | Implemented Locally / **real TimesFM NOT proven** (scaffold) | M | version-pinned TimesFM path | P24 |
| Offender risk scoring | `/people/:id` | `/risk/*` | TabPFN/in-context CPU; `CrimeRiskScore` empty | AWS adapter (optional) | `test_risk` 6 PASS, 2 skip; **full-calibration @slow TIMEOUT on CPU** | Implemented Locally (individual score retired P13) | O | GPU or `risk-calibration` batch CLI | P24 |
| Near-repeat / KDE / graph baselines | map/forecast | `/geo/*`,`/forecast/*` | CPU (local) | Catalyst CPU / AWS adapter | covered by geo/forecast tests | Implemented Locally | M | deploy | P23/P24 |

---

## 6. AWS analytics / model plane (adapter-only; browser never touches it)

| Capability | Current repository | Target repository/service | Local-test | Live-cloud | Scope | Blocker | Owner |
|---|---|---|---|---|---|---|---|
| Retained historical/analytics corpus | AWS RDS PostgreSQL (direct from FastAPI, local) | AWS RDS behind **protected server-to-server adapter** | queries pass | Implemented Locally / adapter **Not deployed** | M | typed adapter operations (P21) | P21/P24 |
| Evidence object storage | AWS S3 bucket `drishti-synthetic-evidence-…` (provisioned) | AWS S3 (analytics artifacts) + Catalyst Stratus (app files) | provisioner exists | Deployed (bucket) / app path uses Stratus | M | boundary split | P21/P24 |
| Catalyst→AWS signed adapter | `services/aws-adapter/` (scaffold) + `infra/aws/adapter/` | AWS API Gateway + Lambda/ECS adapter | contract tests | Implemented Locally / **Not deployed** | M | AWS provisioning | P24 |
| GPU worker (TabFM/TimesFM image) | `services/gpu-worker/` + `infra/aws/gpu-worker/` (scaffold) | Private ECR image + SageMaker async GPU | offline `--plan` OK | Implemented Locally / **Not deployed** | M | Docker build + ECR + SageMaker | P24 |

---

## 7. Catalyst service usage (organizer-designated services)

| Service | DRISHTI use | Current state | Scope | Owner |
|---|---|---|---|---|
| Slate / Web Client Hosting | public SPA | Implemented Locally / Not deployed | M | P23 |
| Authentication | login/session/role source | Implemented Locally / Not proven | M | P23 |
| API Gateway | routing/auth/throttle | Implemented Locally / Not deployed | M | P21/P23 |
| AppSail | FastAPI backend (OCI) | Implemented Locally / image not built (Docker daemon) | M | P22/P23 |
| Data Store | operational relational + full-text | Implemented Locally (repo + fakes) / Not imported | M | P21/P23 |
| Stratus | evidence/report/export objects | Implemented Locally (fake) / Not provisioned | M | P21/P23 |
| Functions (8) | gateway_api + 5 event + 2 cron | Implemented Locally (`node --check` OK) / Not deployed | M | P21/P23 |
| Signals | **1 minimal** `prediction.requested` | Config only — **cannot prove live** (strict-blocked K9) | M | P23 |
| Job Scheduling / Cron | **1 minimal** `drishti-forecast-daily` | Config only — not proven | M | P23 |
| NoSQL | board presence/layout, UI prefs | Implemented Locally (fake) | O | P21/P23 |
| Cache | idempotency/ratelimit/lookup/nonce | Implemented Locally (fake) | O | P21/P23 |
| QuickML | RAG + no-code baseline | **Disabled Optional** | O | P19/P23 |
| Zia (voice/translation) | query voice + KN/EN speech | **Not integrated** (browser Web Speech fallback); voice **in scope** but Zia unverified | O→M | P19/P23 |
| Zia (OCR/vision) | — | **Not used** (out of scope by design) | D | — |
| SmartBrowz | report PDF/screenshot | **Disabled Optional** | O | P23 |
| Mail / Push | notifications | **Disabled Optional** | O | P23 |
| Circuits | branch/parallel orchestration | **Unavailable in IN DC** (documented) → Functions+Jobs | N/A | — |
| Zia AutoML | tabular training | **Unavailable in IN DC** (documented) → QuickML + AWS TabFM | N/A | — |
| Pipelines | CI/CD | Implemented Locally (`catalyst-pipelines.yaml` valid) / Not linked | M | P22/P23 |
| Domain Mappings | custom domain | **Not used** (default Catalyst domain; not a blocker) | O | P23 |
| Connections | OAuth/OIDC token lifecycle | Implemented Locally (signed-service fallback) | O | P23 |

---

## 8. Explicitly out-of-scope / deferred (never presented as implemented)

- OCR, document/FIR field extraction, evidence-media transcription, face/object
  recognition — **out of scope** (voice **query** dictation is separate and in scope).
- Official agency gauge feeds (IMD/KSNDMC/CWC/GSI/FIRMS) — **External Access Required**.
- Full OSINT / dark-web scraping — out of scope (dark-web crime is a *manually
  classified synthetic scenario* only, added in P20).
- TimeGPT / Chronos / LSTM alternate forecasters, automatic model retraining,
  production RLS/FORCE RLS — **Post-Hackathon**.
- Real directory/SSO/rank sync, multi-tenancy, full board snapshot versioning,
  1M-case/100k-user HA certification — **Post-Hackathon**.

---

## 9. Summary counts (2026-07-20)

- React destinations: **20** routes (13 crime-intelligence + 5 emergency-response + landing/login).
- FastAPI routers: **26** mounted (+ health/demo); **40** AI/analytics routes conform to the AiResult contract (3 raw reads exempt).
- Catalyst Functions: **8** (`node --check` clean). Data Store tables: operational (106 import configs) + **6** board + **14** disaster (Data Store-native). Stratus buckets: **3** (evidence/import/report).
- Minimal event plane: **1** Signal + **1** cron (both config-only, not live-proven).
- Live Verified capabilities: **0** (no deployment yet). Everything mandatory is **Implemented Locally**; live verification owned by **Prompts 23–24**.
- Strict acceptance (`acceptance_check.py --strict`): **BLOCKED** — 10/11 mandatory checks HELD/MANUAL/config-only (only K10 no-browser-secrets is release-proven).
