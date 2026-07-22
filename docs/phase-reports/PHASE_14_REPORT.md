# PHASE 14 — Catalyst-native deployment + external AWS custom-model integration

Status date: 2026-07-18
Owner: implementation agent (Kiro)
Catalyst project: **DHRISTI** (ID `48361000000030003`), India (IN) DC, Development environment.

> **CORRECTION ADDENDUM (2026-07-20, Prompt 18 re-verification).** The statements
> below that "Docker is not installed" / "Docker absent" are **now stale**.
> Re-verified on this machine: `docker --version` → **Docker version 29.6.1** (the
> **CLI is installed**). What is missing is a **running Linux daemon** —
> `docker info` returns "failed to connect to the docker API at
> npipe:////./pipe/dockerDesktopLinuxEngine". So the AppSail/GPU image builds are
> blocked only until Docker Desktop's Linux engine is started (verified/started in
> `prompt3.md` Prompt 22), not by an absent CLI. Other tool versions re-verified:
> Node v20.17.0, npm 11.5.2, Python 3.12.10, Catalyst CLI 1.27.0, AWS CLI 2.17.22,
> git 2.47.1. Historical text retained below unchanged as evidence.

> **Honesty note (read first).** This report distinguishes three states and never
> conflates them:
>
> - **DONE** — executed and verified in this environment (command output or file evidence).
> - **SCAFFOLDED** — real artifact committed to the repo, but not yet deployed to the
>   cloud (blocked on a tool/credit/console/GPU dependency named in each row).
> - **BLOCKED** — cannot be completed in the current environment; the exact platform
>   blocker is recorded so it is not silently skipped or faked.
>
> No cloud deployment, GPU run, AWS provisioning, or credit spend is claimed unless it
> appears under **DONE** with evidence. Placeholder/stubbed behavior is never labelled
> as a real model or a live deployment.

---

## 0. Executive status

| Part | Description | State |
|---|---|---|
| A | Catalyst CLI login + DHRISTI project binding + local config | **DONE** (verified) |
| A.8/J | Plan-baseline (INR 1500 + 300) + Part J cost safety | **BLOCKED** — no CLI billing API; console-only. **Kept (J)**: confirm credit balance, avoid duplicate AppSail/Signals/crons, conservative sizing, AWS budget alarm, stop GPU after test, cleanup; 50/75/90% Catalyst automation **OPTIONAL** (see §9) |
| B | Component allocation + 26-row compliance matrix | **DONE** — matrix + committed component scaffolding (functions/client/appsail/ds-import/jobs/gateway/pipeline), locally verified (§3.1–3.2) |
| C | React → Slate / Web Client Hosting + Catalyst Auth | **IMPLEMENTED (verified)** — `web/src/auth/` (embedded Catalyst Auth), single API-Gateway base URL, SPA/caching/CORS/badge; build+41 tests+secret-scan pass; cloud deploy HELD (§5, `PHASE_14_PARTC_REPORT.md`) |
| D | FastAPI → AppSail (lightweight OCI, health, non-root) | **SCAFFOLDED (verified)** — `Dockerfile.appsail` (now binds `X_ZOHO_CATALYST_LISTEN_PORT`) + health endpoints + `appsail.deploy.json`; image build/deploy **BLOCKED on Docker** (§6) |
| E | Data Store / Stratus / NoSQL / Cache mapping + migration | **SCAFFOLDED (verified)** — mapping + repository + **106 import configs** + idempotent importer; import pending (§7) |
| F | Secure Catalyst→AWS adapter (signed boundary, private RDS, protected adapter, capability-gaps, scoped SSE channel) | **IMPLEMENTED** — inbound signed-context boundary + adapter round-trip + channel interop verified (`PHASE_14_PARTF_REPORT.md`); AWS provisioning / IAM / RDS lockdown **HELD** (§8) |
| G | ML/RAG placement + prediction runtime (+ G.1–G.5 scoping) | **IMPLEMENTED** — `app/predict/{placement,dispatch_policy,validation,lineage,runtime,comparison,enablement,router}.py` + `infra/catalyst/ml-placement.json`; **G.1/G.2** reduced routing matrix + reduced model set (deferred models documented, off by default); **G.3** one SageMaker-async GPU mechanism (multi-mode deferred); **G.4** correction-staleness + inference-only governance; **G.5** six committed tests (`tests/test_predict_runtime.py`, 5 passed / 1 skipped); verified offline (`PHASE_14_PARTG_REPORT.md`); SageMaker/ECR + real GPU + QuickML enable **HELD** (§8.7) |
| H | Job Scheduling / Signals / Circuits (+ Part H minimal scoping) | Circuits + AutoML **UNAVAILABLE in IN DC** (verified, §8.4); **minimal event plane** (§8.8): ONE `prediction.requested` Signal + ONE `drishti-forecast-daily` cron are `tier:minimal`, all else optional/deferred (Mail/Push→Prompt 15); retry + failed-job state + persist-before-emit kept; `jobs/` all disabled until enabled |
| I | Pipelines CI/CD (+ Part I minimal scoping) | **SCAFFOLDED** — `catalyst-pipelines.yaml` simplified to the **7-step** hackathon flow (install→lint/test→build→secret-scan→dev-deploy→health/auth/prediction smoke→retain-for-rollback); prod-promotion/SBOM/GPU-rebuild/DS-forward-recovery/concurrency-lock **deferred**; GPU worker deploys **separately** (`infra/aws/gpu-worker/`); `smoke_test.py` +prediction checks (§8.8) |
| K | Verification (reduced to the demo) | **Reduced to 11 demo checks** — `infra/catalyst/verification/` (`acceptance-checklist.json` + `acceptance_check.py`); offline **2 PASS/7 HELD/2 MANUAL**, K8/K9/K10 proven now, K1–K7 held on deploy, K6 on GPU, K5/K11 manual/ops; NoSQL/Cache/Mail/Push/SmartBrowz/QuickML/Circuits test-only-when-enabled (§10) |

**The only planned human pause — the Zoho browser login/consent — was already completed by
the user** (login as `prajwalbr0304@gmail.com`, IN DC). Every step after that in Part A
(whoami, project:list, init, project binding, verification) was performed by the agent via
CLI with no further user interaction.

**Hard environment blockers discovered (not optional design choices):**

1. **Docker is not installed** on this machine (`docker : term not recognized`). The AppSail
   custom-runtime OCI image and the GPU-worker image cannot be *built* locally. All image
   artifacts (`Dockerfile.appsail`, `services/gpu-worker/`) are ready; the build+push+deploy
   steps are documented in §6 / §11 and require Docker (or a CI runner that has it).
2. **No NVIDIA GPU / CUDA** in this environment. A real TabFM run asserting `device=cuda`
   cannot execute here; it must run on AWS SageMaker/Batch GPU. The fail-closed contract
   (G.3.4) is implemented so a `tabfm` job *errors* rather than silently returning a fallback.
3. **Credit-spending cloud deploys** (`catalyst deploy`, `catalyst ds:import`, AppSail/Slate
   creation, AWS SageMaker/Batch/ECR) are held pending explicit go-ahead because the hackathon
   budget is finite (INR ~1800) and several steps are hard to reverse. See §9/§11.
4. **Circuits** and **Zia AutoML** are **not available in the IN data center** (verified
   against current official docs, §8.4). The compliance matrix records these honestly and the
   design uses the documented Functions + Job Scheduling fallback.

