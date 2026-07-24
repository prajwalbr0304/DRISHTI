# DRISHTI — Model Release Checklist (Prompt 25)

> Governs the **AWS custom-ML plane** (TabFM district-risk + TimesFM trajectory forecast)
> that Catalyst calls server-to-server. Synthetic hackathon demo. **Never** a production
> or commercial model release. TabFM weights are **Non-Commercial licence** — evaluation only.

## 1. Model inventory & provenance

| Model | Role | Backend | Weights digest (verified at load) | Licence |
|---|---|---|---|---|
| TabFM (classification) | District risk-band | PyTorch / CUDA (T4) | `928cb350…be…a2085` | **TabFM Non-Commercial License v1.0** (weights); `tabfm` PyPI code Apache-2.0 |
| TimesFM 2.5-200m | Aggregate trajectory forecast | PyTorch / CUDA (T4) | `2f776efe…ce8` | Apache-2.0 |
| SeasonalForecaster (deterministic) | Labelled CPU fallback / backtest model | CPU (numpy) | n/a | in-repo |

- Prediction envelope version: **1.0.0** (worker ↔ AppSail contract; carries backend, device, gpu_name, model_artifact_digest, request_id).
- GPU image: ECR `…/drishti-gpu-worker@sha256:a2944b79…` (tag 0.2.3), built in AWS CodeBuild. Weights pulled from Hugging Face at T4 cold-start (not baked).

## 2. Release gate (each item must hold before a model claim)

- [x] **Real backend + device proven.** TabFM ran on `DeviceKind.CUDA`, `gpu_name="Tesla T4"` (`artifacts/phase-25/live-integration-reproof.log`); TimesFM ran on `cuda`/`Tesla T4`, wrote 32 districts (`artifacts/phase-25/forecast-timesfm-only.log`).
- [x] **Artifact digest verified at load** and recorded in the result (`928cb350…`, `2f776efe…`) — matches DECISIONS.md; fail-closed on mismatch.
- [x] **TimesFM intervals + cutoff/freshness** present (fan p10/median/p90, model_version_id).
- [x] **Fallbacks labelled distinctly + fail-closed.** Missing CUDA / weights / licence / schema → the run fails closed; the CPU/in-context path is labelled `planner_source`/degraded, never silently substituted (`services/gpu-worker/backends.py`, `app/predict`).
- [x] **Data minimization.** Only approved aggregate inputs cross to AWS — never raw evidence, unrestricted FIR narratives or person attributes (`aws-ml-proof` model-proof rule; adapter envelope schema).
- [x] **Catalyst is the sole caller.** The browser never reaches AWS; AWS is reached only server-to-server via the protected adapter (API GW + Lambda `drishti-aws-adapter` + Secrets Manager + DLQ).
- [x] **Cost control / teardown.** Temporary T4 endpoint deleted after proof; **live read-only inventory confirms zero SageMaker endpoints / transform jobs** (`artifacts/phase-25/aws-inventory.json`). ECR image + KMS-encrypted S3 weights retained for an immutable redeploy.
- [ ] **Deployed AppSail → adapter chain (live, end-to-end):** the server-side client path is proven against real AWS via a driver, but the *deployed* AppSail is not yet wired (`DRISHTI_AWS_ADAPTER_URL`/`SECRET`) — see POST_HACKATHON_BACKLOG RB-3.

## 3. Redeploy / invoke / teardown (bounded, cost-aware)

```text
# single-T4 (quota L-EA346344 = 1; ml.g4dn.2xlarge only), profile drishti, ap-south-1
python infra/aws/gpu-worker/sagemaker_ops.py deploy  --image-digest sha256:a2944b79…
python infra/aws/gpu-worker/sagemaker_ops.py invoke  ...            # capture backend/device/digest
python infra/aws/gpu-worker/sagemaker_ops.py teardown              # delete endpoint/config/model + autoscaling
python .kiro/skills/aws-ml-proof/scripts/aws_inventory.py --profile drishti --phase 25  # confirm zero endpoints
```

## 4. Never claim

- No production or commercial TabFM use (weights are Non-Commercial).
- No individual synthetic person-risk prediction presented as operational.
- No accuracy certification from extrapolation; only measured runs are evidence.
