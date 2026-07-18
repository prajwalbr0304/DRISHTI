# PHASE 14 — Catalyst-native deployment + external AWS custom-model integration

Status date: 2026-07-18
Owner: implementation agent (Kiro)
Catalyst project: **DHRISTI** (ID `48361000000030003`), India (IN) DC, Development environment.

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
| A.8/J | Plan-baseline (INR 1500 + 300) verification | **BLOCKED** — no CLI billing API; console-only (see §9) |
| B | Component allocation + 26-row compliance matrix | **DONE** (this document) |
| C | React → Slate / Web Client Hosting | **SCAFFOLDED** — config work + deploy runbook; deploy pending (§5) |
| D | FastAPI → AppSail (lightweight OCI, health, non-root) | **SCAFFOLDED** — `Dockerfile.appsail` + health endpoints DONE; image build/deploy **BLOCKED on Docker** (§6) |
| E | Data Store / Stratus / NoSQL / Cache mapping + migration | **SCAFFOLDED** — mapping + repository contract; import pending (§7) |
| F+G | Secure Catalyst→AWS adapter + typed model contracts | **SCAFFOLDED** — contracts; AWS provisioning + GPU run **BLOCKED** (§8) |
| H | Job Scheduling / Signals / Circuits check | Circuits + AutoML **UNAVAILABLE in IN DC** (verified, §8.4); Functions+Jobs fallback SCAFFOLDED |
| I | Pipelines CI/CD | **SCAFFOLDED** — pipeline config + deploy scripts |
| K | Verification | Partial — see §10 (what is verifiable now vs pending) |

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
3. **Credit-spending cloud deploys** (`catalyst deploy`, `ds:import`, AppSail/Slate creation,
   AWS SageMaker/Batch/ECR) are held pending explicit go-ahead because the hackathon budget is
   finite (INR ~1800) and several steps are hard to reverse. See §9 and §11.
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

Disposition legend: **Used(D)** deployed+tested · **Used(S)** scaffolded, deploy pending ·
**Not used** capability genuinely absent from scope · **Unavailable** region/platform gate with evidence.