---

## 1. Part A — CLI login and project binding (DONE, verified)

### 1.1 Commands executed (secrets redacted)

```text
catalyst --version                         -> 1.27.0
catalyst whoami                            -> Logged as: prajwalbr0304@gmail.com
catalyst project:list                      -> DHRISTI / 48361000000030003 ; Project-Rainfall / 48361000000013024
# in infra/catalyst/ :
catalyst init --project 48361000000030003 --org 60075362708 -ni
                                           -> ".catalystrc file has be successfully created"
                                           -> "Catalyst initialization complete!"
catalyst project:list  (from infra/catalyst) -> "DHRISTI (active) (base)"

# re-verified live 2026-07-18 (this session), no user interaction after browser login:
node --version / npm --version             -> v20.17.0 / 11.5.2
catalyst whoami                            -> Logged as: prajwalbr0304@gmail.com
catalyst project:use 48361000000030003     -> "Successfully made project active"
catalyst help                              -> full command list; NO billing/usage command (see A.8/§9)
```

The agent used `-ni` (non-interactive) + `--project` + `--org` so no interactive
arrow/checkbox prompt could hang, and no project/component selection was delegated to the user.

### 1.2 Binding evidence — `infra/catalyst/.catalystrc` (no tokens)

| Field | Value |
|---|---|
| Project name | DHRISTI |
| Project ID | `48361000000030003` |
| Org ID | `60075362708` |
| Environment | Development (`type 3`) |
| Dev domain | `dhristi-60075362708.development` |
| Timezone | Asia/Kolkata (India DC) |

The CLI auth token lives **outside this repo** in the OS user-data directory the CLI manages
via `env-paths` — verified on this machine at `%APPDATA%\zcatalyst-cli-nodejs`
(`C:\Users\Prajwal\AppData\Roaming\zcatalyst-cli-nodejs`, holding `.zcatalyst-cli-key`,
`zcatalyst-cli-v1.json`, `Config/`). (`~/.catalyst` does **not** exist on this machine; the
earlier note to that effect was corrected after direct inspection — names only, token contents
never read.) No token, refresh token, or client secret is written into the repository.
`catalyst.json` is created when features (functions/client/appsail) are scaffolded; the project
binding itself lives in `.catalystrc`, which was verified active.

> **No duplicate project was created.** The existing credited `DHRISTI` project was selected by
> ID. `Project-Rainfall` was left untouched.

### 1.3 gitignore hardening (DONE)

Added a Catalyst section to the root `.gitignore`: ignores `.catalyst/` caches, deploy zips,
functions `node_modules/`, per-function `.env`, `secrets.json`, and generated serving exports.
Safe config (`.catalystrc`, `catalyst.json`, `app-config.json`) remains committable.

---

## 2. Environment & tooling facts

| Tool | Version | Note |
|---|---|---|
| Catalyst CLI | 1.27.0 | India DC login active |
| Node.js | v20.17.0 | AppSail/Functions/React toolchain |
| npm | 11.5.2 | |
| Python | 3.12.10 | FastAPI + migration scripts |
| AWS CLI | 2.17.22 | profile `drishti` → acct `860510875713`, `ap-south-1`, AdministratorAccess |
| Docker | **absent** | **blocks local OCI image build** |
| GPU / CUDA | **absent** | **blocks local real-TabFM run** |

---

## 3. Part B — Catalyst component allocation

Deployment boundary (unchanged from the phase objective): Catalyst hosts the public app,
operational data, object store, auth, gateway, functions, jobs, signals, reports and CI/CD.
AWS is retained only for the complete historical/analytics corpus and the custom GPU/geospatial
model plane. Every AWS use carries a capability-gap justification (§8.5).

### 3.1 Organizer capability compliance matrix (26 rows)

Disposition legend: **Used(D)** deployed+tested · **Used(S)** scaffolded + locally verified,
cloud deploy pending · **Not used** capability genuinely absent from scope · **Unavailable**
region/platform gate with evidence. Every **Used(S)** row now cites a committed artifact (Part B
built these this session — see §3.2 for the file list + verification evidence).

| # | Capability | Required Catalyst service | DRISHTI disposition |
|---:|---|---|---|
| 1 | Serverless backend logic | Functions | **Used(S)** — 8 Node20 functions in `infra/catalyst/functions/` (gateway_api + evidence/datastore/prediction/report/notify events + 2 crons); `node --check` clean; deploy pending |
| 2 | Docker image deployment | AppSail custom OCI | **Used(S)** — `services/ml/Dockerfile.appsail` (linux/amd64, non-root, now binds `X_ZOHO_CATALYST_LISTEN_PORT`). Build **BLOCKED on Docker** (CI runner or §11) |
| 3 | Full managed web application | AppSail | **Used(S)** — FastAPI is the AppSail runtime; `infra/catalyst/appsail/appsail.deploy.json` descriptor; `/health/live|ready` DONE |
| 4 | React/Vite frontend | Slate or Web Client Hosting | **Used(S)** — Slate (`react-vite`) + `web/public/_redirects` + `infra/catalyst/client/`; single gateway API base URL; deploy pending |
| 5 | Custom domain + SSL | Domain Mappings | **Not used** — no domain supplied for the hackathon; generated Catalyst/Slate URLs used. Recorded as capability-absent-**input**, not a platform gap |
| 6 | Operational relational data | Data Store | **Used(S)** — `app/datastore/mapping.py` + `CatalystDataStoreRepository` + **106 generated import configs**; curated import pending |
| 7 | Semi-structured data | NoSQL | **Used(S)** — `app/nosql.py` (ABC + in-mem fake + SDK impl) + `nosql/segments.json` (UiPreferences/Presence[TTL]; BoardLayout+FeedEnvelope reserved-disabled); never a duplicate of relational records |
| 8 | Application object/blob storage | Stratus | **Used(S)** — `app/stratus.py` (presign up/down + versioning + head) + `stratus/buckets.json` (evidence/import/report, private, versioned) + `evidence_event`; S3→Stratus copy pending |
| 9 | Cache | Cache | **Used(S)** — `app/cache.py` (idempotency/ratelimit/nonce/lookup, `add_if_absent`) + `cache/namespaces.json`; backs the signed-context nonce-replay guard (`app/gateway_context.py`) |
| 10 | Full-text application search | Data Store | **Used(S)** — **16 search-enabled tables** (`search_enabled_tables()`); Data Store search in `CatalystDataStoreRepository.search`; no external engine |
| 11 | Text LLM/RAG/knowledge base | QuickML | **Used(S)** — `app/quickml.py` (RAG client: citations + refusal; offline fake refuses by default, verified) + `quickml/rag-knowledge-base.json`; disabled until `DRISHTI_QUICKML_RAG_ENABLED` |
| 12 | No-code ML pipeline | QuickML | **Used(S)** — `quickml/nocode-experiment.json` (area-workload-band baseline: leakage/fairness gated, human approval, no auto-promote) |
| 13 | Automated tabular training | Zia AutoML | **Unavailable** — AutoML not offered in IN/EU/AU/JP/SA/CA DCs ([docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl)). Fallback: QuickML baseline + justified AWS TabFM |
| 14 | OCR/face/image/object/barcode/ID | Zia Services | **Not used** — input is digital/manual; extraction deferred. `evidence_event` does hash/size/scan only, **no OCR/extraction** |
| 15 | Speech/voice/translation | Zia Services | **Not used** — voice/transcription deferred |
| 16 | PDF/image/screenshot/headless | SmartBrowz | **Used(S)** — `app/smartbrowz.py` (render_pdf/screenshot → watermark+sha256+version; fake verified) + `report_event` (workflow §11) |
| 17 | Login/signup/session identity | Authentication | **Used(S)** — Catalyst Auth → `gateway_api` derives the role **server-side** (client identity headers stripped) |
| 18 | API routing/auth/throttling | API Gateway | **Used(S)** — `infra/catalyst/api-gateway/routes.json` (auth=required + sliding-window throttle); gateway fronts `gateway_api`, which invokes AppSail (AppSail is not a native Gateway target) |
| 19 | OAuth token lifecycle | Connections | **Used(S)** — `app/connections.py` + `connections/connections.json`; returns a token only when an OAuth/OIDC Connection is configured, else honestly reports the signed-service-auth gap (§8.3) |
| 20 | Scheduled jobs/cron | Job Scheduling | **Used(S)** — `infra/catalyst/jobs/cron-schedules.json` (reconcile/forecast + reserved §13–16), all **`enabled:false`** until owning phases; `cron_reconcile`/`cron_forecast` functions |
| 21 | Data/upload/auth event reactions | Signals + Event Functions | **Used(S)** — 5 event functions + `infra/catalyst/jobs/signals-rules.json` (evidence upload, canonical-version, prediction req/result, report.ready, notify.requested, user_signedup) |
| 22 | Cross-component event routing | Signals | **Used(S)** — same registry; custom `drishti_app` publisher routes cross-component events |
| 23 | Branch/parallel workflow | Circuits | **Unavailable** — Circuits not offered in IN/EU/AU/JP/SA/CA DCs ([docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/serverless/circuits/get-a-component-instance/)). Fallback: idempotent Functions + Job Scheduling (re-verified 2026-07-18 via the datastore SDK doc DC note) |
| 24 | Transactional email | Mail | **Used(S)** — `notify_dispatch` data-minimized templates; disabled until `DRISHTI_NOTIFY_ENABLED` |
| 25 | Web/mobile push | Push Notifications | **Used(S)** — `notify_dispatch` push intent (mobile-app-id gated); data-minimized |
| 26 | CI/CD | Pipelines | **Used(S)** — `infra/catalyst/pipelines/catalyst-pipelines.yaml` (5 stages: validate/scan/build/deploy/release) + `smoke_test.py` |

