# Phase 14 Part G — ML/RAG placement + prediction runtime

Companion to `PHASE_14_REPORT.md` §8. Status date: 2026-07-18.
Catalyst project: **DHRISTI** (`48361000000030003`), India (IN) DC, Development env.

> **Status legend:** **DONE** — executed + verified here (evidence inline) ·
> **IMPLEMENTED** — code/config written and locally verified (diagnostics /
> functional round-trip) · **HELD** — real artifact ready; the only remaining
> step is credit-spending or a Console/AWS-account action, deliberately not run.
>
> Part G **wires together** the pieces Parts B/D/E/F scaffolded — the versioned
> `envelope.py`, the G.1 `routing.py`, the signed HTTPS `adapter.py` + circuit
> breaker, the `quickml.py` RAG/no-code contract, the AWS `gpu-worker` and the
> scoped SSE channel — into a governed **prediction runtime**, and adds the
> Part-G-specific layers that did not exist before: **model/RAG placement**,
> the **dispatch-mode policy**, **fail-closed result validation**, **Data Store
> lineage**, the **orchestrator**, and the **baseline-vs-AWS comparison**.
> Nothing below claims a cloud deployment: the SageMaker/Batch/ECR deploy, the
> real GPU run and enabling QuickML all spend credits / need the account and are
> **HELD**. Every offline equivalent is verified against the real code paths.

---

## 0. Item-by-item status (spec Part G, 1–5 + the prediction flow)

| # | Requirement | State |
|---|---|---|
| 1 | QuickML for any enabled text-LLM/RAG/KB + an eligible no-code ML baseline; Zia AutoML only if actually exposed, else record the verified regional unavailability | **IMPLEMENTED / DONE** — `quickml.py` (pre-existing) + new `placement.py` records QuickML RAG + no-code on Catalyst and **Zia AutoML UNAVAILABLE (IN DC) with doc evidence** (§1). QuickML enable is **HELD** |
| 2 | Run TabFM/TimesFM/custom GPU externally (Catalyst has no GPU runtime); private ECR + temporary S3 staging only for SageMaker/AWS Batch | **IMPLEMENTED** — `gpu-worker` (pre-existing) + `placement.py` places TabFM/TimesFM/ST-GNN on AWS GPU with ECR + temp-S3; `adapter`/`aws-adapter` carry the S3-staged Batch/SageMaker path (§2). Real ECR/GPU run **HELD** |
| 3 | Prefer AWS Batch for offline forecasts/backfills/eval + scale to zero; SageMaker async only for a *measured* NRT need; real-time only after a benchmark; never Serverless for a GPU workload | **IMPLEMENTED** — new `dispatch_policy.py` encodes exactly this + a validator + a GPU-never-serverless guard (§3) |
| 4 | Compare the QuickML/no-code baseline vs the custom AWS model on the SAME time-aware/group-aware split with leakage guardrails | **IMPLEMENTED** — new `comparison.py` (shared-split hash + leakage-safe gate) + `from_workload_evaluation` folds in the QuickML no-code baseline (§4) |
| 5 | Store model/version/feature lineage + validated predictions in Data Store; the AWS runtime never writes to the browser and is not the authoritative DB | **IMPLEMENTED** — new `lineage.py` + `runtime.py` persist FeatureSnapshot/PredictionRequest/PredictionResult to Data Store with full lineage; results are NEW records tagged `authoritative_store=catalyst_data_store` (§5) |
| flow | The full prediction flow (Gateway→Function→AppSail→validate+persist→Jobs→adapter→Batch/SageMaker→validate→Data Store→Signals→poll/scoped channel→UI) | **IMPLEMENTED** — new `runtime.py` orchestrator + `router.py`; data-minimized notice bridges to the Part F scoped SSE channel (§6). Live deploy **HELD** |

New files (all `get_diagnostics`-clean): `services/ml/app/predict/{placement,dispatch_policy,
validation,lineage,runtime,comparison,router}.py` + `infra/catalyst/ml-placement.json`;
edited: `app/predict/__init__.py`, `app/main.py`.

---

## 1. QuickML placement + Zia AutoML unavailability (item 1)

