# infra/aws/gpu-worker — separate GPU-worker deploy (Prompt 14 Part I + G.3)

The GPU worker is deployed **separately** from the Catalyst pipeline. The pipeline
(`infra/catalyst/pipelines/`) never rebuilds GPU images; instead the worker is
built + pushed and its SageMaker endpoint created with the AWS CLI/SageMaker
script here, and the running system references it by **immutable image + model
versions**.

## What this deploys

- One **private, IMMUTABLE, scan-on-push ECR repo** (`drishti-gpu-worker`), KMS-encrypted.
- The `services/gpu-worker/` image (CUDA + torch + TabFM/TimesFM), referenced by
  `@sha256` **digest** — never a mutable tag.
- Model artifacts in a **KMS-encrypted, versioned S3** prefix (TabFM + TimesFM
  enabled per G.2; ST-GNN deferred).
- **One SageMaker asynchronous-inference endpoint** (`drishti-gpu-async`) — the
  single AWS GPU mechanism (G.3) — with **scale-to-zero** autoscaling (`min=0`),
  served by an **IAM execution role** (no static credentials).

The Part F adapter is then pointed at it with `DRISHTI_SM_ASYNC_ENDPOINT=drishti-gpu-async`;
the AppSail app never talks to SageMaker directly.

## Files

| File | Purpose |
|---|---|
| `gpu-worker-infra.json` | reviewed descriptor (ECR / S3 / SageMaker async / autoscaling / IAM) |
| `deploy_gpu_worker.py` | validate the descriptor + print the ordered AWS CLI/SageMaker plan; `--commit` executes (HELD) |

## Usage

```powershell
# Offline plan + guardrail validation (no AWS calls, no credentials):
python infra/aws/gpu-worker/deploy_gpu_worker.py

# Plan the shutdown/cleanup:
python infra/aws/gpu-worker/deploy_gpu_worker.py --teardown

# Execute (HELD — spends AWS credits, needs the account + Docker + a GPU build host):
python infra/aws/gpu-worker/deploy_gpu_worker.py --commit --yes-spend-credits
```

`--plan` (default) is fully offline and fails closed on any G.2/G.3 violation
(mutable tag, non-GPU / serverless instance, missing scale-to-zero, missing IAM
role, or any static credential in the descriptor).

## Cost safety (J)

The async endpoint scales to zero when idle, so GPU cost is only incurred during a
run. **After testing, delete the endpoint** to stop all standing charges:

```powershell
python infra/aws/gpu-worker/deploy_gpu_worker.py --teardown        # shows the commands
aws sagemaker delete-endpoint --endpoint-name drishti-gpu-async
```

The image + model artifacts stay in ECR/S3 for a later redeploy by the same
immutable digest/version.

## Held

Building the image (Docker + a GPU build host), pushing to ECR, staging the model
artifacts, and creating the endpoint all spend credits / need the AWS account and
are **HELD** for an explicit go-ahead. The descriptor + plan are the reviewed
runbook.