No row is omitted. Rows 13 and 23 are **Unavailable** with current documentation evidence
(re-verified 2026-07-18); rows 5, 14, 15 are **Not used** for scope/input reasons. All other
rows are **Used(S)**: the component is allocated, the artifact is committed and locally verified,
and only the credit-spending cloud deploy remains (held for go-ahead).

### 3.2 Part B implementation — committed artifacts + verification (this session)

> **Correction to earlier drafts.** Previous revisions of this report described the
> Function/client/AppSail-config/ds-import/jobs/pipeline artifacts as if they were already
> present. In fact only `Dockerfile.appsail`, `requirements.appsail.txt`, the health endpoints
> and `app/datastore/{mapping,repository}.py` existed. **Part B (this session) actually creates
> the remaining component scaffolding.** Every disposition above now points to a file that
> exists in the repo. No cloud deploy is claimed.

**Committed artifacts**

- **Project manifest:** `infra/catalyst/catalyst.json` (functions targets + client).
- **Functions (`infra/catalyst/functions/`):** `gateway_api` (advancedio public facade),
  `evidence_event`, `datastore_event`, `prediction_event`, `report_event`, `notify_dispatch`
  (event), `cron_reconcile`, `cron_forecast` (cron, **no schedule registered**). Each has
  `index.js` + `catalyst-config.json` (node20) + `package.json`. `_shared/context.js` is a
  non-deployed reference. `README.md` documents the signed-context contract + Signals map.
- **Inbound trust boundary (AppSail side):** `services/ml/app/gateway_context.py`
  (`verify_signed_context` — HMAC over the base64url payload, ms timestamps matching JS
  `Date.now()`, scope/expiry/skew checks, nonce-replay cache) + `app/internal/router.py`
  (`/internal/ping` guarded proof endpoint), wired into `app/main.py`. The **outbound** AWS
  adapter already existed (`app/predict/{adapter,envelope,routing}.py`) and is unchanged.
- **Frontend hosting:** `web/public/_redirects` (SPA + `/app/*` fallback),
  `infra/catalyst/client/{client-package.json, slate-config.toml, README.md}`, and
  `VITE_DEMO_BADGE` added to `web/.env.example`.
- **AppSail:** `services/ml/Dockerfile.appsail` fixed to bind
  `${X_ZOHO_CATALYST_LISTEN_PORT:-${APP_PORT:-9000}}` (CMD + HEALTHCHECK) +
  `infra/catalyst/appsail/{appsail.deploy.json, README.md}` (env-key contract; `DATABASE_URL`
  explicitly **not** set for the CRUD path).
- **Data Store import:** `infra/catalyst/ds-import/{generate_import_configs.py,
  import_serving_subset.py, README.md}` + **106 generated `configs/*.import.json`** +
  `import-manifest.json` + `reserved-namespaces.json`.
- **Jobs / Signals / API Gateway:** `infra/catalyst/jobs/{cron-schedules.json,
  signals-rules.json, README.md}` (all disabled/inactive) + `infra/catalyst/api-gateway/
  {routes.json, README.md}`.
- **CI/CD:** `infra/catalyst/pipelines/{catalyst-pipelines.yaml, smoke_test.py, README.md}`.

**Verification performed (local, offline — no cloud, no credit spend)**

- All committed JSON validated (`python -m json.tool` over `infra/catalyst/**/*.json` → 0 bad).
- All 8 Function `index.js` + `_shared/context.js` pass `node --check`.
- New Python compiles (`py_compile`); `app.main` imports cleanly and registers `/internal/ping`
  (GET+POST) + the health routes.
- **Signed-context interop (Node → Python) verified end-to-end:** a Node-signed context is
  accepted by `verify_signed_context`; a **forged signature**, a **replayed nonce** and an
  **expired context** are all rejected (4/4 checks).
- ds-import generator produced 106 configs; the importer is idempotent (stable content hash
  across runs) via `CatalystDataStoreRepository.bulk_upsert`.
- Regression: `pytest --collect-only` = **327 tests, no import errors**; `tests/test_workload.py`
  = **15 passed**.

**Also committed this session (gap-closure pass)**

- **Component contracts** (narrow ABC + in-memory fake + Catalyst-SDK impl + env-gated factory):
  `app/{stratus,nosql,cache,smartbrowz,quickml,connections}.py` (all compile + import; offline
  RAG refuses by default; SmartBrowz fake renders a watermarked+hashed doc — verified) with
  descriptors `infra/catalyst/{stratus/buckets.json, nosql/segments.json, cache/namespaces.json,
  quickml/{rag-knowledge-base,nocode-experiment}.json, connections/connections.json}` +
  `infra/catalyst/COMPONENTS.md` (capability→artifact index + live CLI evidence).
- **Full per-workflow specs:** `docs/phase-reports/PHASE_14_WORKFLOWS.md` — all 18 workflows with
  owner, trigger, typed I/O, idempotency key, state machine, retry/timeout, DLQ/failed-item,
  audit & lineage, metrics/alerts, credit limit, rollback/replay.