`services/ml/app/predict/placement.py` (`PLACEMENT_VERSION = 2026.07.18-1`) is the
single source of truth for **where** each ML/RAG capability runs, mirrored to
`infra/catalyst/ml-placement.json` (parity-guarded). It records **10 placements**:

- **Catalyst QuickML** — the enabled text-LLM/RAG/knowledge-base assistant
  (`quickml-rag`) and the **eligible no-code ML baseline** (`quickml-nocode-baseline`).
  The validator asserts any available RAG/no-code capability is placed on QuickML
  (never AWS/third-party).
- **Zia AutoML** — placement `UNAVAILABLE`, availability `unavailable-in-region`,
  with the **verified evidence** (Catalyst AutoML SDK docs: not offered in
  EU/AU/IN/JP/SA/CA, checked 2026-07-18) and the recorded fallback (QuickML
  no-code baseline + the justified AWS TabFM path). The validator refuses an
  `UNAVAILABLE` entry that lacks evidence + a fallback — so unavailability is
  recorded, never faked as "used".
- **AWS GPU** — TabFM / TimesFM / ST-GNN (§2).
- **Catalyst CPU** — near-repeat (Hawkes), KDE/ST-DBSCAN hotspots, forecast
  fusion and the statistical/GBM baselines.

`validate_placements()` also **cross-checks** the AWS-GPU tasks against
`capability_gaps.py` (every AWS-GPU task must have a capability-gap record), so
the two source-of-truth modules cannot drift. The QuickML RAG assistant itself is
the pre-existing `app/quickml.py` (offline fake refuses by default); enabling the
Catalyst QuickML endpoint is **HELD** behind `DRISHTI_QUICKML_RAG_ENABLED`.

## 2. TabFM/TimesFM/custom GPU run externally (item 2)

Catalyst exposes no custom GPU runtime, so the foundation/custom models run on AWS
(the genuine capability gap, justified in `capability_gaps.py`). This part was
built in earlier parts and is re-confirmed by placement:

- `services/gpu-worker/` — the ONLY image with CUDA + torch + TabFM/TimesFM
  weights: `backends.run_tabfm` explicitly selects CUDA, moves model + tensors to
  the device, runs a BF16 numerical smoke test, chunks queries and reports GPU
  name/memory/latency; it **fails closed** (`BackendUnavailable`) when CUDA or the
  digest/license-verified weights (`_tabfm_loader.py`) are missing — never a
  fallback mislabelled as TabFM. Pushed to **private ECR** by digest; weights from
  an encrypted S3 prefix via an execution role.
- The Catalyst→AWS transport (`app/predict/adapter.py` client → `services/aws-adapter/
  dispatch.py`) stages async/Batch I/O in a **KMS-encrypted S3 prefix** only —
  `S3` is temporary SageMaker/AWS Batch staging, never the application object store
  (that is Catalyst Stratus, Part E).

`placement.py` records TabFM (`station_workload_band`, `area_incident_forecast_tabfm`),
TimesFM (`timesfm_count_forecast`) and ST-GNN (`stgnn_area_forecast`) as `aws-gpu`
with the ECR + temp-S3 runtime. The real ECR build + GPU run is **HELD** (no Docker
/ no GPU in this environment; see main report §2/§8.6).

## 3. Dispatch-mode selection policy (item 3)

New `services/ml/app/predict/dispatch_policy.py` encodes the spec as one
deterministic, validated decision:

- **Offline forecasts / backfills / evaluation → AWS Batch, `scale_to_zero=True`.**
- **Measured near-real-time → SageMaker asynchronous inference** (also scale-to-zero).
- **Real-time → a real-time endpoint ONLY when `realtime_benchmarked=True`**; without
  a latency/traffic benchmark on record the run is routed to async and the decision
  flags `requires_benchmark=True, benchmark_satisfied=False`.
- **Never Serverless for a GPU workload** — `assert_no_serverless_gpu` fail-closes a
  GPU backend requesting `sagemaker_serverless`/`serverless` (and `DispatchMode` has
  no serverless member by design).

`validate_dispatch_policy()` exercises the whole matrix (both GPU + CPU backends)
and asserts every invariant at import/CI time. The chosen mode is set on the
envelope by the runtime before dispatch.

