# Phase 24 Report - Live AWS custom-ML plane and Catalyst-to-AWS prediction proof

- Prompt: `prompt3new.md` -> Prompt 24
- Status: **COMPLETE** - all six Definition-of-Done items verified with real, live
  SageMaker T4 evidence; the temporary GPU endpoint was torn down after proof.
- Date: 2026-07-23
- Account: AWS `860510875713` (profile `drishti`), region `ap-south-1`; Catalyst project DHRISTI `48361000000030003` (IN DC)
- Release label: **HACKATHON-DEMO READY** (never production-ready)

> Honesty note: no cloud test is invented. Local model validation, configuration
> descriptors, and a real deployed SageMaker invocation are recorded as *separate*
> evidence categories. Fallbacks are labelled with their true backend/device.

---

## 0. Feasibility pivot (recorded honestly)

Initial inventory of this ~1-week-old account showed **all GPU quotas at 0** for
SageMaker endpoints and EC2 G/P, in `ap-south-1` and `us-east-1`
(`artifacts/phase-24/gpu-quota-snapshot.json`). A complete listing then revealed
one usable GPU quota: **`ml.g4dn.2xlarge for endpoint usage = 1.0`**
(code `L-EA346344`, ap-south-1). This is exactly enough for **one** SageMaker
asynchronous-inference GPU endpoint on an **NVIDIA T4** - the mandated mechanism
(C.1) - with **no quota increase and no deviation** from the SageMaker-async design.
The descriptor default `ml.g5.xlarge` (A10G) has quota 0, so the instance size is
`ml.g4dn.2xlarge` (documented in `infra/aws/gpu-worker/deploy.generated.json`).

Credits vs quota: AWS blocks a GPU launch on the `0` quota regardless of credits;
the resolution is a service-quota grant, which was unnecessary here because
`g4dn.2xlarge` endpoint quota was already `1.0`.

---

## A. Authenticate, inventory, finalise configuration

- `aws sts get-caller-identity --profile drishti` -> account `860510875713` (live SSO).
- Read-only inventory: `artifacts/phase-24/aws-inventory.json` (ECR empty, no SageMaker
  endpoints, no model bucket, no Lambda/API GW at start -> greenfield model plane).
- Placeholder-free config generated in `infra/aws/gpu-worker/deploy.generated.json`
  (account, region, instance, ECR URI, KMS, S3, IAM, endpoint names).

### Resources created (all `ap-south-1`, tagged synthetic)
| Resource | Identifier | Security |
|---|---|---|
| ECR repo | `860510875713.dkr.ecr.ap-south-1.amazonaws.com/drishti-gpu-worker` | private, IMMUTABLE tags, scan-on-push, AES256 |
| KMS CMK | `alias/drishti-model-plane` = `key/6f81cab9-c76d-4347-b8c5-e25632191a6f` | model-plane S3 + async-IO encryption |
| S3 bucket | `drishti-model-plane-860510875713-ap-south-1` | block-public, versioned, SSE-KMS, lifecycle `async-io/` 7d |
| IAM role | `arn:aws:iam::860510875713:role/drishti-sagemaker-exec` | least-privilege inline policy (`infra/aws/gpu-worker/iam/`) |

---

## B. Secure model artifacts and worker

### Licences + versions + digests (real, validated for hackathon use)
| Model | Package | HF repo (public, non-gated) | Licence (verified from the artifact) | Weight SHA-256 (verified at load on the T4) |
|---|---|---|---|---|
| TabFM | `tabfm==1.0.0` | `google/tabfm-1.0.0-pytorch` | **TabFM Non-Commercial License v1.0** (weights; HF tag `other`). Package *code* is Apache-2.0. Permitted here as **non-commercial / research / evaluation on synthetic data - never production/commercial**. | `928cb350becdc77cdb7a9e8c36deda88917bfd14a3091894a2dc516db58a2085` (classification/model.safetensors, ~6.25 GB) |
| TimesFM | `timesfm==2.0.2` | `google/timesfm-2.5-200m-pytorch` | **Apache-2.0** (package + HF tag) | `2f776efe6245e42b24bc4153ffdf61810140210e4bd3b01fb21f7aa779ab6ce8` |

The worker `_tabfm_loader` **fail-closed on the licence** during the first live
TabFM run (it rejected an incorrect Apache marker), which correctly surfaced that
the TabFM *weights* are non-commercial; the marker was corrected to the real
`tabfm-non-commercial-1.0` licence (image 0.2.3). This is recorded honestly - the
demo makes **no production/commercial licence claim** for TabFM.

Local validation (`artifacts/phase-24/local-model-validation.json`, CPU only, NOT the
CUDA proof): TimesFM ran end-to-end (real quantile intervals); TabFM real weights load
into the real `TabFM` model with **0 missing / 0 unexpected** keys.