- **End-to-end synthetic fixtures:** `infra/catalyst/workflows/fixtures/wf{01..12,17,18}.fixture.json`
  (+ README). 13–16 fixtures are **deferred** (phase-order rule).
- **Billing Budget/Report:** `infra/catalyst/billing/budget.json` (plan baseline INR 1,800,
  alerts at 50/75/90%, cost controls, console-only).

**Live CLI inspection of the credited project (2026-07-18) + corrections (vs earlier drafts)**

- Inspected `DHRISTI` after login (`catalyst help`). CLI-managed components: `functions`,
  `client`, `appsail`, `slate`, `apig`, **`ds:import`/`ds:export`/`ds:status`**, `deploy`,
  `event:generate`, `signals:generate`, `config`, `iac`. Console/SDK-managed (no CLI verb):
  QuickML, Stratus, NoSQL, Cache, SmartBrowz, Connections, Circuits, Zia, Mail, Push, Pipelines,
  billing — so per-project availability for those is governed by IN-DC docs + console, not a
  readable CLI gate (recorded honestly).
- **Correction:** an earlier draft of this report claimed there is "no `catalyst ds:import` CLI".
  **That was wrong.** `ds:import`/`ds:export`/`ds:status` exist (verified above). Data Store bulk
  load is `catalyst ds:import <csv> --config <cfg>` with config `{table_identifier,
  operation:"upsert", find_by:"ExternalID"}` — idempotent upsert by ExternalID. The generator now
  emits that real schema (106 configs regenerated); `import_serving_subset.py` is the offline/CI
  equivalent (SDK `bulk_upsert`).
- AppSail custom OCI runtimes do **not** use `app-config.json`; config is via
  `catalyst deploy appsail` flags / console (kept in `appsail.deploy.json` as the reviewed source).
- The container must listen on `X_ZOHO_CATALYST_LISTEN_PORT` (fixed).

---

## 4. Workflow inventory (owners, triggers, idempotency, DLQ)

Catalyst Pipelines owns CI/CD only. Data/event workflows use Functions, AppSail, Data Store,
Stratus, Signals/Event Functions and Job Scheduling. QuickML owns eligible no-code ML/RAG.
AWS Batch/SageMaker owns justified custom model computation. **Circuits is not used (IN DC
gate); idempotent Functions + Job Scheduling replace branch/parallel orchestration.**

Idempotency key convention (all model-producing workflows):
`<task>:<subject>:<cutoff>:<feature-schema-version>:<model-version>:<source-version-hash>`.

> **Full specifications:** each workflow below is fully specified (owner, trigger, typed
> input/output, idempotency key, state machine, retry/timeout, DLQ/failed-item, audit & lineage,
> metrics/alerts, credit limit, rollback/replay) in **`docs/phase-reports/PHASE_14_WORKFLOWS.md`**,
> with an end-to-end synthetic fixture per workflow in
> **`infra/catalyst/workflows/fixtures/`** (13–16 fixtures deferred per the phase-order rule).
> The table below is the index.

| # | Workflow | Owner | Trigger | State |
|---:|---|---|---|---|
| 1 | `catalyst-ci-cd` | Pipelines | repo change / manual release | SCAFFOLDED |
| 2 | `bootstrap-catalyst-serving-data` | CLI `ds:import` + Stratus | initial deploy / rebuild | SCAFFOLDED (import pending) |
| 3 | `structured-intake-and-import` | AppSail/Functions + Data Store + Stratus | draft save / submit / approve / import | SCAFFOLDED |
| 4 | `digital-evidence-ingestion` | Stratus + Data Store + Signals + isolated scanner | file upload | SCAFFOLDED (scan job disabled) |
| 5 | `identity-resolution-and-graph-refresh` | AppSail/Jobs + protected AWS adapter | validated person/party change | SCAFFOLDED |
| 6 | `feature-snapshot-and-staleness` | Data Store event → Event Function/AppSail | approved canonical version change | SCAFFOLDED |
| 7 | `custom-prediction-dispatch-and-result` | Jobs + AppSail/Function + AWS adapter | approved PredictionRequest | SCAFFOLDED |
| 8 | `model-training-evaluation-and-release` | QuickML + AWS Batch/SageMaker | approved offline experiment | SCAFFOLDED |
| 9 | `aggregate-and-spatiotemporal-forecast` | Jobs + AWS Batch/SageMaker | scheduled/approved run | SCAFFOLDED |
| 10 | `approved-knowledge-rag` | QuickML | approved SOP KB release | SCAFFOLDED |
| 11 | `report-generation-and-delivery` | Jobs/AppSail + SmartBrowz + Stratus + Signals | authorized report request | SCAFFOLDED |
| 12 | `notification-delivery` | Signals + Mail/Push | approved lifecycle event | SCAFFOLDED |
| 13 | `investigation-board-activity-and-export` | AppSail + Data Store/NoSQL/Cache + Signals + SmartBrowz | board mutation/replay/export | **DISABLED scaffold** — owned by Prompt 16 |
| 14 | `hazard-feed-ingestion-and-freshness` | Jobs + Functions/AppSail + Stratus/Data Store | replay cron / connector | **DISABLED scaffold** — owned by Prompt 17 |
| 15 | `hazard-forecast-review-and-alert` | Functions + Jobs + AWS adapter | validated readings/window | **DISABLED scaffold** — owned by Prompt 17 |
| 16 | `resource-allocation-and-routing` | AppSail/Jobs + AWS OR-Tools/PostGIS | approved planning request | **DISABLED scaffold** — owned by Prompt 17 |
| 17 | `reconciliation-backup-recovery-and-cleanup` | Jobs/Functions + Catalyst/AWS ops APIs | schedule/gate/drill | SCAFFOLDED |
| 18 | `embeddings-and-similarity-index-refresh` | Jobs + AWS Batch/AppSail + vector store | approved source/model change | SCAFFOLDED |

**Committed artifacts backing this inventory (Part B, §3.2):** §1 → `pipelines/
catalyst-pipelines.yaml`; §2 → `ds-import/` (106 configs + importer); §3/§4/§6/§7/§11/§12 →
the event functions `evidence_event`/`datastore_event`/`prediction_event`/`report_event`/
`notify_dispatch` + `jobs/signals-rules.json`; §9/§17/§18 → `cron_forecast`/`cron_reconcile` +
`jobs/cron-schedules.json` (disabled); all model dispatch → `app/predict/{adapter,envelope,
routing}.py` (pre-existing) behind the signed boundary `app/gateway_context.py`.

**Phase-order rule honored:** workflows 13–16 are created only as disabled scaffolds with
reserved Data Store/Stratus/NoSQL namespaces (`ds-import/reserved-namespaces.json`) and typed
adapter contracts, plus **RESERVED disabled** entries in `jobs/cron-schedules.json` and
`jobs/signals-rules.json`. No schedule or event subscription for 13–16 is enabled, so they incur
no charge. They are NOT claimed as functional.

---

## 5. Part C — React → Catalyst hosting (IMPLEMENTED, verified; cloud deploy HELD)

Full detail + verification evidence: **`PHASE_14_PARTC_REPORT.md`**. Summary:

- **Single public API base URL.** All `VITE_*` reads are centralised in
  `web/src/config/runtime.ts`. `web/.env.production` points the deployed build at the Catalyst
  **API Gateway** origin + `/api` (route → `gateway_api` → signed context → AppSail); dev uses
  `http://localhost:8000`. No secret / `DATABASE_URL` / AWS URL is placed in any `VITE_*` var or
  the bundle — enforced by `web/scripts/check-bundle-secrets.mjs` (runs on build; verified clean).