## 4. QuickML/no-code baseline vs custom AWS model (item 4)

New `services/ml/app/predict/comparison.py` makes the comparison a typed,
self-validating record with the two guarantees the spec requires:

1. **Same split** — a `SplitDescriptor` (train/val/test sizes + geographic-holdout
   districts + cutoff axis) hashes to one value; every `Comparator` carries the
   split hash it was scored on, and `validate()` **rejects** the comparison if any
   comparator used a different split.
2. **Leakage guardrails** — `validate()` refuses unless the shared dataset is
   `leakage_safe` (the leakage / protected-feature / label-independence report from
   the workload evaluation).

`from_workload_evaluation(report, quickml_baseline=…)` adapts the existing held-out
evaluation (whose candidate + baselines already share one test split), labels the
candidate as the **custom AWS model** (`google-tabfm-v1`, `aws-gpu`) and folds in the
**Catalyst QuickML no-code baseline** on the same split — recording it as a *pending*
comparator when the (held) QuickML pipeline has not run, so the record stays honest.
`skill()` and `winner()` quantify the AWS model's edge over the QuickML/CPU baselines.

## 5. Lineage + validated predictions in Data Store (item 5)

New `services/ml/app/predict/lineage.py` builds the Data Store rows keyed by a stable
`ExternalID` (idempotent upsert):

- `FeatureSnapshot` — the immutable, hashed input the model saw.
- `PredictionRequest` — the governed request + exactly the fields
  `validation.ResultExpectation.from_request_row` needs to re-validate an async result.
- `PredictionResult` — the **validated** result written back as a **NEW** record with
  full lineage (feature-schema version+digest, model version+artifact digest, context
  version, training-dataset snapshot, observation cutoff, source-version hash, dispatch
  mode, **actual** backend + device) and `AuthoritativeStore=catalyst_data_store`,
  `ResultSource=aws_model_plane`. This makes it unambiguous that AWS *produced* a result
  record and never becomes the authoritative store or writes to the browser.

## 6. The prediction runtime + flow (the G prediction flow)

New `services/ml/app/predict/runtime.py` (`PredictionRuntime`) implements the flow
exactly as drawn, with every dependency injectable (adapter, Data Store repository,
signal publisher) so it is fully testable offline:

```
route() gate  ->  build + shape-validate envelope  ->  select dispatch mode
  ->  persist FeatureSnapshot + PredictionRequest (Data Store)
  ->  protected AWS adapter.dispatch()  ->  Batch/SageMaker
  ->  adapter.poll()  ->  validate_result() (fail-closed)
  ->  persist PredictionResult (Data Store)  ->  data-minimized Signal notice
```

- **Routing gate first:** a draft / submission / raw-upload event (or an approved
  FIR missing verified geography/time/head) raises `RuntimeRefused` **before**
  anything is persisted or dispatched — no model call.
- **Fail-closed:** a `tabfm` job that comes back as a fallback is rejected by
  `validate_result` and **no** `PredictionResult` is written (the request is marked
  `rejected`/`failed`).
- **Data-minimized notice:** on success the runtime emits `{type, template, task,
  subject_kind, subject_count, state, …external ids}` — never scores/PII. A
  `ChannelSignalPublisher` bridges it to the Part F scoped SSE channel
  (`stream.publish_to_channel`) for a bound (board, user); batch jobs use the null
  publisher (Gateway polling reads Data Store).

New `services/ml/app/predict/router.py` (registered in `app/main.py`) exposes the
runtime: open aggregate-metadata introspection (`/predict/placement`,
`/predict/capability-gaps`, `/predict/routing`, `/predict/dispatch-policy`,
`/predict/health`) and the role- + write-guarded `POST /predict/jobs` +
`GET /predict/jobs/{request_id}` smoke path (a process-cached runtime shares the
offline fake adapter + Data Store across submit + collect).

## 7. Verification evidence

All offline against the real code paths (no committed test files, per the standing
constraint; a throwaway harness was used and removed):