| # | Capability | Required Catalyst service | DRISHTI disposition |
|---:|---|---|---|
| 1 | Serverless backend logic | Functions | **Used(S)** — Gateway facade + event/notification Functions scaffolded in `infra/catalyst/functions/`; deploy pending Docker-free CLI step |
| 2 | Docker image deployment | AppSail custom OCI | **Used(S)** — `services/ml/Dockerfile.appsail` (linux/amd64, non-root, port 9000). Build **BLOCKED on Docker**; deploy cmd in §11 |
| 3 | Full managed web application | AppSail | **Used(S)** — FastAPI is the AppSail runtime; readiness endpoints DONE |
| 4 | React/Vite frontend | Slate or Web Client Hosting | **Used(S)** — Slate preferred; single API base URL + auth config prepared; deploy pending |
| 5 | Custom domain + SSL | Domain Mappings | **Not used (yet)** — no domain supplied for the hackathon; generated Catalyst URLs used. Recorded as capability-absent-input, not a platform gap |
| 6 | Operational relational data | Data Store | **Used(S)** — full PG→Data Store mapping + `CatalystDataStoreRepository` contract; curated import pending |
| 7 | Semi-structured data | NoSQL | **Used(S)** — reserved for board layouts / UI prefs / presence only (§7.4) |
| 8 | Application object/blob storage | Stratus | **Used(S)** — evidence/import/report buckets designed; S3→Stratus copy pending |
| 9 | Cache | Cache | **Used(S)** — bounded-TTL idempotency/rate-limit/lookup only |
| 10 | Full-text application search | Data Store | **Used(S)** — case/FIR/person/evidence metadata search via Data Store search; no external search engine |
| 11 | Text LLM/RAG/knowledge base | QuickML | **Used(S)** — approved-SOP RAG path scaffolded; enable in a later phase |
| 12 | No-code ML pipeline | QuickML | **Used(S)** — eligible baseline experiment planned as the QuickML no-code path |
| 13 | Automated tabular training | Zia AutoML | **Unavailable** — AutoML not offered in IN/EU/AU/JP/SA/CA DCs ([docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl)). Fallback: QuickML baseline + justified AWS TabFM |
| 14 | OCR/face/image/object/barcode/ID | Zia Services | **Not used** — input is digital/manual; extraction deferred (out of hackathon scope) |
| 15 | Speech/voice/translation | Zia Services | **Not used** — voice/transcription deferred |
| 16 | PDF/image/screenshot/headless | SmartBrowz | **Used(S)** — report/board/disaster export generation scaffolded |
| 17 | Login/signup/session identity | Authentication | **Used(S)** — Catalyst Auth wired into React + Gateway facade identity derivation |
| 18 | API routing/auth/throttling | API Gateway | **Used(S)** — Gateway in front of Functions; protected Function facade invokes AppSail (AppSail is not a documented native Gateway target) |
| 19 | OAuth token lifecycle | Connections | **Used(S)** if the AWS adapter exposes OAuth/OIDC; else the signed-service-auth gap is recorded (§8.3) |
| 20 | Scheduled jobs/cron | Job Scheduling | **Used(S)** — forecast/health/cleanup/export crons defined **disabled** until owning phases |
| 21 | Data/upload/auth event reactions | Signals + Event Functions | **Used(S)** — `evidence.uploaded`, `import.completed`, `prediction.requested`, `report.ready` |
| 22 | Cross-component event routing | Signals | **Used(S)** — same event bus |
| 23 | Branch/parallel workflow | Circuits | **Unavailable** — Circuits not offered in IN/EU/AU/JP/SA/CA DCs ([docs](https://docs.catalyst.zoho.com/en/sdk/python/v1/serverless/circuits/get-a-component-instance/)). Fallback: idempotent Functions + Job Scheduling |
| 24 | Transactional email | Mail | **Used(S)** — data-minimized synthetic notices; delivery metadata only |
| 25 | Web/mobile push | Push Notifications | **Used(S)** — data-minimized synthetic notices |
| 26 | CI/CD | Pipelines | **Used(S)** — lint/test/scan/build/deploy/smoke/rollback pipeline config |

No row is omitted. Rows 13 and 23 are **Unavailable** with current documentation evidence
(re-verified 2026-07-18); rows 5, 14, 15 are **Not used** for scope/input reasons.

---

## 4. Workflow inventory (owners, triggers, idempotency, DLQ)

Catalyst Pipelines owns CI/CD only. Data/event workflows use Functions, AppSail, Data Store,
Stratus, Signals/Event Functions and Job Scheduling. QuickML owns eligible no-code ML/RAG.
AWS Batch/SageMaker owns justified custom model computation. **Circuits is not used (IN DC
gate); idempotent Functions + Job Scheduling replace branch/parallel orchestration.**

Idempotency key convention (all model-producing workflows):
`<task>:<subject>:<cutoff>:<feature-schema-version>:<model-version>:<source-version-hash>`.

| # | Workflow | Owner | Trigger | State |
|---:|---|---|---|---|
| 1 | `catalyst-ci-cd` | Pipelines | repo change / manual release | SCAFFOLDED |
| 2 | `bootstrap-catalyst-serving-data` | CLI + ds:import + Stratus | initial deploy / rebuild | SCAFFOLDED (import pending) |
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

**Phase-order rule honored:** workflows 13–16 are created only as disabled scaffolds with
reserved Data Store/Stratus/NoSQL namespaces and typed adapter contracts. No schedule or event
subscription for 13–16 is enabled, so they incur no charge. They are NOT claimed as functional.

---

## 5. Part C — React → Catalyst hosting (SCAFFOLDED)

- The Vite build reads the API base at runtime from `import.meta.env.VITE_API_BASE_URL`
  (`web/src/api/client.ts`), so a single public API base URL can point at the Catalyst API
  Gateway. No secret and no `DATABASE_URL` / AWS URL is placed in any `VITE_*` variable or the
  browser bundle (verified: `web/.env.example` carries only the API base + map style).
- **Hosting choice:** Slate preferred (React build + deploy previews). If the credited project
  lacks Slate, Web Client Hosting is the fallback. CLI path in §11.
- SPA deep-link fallback, asset caching, exact CORS origin and the "Synthetic Hackathon Demo"
  badge are part of the hosting config task.
- Catalyst Authentication integration maps the authenticated user → existing synthetic demo
  role. The client never supplies its own trusted role; the Gateway facade derives role
  server-side (§8.2). Disabling PostgreSQL RLS does not remove this app-auth requirement.
- **Pending:** `catalyst deploy slate` (dev), smoke test, then production promotion.

---

## 6. Part D — FastAPI → AppSail (DONE where possible; build BLOCKED on Docker)

**DONE**
- `/health/live` (dependency-free liveness) and `/health/ready` (readiness; RDS is advisory
  only, never hard-required) added to `services/ml/app/main.py` and lint-clean.
- `services/ml/Dockerfile.appsail`: linux/amd64, non-root (`uid 10001`), binds Uvicorn to
  `0.0.0.0:9000`, liveness healthcheck, **excludes** torch/CUDA/TabFM/TabPFN/TimesFM/
  torch-geometric/sentence-transformers.
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
table** (current Data Store dev limit); the subset is designed around this. Import via
`catalyst ds:import --table <t> --config <cfg>` (upsert). Job IDs, row counts, rejected rows,
relationship checks and source hashes are captured at import time.

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

## 8. Parts F+G — Secure Catalyst→AWS adapter + ML placement (SCAFFOLDED; AWS/GPU BLOCKED)

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

## 9. Part J — Cost / credit controls

- Recorded IDs (no secrets): project `48361000000030003`, org `60075362708`, env Development,
  dev domain `dhristi-60075362708.development`.
- **Plan baseline (from the user's console screenshot):** period 17 Jul – 17 Aug 2026,
  INR 1,500 Basic + INR 300 Free = INR 1,800 usable. **Verification is console-only** — the
  CLI (v1.27.0) exposes no billing/usage command (`catalyst help` lists none). The full balance
  is not assumed to remain available.
- Budget/alerts at ~50/75/90% to be configured in the console where supported.
- Conservative AppSail memory/disk/instances + scale-to-low; prevent duplicate dev deploys;
  keep only the curated linked serving subset; lifecycle temporary Stratus imports/reports.
- AWS: Budgets + CloudWatch alarms; temporary GPU endpoints/Batch jobs stopped after validation.
- A post-hackathon cleanup/export runbook (preserves required Data Store/Stratus data + retained
  AWS model artifacts; deletes temporary resources) is tracked in §11.

---

## 10. Part K — Verification status

**Verifiable now (DONE):**
- Project binding is active (`DHRISTI (active) (base)`), India DC, no tokens committed.
- FastAPI exposes `/health`, `/health/live`, `/health/ready` (lint-clean).
- AppSail image excludes the heavy GPU/foundation stack (requirements diff).
- No secret / DB URL / AWS URL in `VITE_*` (web/.env.example inspected).
- Circuits + AutoML IN-DC unavailability recorded against current docs.

**Pending (needs deploy/Docker/GPU/AWS/credit go-ahead):**
- Public frontend/API URLs resolving to Slate/Web-Client + API Gateway → Function → AppSail.
- AppSail health/SDK connectivity live; Data Store as operational record + full-text search.
- Stratus up/download/hash/version/short-lived access; one NoSQL + one Cache bounded use.
- One authenticated FIR read + one allowed write end-to-end.
- FeatureSnapshot → AWS Batch/SageMaker → PredictionResult round trip.
- Draft/save/submit + raw-evidence upload proving **no** model invocation.
- Real TabFM smoke test asserting `actual_backend=tabfm`, `device=cuda`, and fail-closed on
  missing CUDA/weights.
- Rollback + CI concurrency-lock + forward-recovery drills; production immutable-digest promotion.

---

## 11. Remaining platform actions (runbook)

Ordered, with the exact blocking dependency for each:

1. **Install Docker** (or use a CI runner with Docker) — unblocks image builds (2–8).
2. `docker buildx build --platform linux/amd64 -f services/ml/Dockerfile.appsail -t drishti-api:appsail --load services/ml`.
3. `catalyst functions:add` (Gateway facade + event functions) and `catalyst client:setup` (or `slate:create`/`slate:link`) — creates `catalyst.json`.
4. `catalyst apig:enable` — API Gateway in front of Functions.
5. `catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000` (dev). **Credit-spending.**
6. `catalyst deploy slate` (or Web Client deploy) for the React build (dev). **Credit-spending.**
7. Create Stratus buckets + `catalyst ds:import --table <t> --config <cfg>` for the curated subset. **Credit-spending.**
8. AWS: ECR repo + GPU-worker image + SageMaker/Batch (async/Batch) + SQS/DLQ + IAM roles + API Gateway adapter. **AWS cost.**
9. Smoke tests (§10) → then production promotion of the exact tested immutable digests (may require a console/payment approval — keep the working dev deployment if so).

> Steps 5–9 spend real credits/money and several are hard to reverse. They are intentionally
> held for an explicit go-ahead rather than run silently.

---

## 12. Sources
- Catalyst Circuits regional availability — https://docs.catalyst.zoho.com/en/sdk/python/v1/serverless/circuits/get-a-component-instance/
- Catalyst Zia AutoML regional availability — https://docs.catalyst.zoho.com/en/sdk/python/v1/zia-services/automl
- Catalyst multi-DC base URIs (IN: api.catalyst.zoho.in / accounts.zoho.in) — https://www.zoho.com/catalyst/help/api/introduction/multi-dc.html

(External documentation content was rephrased/summarized for compliance with source licensing.)