- **Catalyst Authentication (new).** `web/src/auth/` integrates the embedded Web SDK
  (`signIn`/`isUserAuthenticated`/`signOut`/`generateAuthToken`, v4.6.1+). `<RequireAuth>` gates
  every app route; `/` stays public. Cross-domain (Slate `*.onslate.in` → gateway
  `*.catalystserverless.in`) uses an **absolute** base URL + `credentials:'include'` + a raw
  `Authorization` token. An **offline** mode (synthetic demo identity) keeps `web` runnable in dev.
  The client never supplies a trusted role — `gateway_api` derives it server-side (§8.2); `X-Role`
  is a stripped display/audit hint. RLS being disabled does not remove this app-auth requirement.
- **SPA fallback / caching / CORS / badge.** `web/public/_redirects` + regenerated
  `dist/.catalyst/slate-config.toml` (`/* → /index.html 200`, `/app/* → /`); content-hashed assets
  + Slate CDN for caching (no `_headers` mechanism on Slate); exact Slate origin whitelisted in
  Console → Authorized Domains (CORS on); `VITE_DEMO_BADGE` "Synthetic Hackathon Demo" on the login
  gate + shell.
- **Hosting choice:** Slate preferred (needs one-time console *Start Exploring*); Web Client
  Hosting is the fallback. CLI path in §11.
- **Verified (local):** `npm run build` (tsc + vite) clean, 41/41 unit tests pass, bundle secret
  scan passes (only the expected unconfigured-URL placeholder warning).
- **HELD (cloud):** `catalyst apig:enable` (API Gateway currently DISABLED), `catalyst deploy
  slate` (dev), smoke test, then production promotion. Exact commands in §11 / the companion report.

---

## 6. Part D — FastAPI → AppSail (DONE where possible; build BLOCKED on Docker)

**DONE**
- `/health/live` (dependency-free liveness) and `/health/ready` (readiness; RDS is advisory
  only, never hard-required) added to `services/ml/app/main.py` and lint-clean.
- `services/ml/Dockerfile.appsail`: linux/amd64, non-root (`uid 10001`), binds Uvicorn to
  `0.0.0.0` on **`${X_ZOHO_CATALYST_LISTEN_PORT:-${APP_PORT:-9000}}`** (fixed this session — the
  container must honour the port Catalyst injects and be listening within 10s; `EXPOSE` is
  Docker-doc only), liveness healthcheck, **excludes** torch/CUDA/TabFM/TabPFN/TimesFM/
  torch-geometric/sentence-transformers.
- `infra/catalyst/appsail/appsail.deploy.json` — reviewed deploy descriptor (name `drishti-api`,
  `docker://drishti-api:appsail`, port 9000, mem 512, instances 1–2, `catalyst_auth=false`,
  env-key contract). Custom OCI runtimes do **not** use `app-config.json`.
- `services/ml/requirements.appsail.txt`: lightweight API dependency set (+ `zcatalyst-sdk`,
  `boto3` for server-side AWS adapter calls). Heavy GPU/foundation packages intentionally absent.

**BLOCKED / pending**
- `docker buildx build --platform linux/amd64 -f services/ml/Dockerfile.appsail ...` — **Docker
  absent**. Once Docker is available (locally or in CI), build → `catalyst deploy appsail
  --name drishti-api --source docker://drishti-api:appsail --port 9000`.
- Server-only env/secrets (Catalyst component IDs, Stratus bucket, Connections ID, feature
  flags, AWS adapter URL) go through AppSail configuration — **never** `DATABASE_URL` for the
  operational CRUD path, and never echoed/committed.
- Conservative memory/disk/min-max instances + scale-to-low for credit control (§9).
- Direct public AppSail CRUD is rejected; only the authenticated Function facade invokes it
  (§8.2). CORS is not used as service authentication.

---

## 7. Part E — Data Store / Stratus / NoSQL / Cache (SCAFFOLDED)

### 7.1 Versioned PG → Data Store mapping
A versioned mapping covers every submitted domain (organisation/geography, case lifecycle,
canonical identity, evidence, structured domains, governance, analytics contract). Every
imported table gets a stable `ExternalID` unique key; imports are idempotent (upsert by
`ExternalID`). Referential IDs, synthetic-data labels, timestamps and lineage are preserved.
No credentials or real PII are imported. Investigation-Board / Disaster-Response tables are NOT
created here — only reserved `ExternalID`/namespace/adapter contracts (phase-order rule).

### 7.2 Repository
`CatalystDataStoreRepository` is the deployed default (Catalyst SDK). The PostgreSQL repository
is retained only as an offline migration / read-only analytics adapter. No deployed operational
endpoint requires direct RDS access. Narrow repository interfaces allow in-memory fakes in tests.

### 7.3 Curated serving subset
Target: ~1,000–5,000 linked cases (golden cases + varied synthetic records exercising search,
dashboards, predictions, board, disaster). **Development imports are capped at 5,000 records per
table** (current Data Store dev limit); the subset is designed around this. Import uses the real
**`catalyst ds:import <csv> --config <cfg>`** CLI (`operation:upsert`, `find_by:ExternalID` =
idempotent upsert by ExternalID), driven by the 106 generated `ds-import/configs/*.import.json`;
`import_serving_subset.py` (SDK `bulk_upsert`) is the offline/CI equivalent. Row counts, rejected
rows, relationship checks and content hashes are captured at import time.

### 7.4 Stratus / NoSQL / Cache responsibilities
- **Stratus** (system of record for objects): private buckets/prefixes for evidence, import
  staging, reports, board/disaster exports; versioning + short-expiry exact-object signed access;
  SHA-256/size/MIME/object-key/version/lineage in Data Store; new evidence quarantined until
  size/type/hash + isolated malware scan pass (security control only — **no OCR/extraction**).
- **NoSQL:** saved board layouts, UI prefs, presence, flexible feed envelopes only — never a
  duplicate of authoritative relational records.
- **Cache:** bounded-TTL reference lookups, idempotency keys, rate-limit counters, short-lived
  summaries only — never system of record.
- **S3 → Stratus** copy of the Prompt-5 evidence fixtures with hash verification is pending
  (Stratus provisioning). S3 remains only for temporary SageMaker/AWS Batch staging copies.

### 7.5 Bootstrap / cutover contract (one-way analytics boundary)
Before cutover: copy selected AWS rows/objects into Data Store/Stratus. After cutover: new input
is written to Data Store/Stratus first; only validated/versioned feature snapshots or analytics
projections (keyed by ExternalID + source version) go to AWS; AWS returns results through the
adapter as new result records (never edits to source input). Scheduled count/hash/version
reconciliation + repeatable rebuild of the serving subset. **No uncontrolled two-way
replication and no last-write-wins.**

---

## 8. Parts F+G — Secure Catalyst→AWS adapter + ML placement/runtime (IMPLEMENTED; AWS/GPU deploy HELD)

### 8.1 Public boundary
No browser component calls AWS or AppSail CRUD directly. API Gateway + authenticated/throttled
Function facade is the public HTTP API boundary; the facade invokes AppSail and protected AWS
services server-side. A direct AppSail WebSocket/SSE channel is allowed only with a short-lived,
audience/board/user-bound token minted via the authenticated Gateway path + strict Origin checks.