- **38/38 harness checks passed.** Placement validate + JSON-mirror parity + Zia
  UNAVAILABLE-with-evidence + a rejected invalid placement; dispatch-policy matrix
  (offline→Batch+scale-to-zero, NRT→async, real-time-without-benchmark→async,
  benchmarked→realtime, GPU+serverless→rejected); result validation (valid accepted;
  **mislabelled TabFM rejected**, **TabFM-on-CPU rejected**, authentic TabFM-on-cuda
  accepted, row-count mismatch rejected, failed-state rejected;
  `ResultExpectation.from_request_row` round-trip); **runtime round-trip** (submit
  persists FeatureSnapshot + PredictionRequest=dispatched, mode=aws_batch; collect
  completes + persists PredictionResult; request→completed; notice data-minimized;
  result tagged AWS-not-authoritative); **TabFM fails closed** (no PredictionResult,
  request→failed); routing gate refuses a draft + an unverified approval; comparison
  validates on the shared split, winner = the AWS model, skill vs QuickML baseline
  computed, mismatched-split + leakage-unsafe both rejected; capability-gaps validate.
- **HTTP smoke (TestClient):** `/predict/placement` 200, `/predict/capability-gaps`
  200, `/predict/routing?event=fir_approved…` → `invokes_model=true` (draft →
  `false`), `/predict/dispatch-policy?…offline_forecast` → `aws_batch`,
  `/predict/health` → `InMemoryFakeAdapter`; and a full **`POST /predict/jobs` →
  `dispatched (aws_batch)` → `GET /predict/jobs/{id}` → `completed`, persisted, with
  the data-minimized notice**.
- **Static:** `get_diagnostics` clean on all 8 new/edited Python files; `app.main`
  imports and registers the 7 `/predict/*` routes; `ml-placement.json` parses and
  equals `placement.emit()`; `python -m app.predict.placement` and
  `-m app.predict.dispatch_policy` exit 0.
- **Regression:** `pytest --collect-only` = **327 tests, no import errors**.

## 7a. Demo scoping — reduced routing matrix + reduced model set (G.1 / G.2)

The routing matrix and placement map DOCUMENT every route/model, but the demo runs
only a defensible subset. New `services/ml/app/predict/enablement.py` is the single
source of truth; `routing.py` filters to the enabled tasks and `placement.py` records
each engine's enablement (both cross-checked at validate-time). Every item is
env-flippable (`DRISHTI_TASK_<NAME>_ENABLED`, `DRISHTI_ROUTE_<EVENT>_ENABLED`,
`DRISHTI_QUICKML_RAG_ENABLED`) so a demo can turn one on without a code change.

**G.1 — routing matrix (kept vs documented-but-disabled)**

| Route (event) | Demo behavior |
|---|---|
| FIR draft / submission | **kept** — no prediction (fail-safe gate) |
| Approved FIR | **kept, ENABLED** → aggregate FeatureSnapshot → near-repeat (eligible) + workload |
| Approved correction | **kept, ENABLED** → prior stale → optional rerun of changed schemas |
| Digital evidence upload | **kept** — storage + manual metadata only, no prediction from bytes |
| CSV/JSON import | **kept, ENABLED** → validation → same approved-FIR workflow |
| Approved context (weather/holiday) | **kept** → TimesFM only (ST-GNN + fusion deferred) |
| Court / laboratory / chargesheet / statement (`structured_record_approved`) | **documented, DISABLED** by default |
| CDR / device / media / financial (`structured_import_reviewed`) | **documented, DISABLED** by default (graph/similarity investigation support is a separate CPU path, unaffected) |
| Hazard/resource | **deferred** — activated by Prompt 17 |

A disabled specialized route returns `invokes_model=False` with a clear "documented
but DISABLED for the demo — enable with `DRISHTI_ROUTE_…_ENABLED=true`" reason.

**G.2 — reduced model set (enabled vs optional/deferred)**