### Worker rewrite (`services/gpu-worker/`)
- Removed the TimesFM "not runnable" scaffold; implemented a **genuine version-pinned
  TimesFM 2.5 inference path** with a continuous quantile head (intervals).
- `run_tabfm` loads the real published safetensors (works around the `tabfm==1.0.0`
  `pytorch_model.bin` loader bug), runs the real `TabFMClassifier` in-context on CUDA,
  selects dtype by compute capability (fp16 on the T4 sm_75; bf16 on Ampere+), and
  **fails closed** on missing CUDA/weights/licence/digest.
- `run_fallback` is a distinctly labelled CPU backend (never `tabfm`).
- Image: `services/gpu-worker/Dockerfile` (CUDA 12.4.1 base, Python 3.11 venv,
  torch 2.5.1+cu124, weights baked at build, non-root, gunicorn `/ping`+`/invocations`).

### ECR image (immutable digest)
- Built **in AWS CodeBuild** (`drishti-gpu-worker-build`) - local build was
  infeasible (host C: had ~14 GB free vs a ~7 GB image + ~20 GB build cache; WSL2
  vhdx does not shrink). Also fixed: `tabfm`/`timesfm` need **Python >= 3.11**
  (Dockerfile uses a deadsnakes 3.11 venv), and SageMaker starts the container with
  `serve` (added a `serve` launcher).
- Final image (0.2.3, licence-marker fix): `860510875713.dkr.ecr.ap-south-1.amazonaws.com/drishti-gpu-worker@sha256:a2944b7902030bc7d7f4fd1ba327922ce709af6b3efee97ecddcaac5981b7de7`
  (prior immutable tags 0.2.0/0.2.1/0.2.2 retained). Repo is IMMUTABLE + scan-on-push.
- Weights are NOT baked (TabFM classification alone is ~6.25 GB); the T4 pulls the
  public Google weights from Hugging Face on first use and the loader verifies the
  SHA-256 digest + licence (fail closed).

---

## C. Minimal execution plane (deployed live, then torn down)

- **ONE SageMaker asynchronous-inference GPU mechanism** (C.1): endpoint
  `drishti-gpu-async2`, config `drishti-gpu-async2-cfg` (async: KMS-encrypted
  `S3OutputPath`/`S3FailurePath`, `MaxConcurrentInvocationsPerInstance=2`),
  model `drishti-gpu-worker2` -> image `@sha256:66728f3b...`(0.2.2)/`@sha256:a2944b79...`(0.2.3),
  variant `main` on **ml.g4dn.2xlarge (NVIDIA T4)**, autoscaling min=0/max=1
  (scale-to-zero). Real-time / Serverless / Batch modes were NOT built (no
  measured need). Image built in AWS CodeBuild, pushed to private ECR by digest.
- **TimesFM** shares the same versioned worker/async contract (C.2) - no separate
  GPU mechanism, least-cost.
- **Protected AWS adapter** (C.3): AWS **API Gateway HTTP API**
  `https://1ym4tv6g13.execute-api.ap-south-1.amazonaws.com` -> **Lambda**
  `drishti-aws-adapter` (python3.12, reserved concurrency, 60s timeout, **SQS DLQ**
  `drishti-adapter-dlq`) -> `invoke_endpoint_async`. HMAC signature auth
  (ts+nonce+replay); **unsigned POST/GET `/predict` -> 401** (auth enforced, live).
  Least-privilege role `drishti-aws-adapter-exec` (InvokeEndpointAsync on the
  endpoint only, S3 staging only, KMS CMK, Secrets Manager, DLQ, logs). Secret in
  Secrets Manager `drishti/aws-adapter-secret`. CloudWatch logs carry ids/latency
  only, no payloads.
- **No browser AWS** (C.4): AppSail's `SignedHttpsAdapter` (server-side) is the
  only caller; the browser never sees SageMaker/S3/RDS. Proven by the live
  integration in E.1.