### 8.2 Signed internal context
The Gateway Function derives identity/role from Catalyst Authentication, strips client-supplied
identity headers, and sends AppSail a short-lived signed context `{user_id, scope, ts, nonce,
request_id}`. AppSail verifies signature/audience/expiry/replay before handling a request.

### 8.3 AWS adapter
Minimal protected adapter inside the AWS VPC for capabilities Catalyst does not replace:
`Catalyst → HTTPS AWS API Gateway → Lambda/ECS adapter → SageMaker/Batch (+ PostGIS/pgRouting
only where needed)`. RDS stays private (no `0.0.0.0/0` on 5432; never a browser/AppSail CRUD
path). Least-privilege execution roles, TLS, timeouts, circuit-breaking, retry-with-jitter,
idempotency, redacted audit logs. Connections used for OAuth/OIDC where compatible; otherwise
short-lived signed service requests with timestamp/nonce replay protection (an API key alone is
not authentication).

### 8.4 Region availability (verified 2026-07-18)
- **Circuits — Unavailable in IN DC.** Current docs: not available in EU/AU/IN/JP/SA/CA
  ([Catalyst Circuits SDK docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/serverless/circuits/get-a-component-instance/)).
  → branch/parallel orchestration uses idempotent Functions + Job Scheduling.
- **Zia AutoML — Unavailable in IN DC.** Current docs: not available in EU/AU/IN/JP/SA/CA
  ([Catalyst AutoML SDK docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl)).
  → automated tabular training uses a QuickML eligible baseline + the justified AWS TabFM path.
- **QuickML** (RAG + no-code baseline) is preferred for RAG and is used where enabled.
- Content rephrased for compliance with source licensing.

### 8.5 Input-to-model routing matrix (G.1) — enforced contract
Model routing is NOT "every input → every model". It is gated by approved task,
FeatureSchemaVersion, subject type, observation cutoff and data-quality state.

| Input/event | Trigger/canonicalization | Model route | Required behavior |
|---|---|---|---|
| FIR draft create/autosave/edit | draft only | **None** | validate + save; **no** PredictionRequest, **no** AWS call |
| FIR submitted for review | submitted, not canonical | **None** | review/audit state only |
| Supervisor-approved FIR (verified head/time/unit/geometry) | new canonical CaseVersion/CaseEvent | near-repeat (eligible) + coalesced workload/area-forecast | **never** score complainant/accused/victim/FIR; mark only aggregate snapshots stale |
| Approved correction/reclassification/transfer | new immutable version | rebuild only schemas whose source fields changed | supersede prior snapshots; no dup for same idempotency key |
| Approved chargesheet/court/lab/statement/property/lifecycle | structured reviewed record | workload/backlog features, graph/similarity refresh, or future labelled-outcome dataset | outcome becomes a label only after label-window closure + approval |
| Digital evidence upload → Stratus | quarantined object + manual metadata | **None from bytes** | hash/type/size/malware only; no OCR/extraction/prediction |
| Reviewed manual evidence metadata | versioned canonical metadata | only a schema explicitly listing those fields; else graph/index refresh | raw content excluded |
| CSV/JSON FIR import | per-row staging/validation/dedup/review | same canonical events as approved forms | reject/hold bad rows; coalesce accepted rows into bounded jobs |
| CDR/device/media/financial import | staged rows + reviewed links | graph/community/similarity; prediction only if an approved non-person aggregate schema permits | unreviewed link ≠ evidence, ≠ feature |
| Weather/holiday/event/area context | approved SourceVersion (freshness/units/geo/cutoff) | TimesFM/ST-GNN/fused aggregate only | reject stale/post-cutoff; preserve provenance |
| Approved SOP/policy text | curated KB release | QuickML RAG | exclude narratives/evidence/unreviewed intel |
| Hazard/readiness/resource inputs (Prompt 17) | validated hazard/resource snapshot | hazard forecast + reviewed allocation/routing | separate task/schema/model; **never** auto-dispatch/auto-warn |

For an approved FIR: persist canonical record first; publish the source-change Signal **only
after** the transaction commits; the handler determines affected aggregate subjects, supersedes
only their prior snapshots, and creates requests with the idempotency key convention above.

### 8.6 AWS GPU implementation status (G.3) — HONEST pre-change facts + gaps
Verified pre-change facts in the current repo:
- `WorkloadRunRequest.foundation_kind` defaults to `"tabpfn"` (`app/workload/schemas.py`).
- `/workload/run` executes `service.run_governed(...)` **in-process** (`app/workload/router.py`).
- `TabFMCandidate` uses `_load_tabfm_model(bfloat16)` and does **not** explicitly place the
  model/tensors on CUDA (`app/workload/models_iface.py`, `app/risk/models_iface.py`).
- No SageMaker/AWS Batch adapter exists yet (must not be inferred from roadmap text).

Therefore the current TabFM path is treated as **local/interim** and is NOT claimed as a real
AWS GPU deployment. Planned (SCAFFOLDED contract; execution BLOCKED on Docker+GPU+AWS):
`services/gpu-worker` separate image; pinned Python/CUDA/PyTorch/TabFM/TimesFM + weight digest +
license check (non-commercial/non-production license honored, no undocumented prod promotion);
immutable ECR digest + encrypted S3 artifacts + execution role; SageMaker-compatible
health/invocation handlers with a versioned request schema carrying only ids/versions/hashes/
cutoff/columns/context/query-rows (never full FIR JSON/narrative/evidence bytes/DB secrets);
signed/versioned result envelope reporting `actual_backend`, `actual_device`, artifact/schema
digests, metrics; **fail-closed** if CUDA or real weights are unavailable (no TabPFN/in-context
output mislabelled as TabFM).

---

### 8.7 Part G — ML/RAG placement + prediction runtime (IMPLEMENTED; cloud HELD)

Full detail + verification: **`PHASE_14_PARTG_REPORT.md`**. Part G wires the
pre-existing pieces (envelope, G.1 routing, signed adapter + breaker, QuickML
contract, `gpu-worker`, scoped SSE channel) into a governed prediction runtime and
adds the Part-G-specific layers. New under `services/ml/app/predict/`:

- **`placement.py`** (+ `infra/catalyst/ml-placement.json`) — the source of truth for
  WHERE each model/assistant runs: QuickML RAG + the eligible **no-code baseline** on
  Catalyst (item 1); TabFM/TimesFM/ST-GNN external **AWS GPU** (item 2); near-repeat/
  KDE/fusion/baselines on **Catalyst CPU**; **Zia AutoML recorded UNAVAILABLE in the IN
  DC with doc evidence** + fallback (never faked). Cross-checks `capability_gaps.py`.
- **`dispatch_policy.py`** (item 3, scoped by G.3) — the hackathon keeps **one** AWS
  GPU mechanism: **SageMaker asynchronous inference** (scale-to-zero). The multi-mode
  selection (AWS Batch / Batch Transform / real-time) is **retained + tested but
  DEFERRED** (`DRISHTI_DISPATCH_MULTIMODE_ENABLED`); the **GPU-never-Serverless** guard
  always applies.
- **`validation.py`** — **fail-closed** result validation (id/task binding, completed
  state, **backend authenticity — TabFM must be `tabfm` on `cuda`**, digest + shape).