| Model / capability | Enablement | Note |
|---|---|---|
| TabFM aggregate workload (`station_workload_band`) | **ENABLED** | primary aggregate prediction (AWS GPU) |
| TimesFM (`timesfm_count_forecast`) | **ENABLED** | scheduled time-series forecast, demo-visible (AWS GPU) |
| Near-repeat (`near_repeat_intensity`) + graph analytics | **ENABLED** | existing CPU investigation support |
| XGBoost / HistGradientBoosting baselines | **ENABLED** | CPU baseline + fallback |
| Separate TabFM AREA-forecast (`area_incident_forecast_tabfm`) | **DEFERRED** | optional |
| ST-GNN (`stgnn_area_forecast`) | **DEFERRED** | unless already stable + valuable |
| Forecast fusion (`forecast_fusion`) | **DEFERRED** | fusion over every model |
| KDE / ST-DBSCAN (`hotspot_clusters`) | **DEFERRED** | not a separate production pipeline |
| QuickML RAG + no-code baseline | **OPTIONAL** | on only when demonstrated |
| Multiple embedding index versions | **DEFERRED** | single active index only |
| Disaster model | **DEFERRED** | Prompt 17 |

Effect: an `Approved FIR` routes to `near_repeat_intensity` + `station_workload_band`
and **drops** `area_incident_forecast_tabfm`; `Approved context` routes to
`timesfm_count_forecast` only and drops ST-GNN + fusion; the runtime **refuses** a
deferred task with a crisp reason before any persist/dispatch.

**Verified (throwaway harness, 20/20, removed):** enablement summary (3 enabled /
4 deferred tasks + capabilities); FIR_APPROVED keeps enabled tasks + defers
area-forecast; CONTEXT keeps only TimesFM + defers ST-GNN/fusion; court/lab route
disabled (and re-enabled via env → workload); a deferred task appears when its env
flag is set; placement enablement counts (4 enabled / 2 optional / 4 deferred) +
JSON-mirror parity + validate-time consistency; runtime refuses a deferred task and
a disabled route while the enabled workload task still submits. `get_diagnostics`
clean; `/predict/enablement` registered (8 `/predict/*` routes total); 327 tests
still collect.

## 7b. Single AWS GPU path (G.3)

The hackathon keeps exactly **one** AWS GPU execution mechanism — **SageMaker
asynchronous inference** (scale-to-zero, tear down after the demo). `dispatch_policy.py`
now returns `sagemaker_async` for every purpose by default; the richer multi-mode
selection (AWS Batch / Batch Transform / real-time) is **retained + tested but
DEFERRED**, OFF unless `DRISHTI_DISPATCH_MULTIMODE_ENABLED=true`.

| Kept (G.3) | Deferred (G.3) |
|---|---|
| One separate GPU-worker container (`services/gpu-worker/`) | Supporting multiple SageMaker execution modes simultaneously |
| Private ECR image + private encrypted S3 model artifacts | Complex warm-worker caching |
| IAM execution role, no static credentials (Part F) | Extensive GPU memory optimisation |
| **One** SageMaker mechanism = async | Automatic canary endpoint promotion |
| Typed request/response envelope; proof of `backend=tabfm` + `device=cuda`; fail-closed when TabFM/CUDA unavailable | Multi-model endpoint lifecycle management |
| GPU shutdown after the demo (Part J runbook) | — |

`assert_no_serverless_gpu` still fail-closes a GPU backend + Serverless. Verified:
`validate_dispatch_policy()` → `single_mechanism=sagemaker_async`,
`deferred_modes=[aws_batch, batch_transform, sagemaker_realtime]`, `multimode_enabled=false`;
`GET /predict/dispatch-policy` reports the same.

## 7c. Governance kept for the hackathon (G.4)

Implemented in `runtime.py` + `lineage.py`, verified by the six tests (§7d):

- **A new FIR does not retrain TabFM** — the runtime only builds a FeatureSnapshot
  and dispatches an **inference** request; there is NO training path.
- **Training and inference stay separate** (no training trigger in the runtime).
- **Corrections create new versions** — a new `source_version_hash` yields a new
  snapshot / request / result (new ExternalIDs).
- **Historical predictions are preserved** — supersession sets `IsStale=True` +
  `SupersededByExternalID` on the prior result; it is never deleted.
- **Duplicate events do not create duplicate GPU jobs** — the idempotency key gives
  the same request/result ExternalID and the adapter dedups; an idempotent re-run
  supersedes nothing.
- **The UI shows model / version / status / stale** — every request + result row
  carries `ModelVersion`, `Status`/`State`, `IsStale`, `StaleReason`.

