---
name: aws-ml-proof
description: Safely inventory, plan, build, scan, deploy, invoke, verify, cost-control, and tear down the bounded DRISHTI AWS TabFM/TimesFM plane using the drishti SSO profile. Use for Prompts 24-26 AWS model evidence and cleanup verification.
---

# DRISHTI AWS ML Proof

Only the `aws-ml-operator` may mutate AWS resources.

## Preflight and inventory

1. Run `scripts/aws_inventory.py --profile drishti --repo <root> --phase <N>`.
2. Confirm caller identity and selected region before mutation.
3. Inspect existing ECR, S3, KMS, IAM, networking, queues, SageMaker, Batch, Lambda/API Gateway, budgets, alarms, and logs.
4. Validate licences, versions, schemas, model/artifact hashes, and placeholder-free configuration.
5. Write a bounded change, cost, concurrency, timeout, rollback, and teardown plan.

Read `references/model-proof.md` before deployment.

## Deploy and prove

- Reuse compatible resources and immutable ECR digests.
- Send only approved aggregate inputs; never send raw evidence, unrestricted FIR narratives, or person attributes.
- Keep Catalyst as the application caller; never expose AWS to the browser.
- Capture real backend/device, CUDA state, model/image/artifact/schema/context digests, request ID, predictions/intervals, cutoff/freshness, runtime, memory, cost, confidence/abstention, and warnings.
- Label CPU/TabPFN/XGBoost fallbacks distinctly and fail closed on missing CUDA, weights, licence, or schema.

## Cleanup

After evidence, stop/delete temporary chargeable GPU endpoints/jobs, verify queues/jobs/endpoints, and record an after-inventory. Completion requires cleanup proof, not merely a teardown command.