- **`lineage.py`** (item 5) — FeatureSnapshot / PredictionRequest / PredictionResult
  Data Store rows keyed by stable ExternalID, results written back as **NEW** records
  tagged `authoritative_store=catalyst_data_store` (AWS never authoritative).
- **`runtime.py`** — the orchestrator: routing gate → persist to Data Store → select
  dispatch mode → protected AWS adapter → validate → persist result → **data-minimized**
  Signal notice (bridged to the Part F scoped SSE channel; else Gateway polling).
- **`comparison.py`** (item 4) — QuickML/no-code baseline **vs** the custom AWS model on
  the **same split** (hash-checked) with the **leakage-safe** guardrail.
- **`enablement.py`** (G.1/G.2 demo scoping) — the reduced routing matrix + reduced
  model set: **ENABLED** = TabFM workload, TimesFM, near-repeat/graph, CPU baselines;
  **DEFERRED** = area-forecast TabFM, ST-GNN, fusion, KDE, multi-embedding; **OPTIONAL**
  = QuickML RAG/no-code; court/lab + CDR/financial routes documented-but-disabled.
  `routing.py` filters to enabled tasks (Approved FIR drops area-forecast TabFM; context
  keeps only TimesFM), `placement.py` records each engine's enablement, and
  `runtime.submit` refuses a deferred task. Env-flippable per task/route.
- **`router.py`** (registered in `main.py`) — open aggregate introspection
  (`/predict/placement|capability-gaps|routing|dispatch-policy|enablement|health`) + the
  role- + write-guarded `POST /predict/jobs` and `GET /predict/jobs/{id}`.

**Governance (G.4):** a new FIR is inference-only (never retrains TabFM; training +
inference are separate paths); a correction creates a new version and marks the prior
result **stale (preserved, not deleted)** + permits a controlled rerun; duplicate events
do not create duplicate GPU jobs (idempotency); every request/result row carries model /
version / status / stale for the UI.

**Six Part G tests (G.5):** `services/ml/tests/test_predict_runtime.py` — (1) draft → no
prediction, (2) approved FIR → one idempotent request, (3) real TabFM CUDA success
(skipped unless the real GPU plane is configured), (4) TabFM failure not labelled success,
(5) evidence upload → no model, (6) correction marks prior stale + controlled rerun →
**5 passed, 1 skipped**.

**Verified offline:** the six tests above + throwaway harness checks (placement parity, Zia
unavailable-with-evidence, single-mechanism dispatch + GPU-never-serverless, result validation
incl. **mislabelled-TabFM rejected**, full runtime round-trip, **TabFM fail-closed**,
routing-gate refusals, enablement filtering, comparison same-split/leakage gates); a TestClient
`POST /predict/jobs → dispatched(sagemaker_async) → GET → completed` round-trip; `get_diagnostics`
clean; `pytest --collect-only` = **333 tests**, no import errors.

**HELD (cloud):** ECR GPU-worker push + weight staging, SageMaker async / AWS Batch
endpoints, `DRISHTI_USE_CATALYST_DATASTORE=true` + adapter env on AppSail, QuickML enable
+ no-code baseline run, and a real-time endpoint (only after a benchmark). Ordered steps in
`PHASE_14_PARTG_REPORT.md` §8.

### 8.8 Parts H + I — minimal event processing + simplified CI/CD (scoping)

**Part H — minimal event processing.** The event plane is deliberately small.
`infra/catalyst/jobs/*.json` now tag each rule/cron with a `tier`:

- **`tier: "minimal"`** (the only two things active for the hackathon): ONE
  `prediction.requested` Signal/Event Function (`prediction-requested` →
  `prediction_event`) and ONE scheduled aggregate forecast job
  (`drishti-forecast-daily` → `cron_forecast`).
- **Kept even so:** retry + failed-job state (auto exponential backoff, max 20; a
  failed `prediction_event` sets `PredictionRequest.Status='failed'`) and the
  **persist-authoritative-record-before-emit** invariant.
- **`tier: "optional"` / deferred (documented, inactive):** Circuits (also IN-DC
  unavailable), a separate event per upload/import/report action, the result-ready
  and canonical-version events, **Mail/Push (→ Prompt 15)**, and multiple crons /
  backfill pipelines. All `active/enabled=false` so they cost nothing until enabled.

**Part I — simplified Catalyst Pipelines.** `catalyst-pipelines.yaml` is reduced to
the sufficient hackathon flow: **install deps → lint/test → build frontend + API →
scan for secrets → deploy to Catalyst development → health/auth/prediction smoke →
retain the previous deploy for rollback** (`smoke_test.py` now also asserts
`/predict/health` + `/predict/enablement`). Deferred (documented, out of the
pipeline): full SBOM/licence automation, production artifact-promotion gates,
**GPU image rebuild in the pipeline**, Data Store export + forward-recovery
simulation, deployment concurrency locks, and deliberately-failed-deploy recovery
testing. The **GPU worker deploys separately** via `infra/aws/gpu-worker/`
(`deploy_gpu_worker.py` — offline `--plan` validated; `--commit` HELD) using AWS
CLI/SageMaker, referenced by **immutable image (`@sha256`) + model versions**.

Verified: all `jobs/` + `billing/` + `gpu-worker/` JSON parse; the pipeline YAML
parses to 5 stages (validate/build/scan/deploy_dev/smoke); `deploy_gpu_worker.py`
`--plan`/`--teardown` exit 0 and `--commit` without confirmation exits 2 (held);
`smoke_test.py` diagnostics clean.

## 9. Part J — Cost / credit controls

- Recorded IDs (no secrets): project `48361000000030003`, org `60075362708`, env Development,
  dev domain `dhristi-60075362708.development`.