Deferred: full automated retraining, dataset-release approval, and production
model-promotion workflows.

## 7d. The six Part G tests (G.5)

Reduced to exactly six, committed at `services/ml/tests/test_predict_runtime.py`
(offline via the fake adapter + in-memory Data Store):

| # | Test | Result |
|---|---|---|
| 1 | FIR draft produces no prediction | **PASS** |
| 2 | Approved FIR creates one idempotent prediction request | **PASS** |
| 3 | One real TabFM CUDA prediction succeeds | **SKIPPED** — integration; runs only when the real AWS adapter + GPU plane is configured (HELD) |
| 4 | TabFM failure is not falsely labelled a success | **PASS** |
| 5 | Evidence upload does not invoke a model | **PASS** |
| 6 | Correction marks the previous result stale + permits a controlled rerun | **PASS** |

`pytest tests/test_predict_runtime.py` → **5 passed, 1 skipped**; full suite
`--collect-only` = **333 tests** (327 + 6), no import errors. TimesFM / Disaster
Response / Investigation Board tests remain in their own phases + Prompt 18.

## 8. Held cloud steps (ordered; run only with go-ahead)

These are the Part-G-specific spend/account steps (they build on Part F §8):

1. Build + push the **GPU-worker** image to **private ECR** by digest, and stage the
   TabFM/TimesFM weights in the encrypted S3 prefix (needs Docker + the AWS account;
   no local GPU — a SageMaker/Batch GPU instance runs the real inference).
2. Create the SageMaker **async** endpoint (small NRT jobs) and/or the **AWS Batch**
   GPU job queue + definition (offline forecasts/backfills/eval, scale-to-zero); set
   `DRISHTI_SM_ASYNC_ENDPOINT` / `DRISHTI_BATCH_JOB_QUEUE` / `…_JOB_DEFINITION` +
   `DRISHTI_ADAPTER_S3_STAGING` on the adapter Lambda (Part F §8 provisions the adapter).
3. On AppSail: set `DRISHTI_AWS_ADAPTER_URL` + `DRISHTI_AWS_ADAPTER_SECRET` and
   `DRISHTI_USE_CATALYST_DATASTORE=true` so the runtime persists to Catalyst Data
   Store and dispatches to the real adapter (the fake/in-memory are used until then).
4. Enable **QuickML RAG** (`DRISHTI_QUICKML_RAG_ENABLED=true` + endpoint) and run the
   **QuickML no-code baseline** pipeline; feed its held-out metrics (same split) into
   `comparison.from_workload_evaluation(quickml_baseline=…)` to replace the pending
   comparator.
5. A real-time endpoint is created **only after** a latency/traffic benchmark; until
   then `dispatch_policy` routes real-time requests to async (by design).

## 9. Honest gaps / limitations

- **No cloud run executed:** the ECR/GPU build, SageMaker/Batch endpoints, the real
  TabFM run asserting `device=cuda`, and enabling QuickML are all HELD (credits /
  AWS account / Docker+GPU). The fail-closed contract means a `tabfm` job **errors**
  rather than returning a fallback until the real GPU plane is live; every offline
  equivalent is verified.
- **Deployed persistence is Data Store:** locally the runtime uses the in-memory
  Data Store fake (and the synthetic RDS is what the write guard checks); in
  deployment `DRISHTI_USE_CATALYST_DATASTORE=true` switches the repository to the
  Catalyst SDK. The row shapes are validated offline; a live `ds:import`/write is
  Part E's HELD step.
- **QuickML no-code baseline metrics are pending** until the Catalyst pipeline runs;
  `comparison.py` records it honestly as an unavailable comparator (never fabricated).
- **Runtime job endpoints reuse the intake write guard** (localhost + synthetic
  marker) for parity with the rest of the service; in deployment the authenticated
  Gateway signed-context boundary (Part D) + the role gate are the real control, and
  the orchestration is driven by Functions + Job Scheduling calling the runtime service.
- **In-process signal hub / cached runtime:** the SSE hub + the router's cached
  runtime are per-instance; the durable notice source in deployment is Catalyst
  Signals → notify, and Gateway polling reads Data Store (Part F §9).