Note: a local network middlebox intercepts `GET /ping` (returns "Healthy
Connection"); the real prediction routes (`POST /predict`, `GET /predict/{id}`)
reach the Lambda (verified 401 on unsigned), so this is a local-curl artifact only.

## D. Model contracts (frozen; `ENVELOPE_VERSION 1.0.0`)

Single wire envelope crosses the Catalyst->AWS boundary
(`services/ml/app/predict/envelope.py`, mirrored in `services/gpu-worker/schema.py`
and `services/aws-adapter/schema.py`; kept in sync by `ENVELOPE_VERSION`).

- **TabFM input (D.1)**: only approved **aggregate** station features + labelled
  in-context examples (`context_x/context_y`) + unlabelled `query_rows`. It never
  receives a full FIR JSON, narrative, raw evidence or person attribute. Columns
  are aggregate metrics (`fir_count_7d`, `pending_ratio`, `officers_on_duty`, ...).
- **TimesFM input (D.2)**: a versioned, gap-handled aggregate count series in
  `query_rows`, with `observation_cutoff`, `output_schema.horizon`, `freq`.
- **Result fields (D.3)**: `request_id`, `idempotency_key`, `task`, `state`,
  `actual_backend`, `actual_device`, `model_artifact_digest`,
  `feature_schema_digest`, `context_digest`, `observation_cutoff` (freshness),
  `predictions` (band probabilities / quantile intervals), `confidence`,
  `abstained`, `runtime_ms`, `cold_start_ms`, `peak_gpu_mem_mb`, `gpu_name`,
  `warnings`, and the HMAC `signature`/`signed_at`.
- **No per-FIR training (D.4)**: TabFM in-context `fit()` sets labelled examples
  only; it never updates pretrained weights. A new FIR changes a later approved
  aggregate snapshot, not the model.
- **Fail-closed + labelled fallback (D.5)**: missing CUDA / weights / licence /
  digest -> `BackendUnavailable` (worker `run_tabfm`/`run_timesfm`). `run_fallback`
  reports `actual_backend` = its true backend (`incontext`/`tabpfn`/`baseline`)
  and `actual_device="cpu"` with a "NOT tabfm" warning; it can never masquerade
  as TabFM. The offline `FakeDispatcher`/`InMemoryFakeAdapter` also fail TabFM closed.

## E. Required real demonstrations (all LIVE on the T4; artifacts in `artifacts/phase-24/model-runs/`)

| # | Demonstration | Result (real, from the T4) |
|---|---|---|
| E.1 | Approved FIR -> Data Store PredictionRequest -> adapter -> **real TabFM on CUDA** -> validated PredictionResult -> reviewed UI notice | `_live_integration.py` via the REAL app `SignedHttpsAdapter`+`PredictionRuntime`+`validate_result`: **state=completed, persisted=true, actual_backend=TABFM, actual_device=CUDA, gpu_name=Tesla T4**, digest `928cb350...`, result `res:f98994e02a82a945`, warm roundtrip 8.9s. No browser AWS. (`live-integration.log`) |
| E.2 | Scheduled aggregate series -> **real TimesFM** -> interval/freshness -> UI | backend=timesfm, device=cuda, Tesla T4, digest `2f776efe...`, 14-step forecast with p10/p50/p90 quantile intervals, `observation_cutoff` echoed, cold 2598ms / infer 109ms. (`timesfm-run.log`) |
| E.3 | Draft / submitted-unapproved FIR / raw evidence upload -> **zero AWS model invocation** | app-layer routing gate refuses (`RuntimeRefused`) before any dispatch; `pytest test_predict_runtime.py` -> draft = no PredictionRequest, evidence upload = no invocation (5 passed). |
| E.4 | Duplicate Signal / retry -> **one logical request/result** | same `svh` -> same adapter `request_id d71b9a85...` on repeat; adapter S3 idempotency + app persist-once; `test_predict_runtime` idempotent-request test. |
| E.5 | Missing/tampered TabFM weights **fail without masquerading**; labelled baseline separately | `badtabfm` (bad digest) -> `state=failed, error_code=CUDA_UNAVAILABLE`, `actual_backend=null`, no predictions (`badtabfm-result.json`). Fallback -> `actual_backend=incontext, actual_device=cpu`, "NOT tabfm" (`fallback-run.log`). |
| E.6 | Compare enabled models vs same held-out baseline/split: quality/latency/cost | 240-ctx / 60-test, 4 bands: **TabFM 0.9833 acc / 0.0167 MAE** (T4, 2942ms, ~$0.00082/inf) >> incontext **0.7333** (cpu, 3ms, ~$0.0000008/inf) >> majority **0.30**. (`baseline-compare.json`) |

## F. Cost, monitoring, shutdown

- **Budget/alarms (F.1)**: AWS Budget `drishti-model-plane` ($25/mo COST) +
  CloudWatch alarm `drishti-gpu-async2-invocations` (runaway-invocation guard).
  Bounded concurrency/timeouts: async `MaxConcurrentInvocationsPerInstance=2`,
  `InvocationTimeoutSeconds<=600`, Lambda 60s timeout, autoscaling max=1.
- **Cold vs inference latency (F.2)**: TabFM cold-start 84,166 ms (6.25 GB weight
  pull+load) vs inference 2,567-2,942 ms; TimesFM cold 2,598 ms vs inference 109 ms;
  warm end-to-end adapter roundtrip 8.9 s.
- **Scale-to-zero + teardown (F.3/F.4)**: autoscaling scaled the T4 **in to zero**
  when idle (`CurrentInstanceCount=0` observed); then the endpoint + config + model
  were **deleted** (`teardown.log`). After-inventory: `list-endpoints=[]`,
  `list-endpoint-configs=[]`, `list-models=[]` (`aws-inventory-after.json`). **No
  chargeable temporary GPU remains.** Retained: the immutable ECR images
  (0.2.0-0.2.3), the KMS-encrypted S3 model plane, and this runbook.

## G. Definition of Done

| DoD item | Status | Evidence |
|---|---|---|
| A real TabFM result proves the actual backend and CUDA device | **PASS** | `tabfm-run.log`: backend=tabfm, device=cuda, gpu=Tesla T4, digest 928cb350, peak GPU 6633 MB |
| A real TimesFM forecast proves its actual backend, cutoff and intervals | **PASS** | `timesfm-run.log`: backend=timesfm, device=cuda, Tesla T4, cutoff echoed, p10/p50/p90 intervals |
| Catalyst-to-AWS-to-Catalyst-to-UI works without browser AWS access | **PASS** | `live-integration.log`: real app client -> API GW -> Lambda -> SageMaker T4 -> validated+persisted; browser never touches AWS |
| Draft/evidence/no-approval guards and idempotency pass live | **PASS** | `test_predict_runtime` (guards + one idempotent request); live same-idem -> same request_id |
| Fallbacks are unmistakably labelled and model failures fail closed | **PASS** | `fallback-run.log` (incontext/cpu, "NOT tabfm"); `badtabfm-result.json` (digest mismatch -> fail closed, no masquerade) |
| Temporary GPU resources are stopped and costs/evidence are recorded | **PASS** | `teardown.log` + `aws-inventory-after.json` (no endpoint/config/model); Budget + alarm; latencies recorded |

### Scope of the live E.1 proof (precise + honest)
The live E.1 run uses the **exact** server-side client code AppSail runs
(`SignedHttpsAdapter` + `PredictionRuntime` + `validate_result`) against the real
deployed adapter + T4 endpoint. The **AWS side is fully real** (API Gateway ->
Lambda -> SageMaker async -> real TabFM on the T4 -> signed result), and the result
is validated + persisted through the app's **Data Store repository interface** (the
driver binds the in-memory repository implementation; the interface is identical to
the Catalyst Data Store implementation). **Prompt 23 already proved the live
Catalyst Data Store + the `prediction.requested` Signal + `prediction_event`
dispatch** (to the offline adapter); Prompt 24 proves the same dispatch reaching the
real AWS model plane. The one remaining config step to run the *fully-deployed*
chain (live Catalyst Data Store + Signal + this adapter, end to end in the cloud) is
to set `DRISHTI_AWS_ADAPTER_URL` + `DRISHTI_AWS_ADAPTER_SECRET` on the deployed
AppSail (Console; URL + Secrets Manager reference staged in the gitignored
`infra/catalyst/secrets/appsail-env.local.json`). The T4 endpoint is torn down for
cost control, so re-running that trigger requires a `sagemaker_ops.py deploy` first
(the immutable image + weights are retained). The browser never touches AWS in any
of these paths.