- **Plan baseline (from the user's console screenshot):** period 17 Jul – 17 Aug 2026,
  INR 1,500 Basic + INR 300 Free = INR 1,800 usable. **Verification is console-only** — the
  CLI (v1.27.0) exposes no billing/usage command (`catalyst help` lists none). The full balance
  is not assumed to remain available.
- **Kept basic cost safety (Part J), in `infra/catalyst/billing/budget.json`:** confirm the
  Catalyst credit balance before/after enabling any paid capability; **avoid duplicate** AppSail
  apps / Signals rules / crons (exactly one `drishti-api`, one `prediction-requested`, one
  `drishti-forecast-daily`, one `drishti-gpu-async`); conservative sizing (AppSail 1–2 instances,
  SageMaker async **scale-to-zero**, dev imports capped at 5000 rows/table); an **AWS budget
  alarm** (AWS Budgets + CloudWatch); **stop GPU after testing** (`deploy_gpu_worker.py
  --teardown` → delete the async endpoint); and a cleanup checklist.
- **The 50/75/90% Catalyst alert automation is OPTIONAL** (`optional:true` in `budget.json`): the
  CLI (v1.27.0) exposes no billing/usage command, so it is applied in Console → Budget only if
  straightforward; otherwise rely on confirming the balance manually + the AWS alarm. The intended
  thresholds (INR 900/1350/1620) are recorded.
- A post-hackathon cleanup/export runbook (preserves required Data Store/Stratus data + retained
  AWS model artifacts; deletes temporary resources) is tracked in `budget.json` `cleanup` + §11.

---

## 10. Part K — Verification status

Part K is **reduced to the actual demo** (11 required checks). The authoritative
list is `infra/catalyst/verification/acceptance-checklist.json`; the one-command
runner is `infra/catalyst/verification/acceptance_check.py` (offline now: **2 PASS,
0 FAIL, 7 HELD, 2 MANUAL** — full acceptance runs post-deploy with `--base-url`/`--web-url`).

| # | Proves | Status | Evidence |
|---|---|---|---|
| K1 | Frontend deployed through Catalyst | **HELD** (deploy) | `web/dist`, `client/slate-config.toml`, pipeline `deploy_dev` |
| K2 | Auth + API Gateway work | **HELD** (deploy) | `gateway_context.py`; `smoke_test.py` unsigned=401/signed=200 |
| K3 | AppSail backend works | **HELD** (deploy) | `/health/live` + `/health/ready` |
| K4 | Data Store serves operational data | **HELD** (deploy + `ds:import`) | `ds-import/` (106 configs); `datastore/repository.py` |
| K5 | Stratus stores one evidence file | **MANUAL** (post-deploy) | `stratus/`; workflow §4 (no OCR) |
| K6 | Approved FIR reaches TabFM on AWS GPU | **HELD** (GPU) | `test_predict_runtime.py::test_real_tabfm_cuda_prediction_succeeds` (skipif); `runtime`+`validation`+`gpu-worker` |
| K7 | Prediction returns to Catalyst + appears in UI | **HELD** (deploy) | `runtime.py`+`lineage.py` (result→Data Store); `stream/` |
| K8 | Drafts + evidence do NOT invoke the model | **VERIFIED (offline)** | `test_predict_runtime.py` (draft + evidence tests) pass; live re-check via `/predict/routing` |
| K9 | One Signal + one scheduled job | **VERIFIED (offline)** | `jobs/*.json` `tier:minimal` (harness PASS) |
| K10 | No secrets in the browser | **VERIFIED (offline)** | `check_no_db_url_in_web.py` (harness PASS) + `check-bundle-secrets.mjs` |
| K11 | AWS GPU resources are stopped | **MANUAL/ops** | `deploy_gpu_worker.py --teardown`; `budget.json` cleanup |

**Test only when the feature is enabled (NOT in the minimum set):** NoSQL, Cache,
Mail, Push, SmartBrowz, QuickML, Circuits — each tested when its
`DRISHTI_*_ENABLED` flag / region availability makes it live (see the checklist
`test_only_when_enabled`).

**Supporting evidence already captured (Part B, §3.2):** all committed JSON valid; 8
Functions pass `node --check`; `app.main` imports with `/internal/ping`; Node→Python
signed-context interop 4/4; ds-import = 106 configs + idempotent importer; regression
`pytest --collect-only` = **333 tests** (incl. the six Part G tests), no import errors.
Circuits + AutoML IN-DC unavailability recorded against current docs.

---

## 11. Remaining platform actions (runbook)

Ordered, with the exact blocking dependency for each:

1. **Install Docker** (or use a CI runner / Catalyst Pipelines runner with Docker) — unblocks image builds (2–8). Catalyst Pipelines runners have Docker, so `catalyst-pipelines.yaml` `build_appsail_image` can build the OCI image without a local Docker.
2. `docker buildx build --platform linux/amd64 -f services/ml/Dockerfile.appsail -t drishti-api:appsail --load services/ml` (or let the pipeline do it).
3. Functions + `client` + `catalyst.json` are already **committed** in `infra/catalyst/`. Run `catalyst functions:add`/`client:setup` only to (re)install `node_modules`, then `catalyst deploy --only functions,client`.
4. `catalyst apig:enable` — API Gateway in front of Functions; apply `api-gateway/routes.json` in the console, then `catalyst pull` for the canonical `catalyst-user-rules.json`.
5. `catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000` (dev). **Credit-spending.**
6. `catalyst slate:create --framework react-vite` + `catalyst deploy slate` (or Web Client deploy) for the React build (dev). **Credit-spending.**
7. Create Stratus buckets, then import the curated subset with the CLI: `catalyst ds:import serving-export/<T>.csv --config infra/catalyst/ds-import/configs/<T>.import.json` (upsert by ExternalID; poll `catalyst ds:status import <job_id>`). Offline/CI equivalent: `DRISHTI_USE_CATALYST_DATASTORE=true python infra/catalyst/ds-import/import_serving_subset.py --source-table <T> --export serving-export/<T>.export.jsonl --commit`. **Credit-spending.**
8. Configure Signals rules (`jobs/signals-rules.json`) + crons (`jobs/cron-schedules.json`) in the console and set the matching `DRISHTI_*_ENABLED` AppSail env flags to enable each workflow.
9. AWS: ECR repo + GPU-worker image + SageMaker/Batch (async/Batch) + SQS/DLQ + IAM roles + API Gateway adapter. **AWS cost.**
10. Smoke tests (`pipelines/smoke_test.py`, §10) → then production promotion of the exact tested immutable digests (may require a console/payment approval — keep the working dev deployment if so).

> Steps 5–9 spend real credits/money and several are hard to reverse. They are intentionally
> held for an explicit go-ahead rather than run silently.

---

## 12. Sources
- Catalyst Circuits regional availability — https://docs.catalyst.zoho.com/en/sdk/python/v1/serverless/circuits/get-a-component-instance/
- Catalyst Zia AutoML regional availability — https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl
- Catalyst multi-DC base URIs (IN: api.catalyst.zoho.in / accounts.zoho.in) — https://www.zoho.com/catalyst/help/api/introduction/multi-dc.html

(External documentation content was rephrased/summarized for compliance with source licensing.)


---

## Prompt 23 live-evidence addendum (2026-07-23) — additive, historical text unchanged

The Phase 14 Catalyst spine is now **deployed and proven live** on DHRISTI
`48361000000030003` (IN DC, Development). See `docs/phase-reports/PHASE_23_REPORT.md`
and `artifacts/phase-23/`.

- **AppSail `drishti-api`** live at `https://drishti-api-50044118953.development.catalystappsail.in`
  — `/health/live`=200, `/health/ready`=200 (config/operational_datastore/gateway_auth/
  object_store/analytics_db all ok). Signed gateway-context boundary enforced
  (`security-probe.log` 11/11: direct bypass→401, forgeries/expiry/replay→401).
- **9 Functions** deployed live (`gateway_api`, `channel_token`, 5 event, 2 cron).
- **Signal (matrix rows 21/22)** proven end-to-end: `prediction-requested` Data Store
  Row-Insert → `prediction_event` → AppSail `/internal/predictions/dispatch` →
  `PredictionRequest sigtest-f7e3135a02` advanced **`approved → queued`** (~2 s);
  **retry** (Signals attempts #1..#6) and **idempotency** (same key deduped) proven
  (`signal-proof.log`, `idempotency-proof.log`). Runtime note: Catalyst Event payload is
  read via the **`event.data` property** on this node20 runtime (`getData()` returns
  undefined); rule uses All Events with the authoritative `state==approved` check in the
  function.
- **Cron (matrix row 20)** proven: `drishti_forecast` (daily 00:10 IST) → `cron_forecast`
  → created `forecast-2026-07-22` queued (execution `48361000000061010`).
- **Data Store** operational CRUD proven live via `PredictionRequest` (`48361000000043006`).
- **Application rollback** + additive forward recovery proven (`rollback-proof.log`).
- **AWS custom-model dispatch** remains the Prompt 24 plane; here dispatch records
  `skipped_disabled → queued` idempotently (AppSail `DRISHTI_PREDICTION_DISPATCH_ENABLED`
  off by design until Prompt 24).