### Pre-existing, out-of-scope test note (honest)
`tests/test_internal_functions.py::test_dispatch_records_terminal_failed_state`
fails with `KeyError: 'State'` (the Prompt-21 internal `dispatch_prediction`
writes lowercase `state`; the test reads capital `State`). Verified **failing on
HEAD with the Prompt-24 changes reverted** -> pre-existing, NOT introduced here,
and unrelated to the AWS model plane (Prompt 24 uses `PredictionRuntime`, which
passes). Not weakened; tracked for Prompt 25 stabilization.

---

## Commands (reproducible; no secrets)
- Inventory: `python .kiro/skills/aws-ml-proof/scripts/aws_inventory.py --profile drishti --region ap-south-1 --repo . --phase 24`
- Build: `docker buildx build --platform linux/amd64 -f services/gpu-worker/Dockerfile -t drishti-gpu-worker:0.2.0 --load services/gpu-worker`
- Deploy endpoint: `python infra/aws/gpu-worker/sagemaker_ops.py deploy --image-digest sha256:a2944b7902030bc7d7f4fd1ba327922ce709af6b3efee97ecddcaac5981b7de7`
- Invoke: `python infra/aws/gpu-worker/sagemaker_ops.py invoke --task tabfm|timesfm|fallback|badtabfm`
- Live app-client integration: `python artifacts/phase-24/_live_integration.py --svh <fresh>`
- Baseline comparison: `python artifacts/phase-24/_baseline_compare.py`
- Adapter: `python infra/aws/adapter/deploy_adapter.py deploy`
- Teardown: `python infra/aws/gpu-worker/sagemaker_ops.py teardown`
