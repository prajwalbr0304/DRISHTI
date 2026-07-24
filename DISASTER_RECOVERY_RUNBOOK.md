# DRISHTI — Disaster Recovery & Rollback Runbook (Prompt 25 Part G)

> Synthetic hackathon demo on Zoho Catalyst + a bounded AWS custom-ML plane. This runbook
> covers backup, recovery, application/model rollback, retention/legal-hold and a
> deterministic demo reset. All data is synthetic; no secrets appear here.

## 0. Data-plane map (what lives where)

| Plane | Owns | Recovery mechanism |
|---|---|---|
| Catalyst **Data Store** | Board, Disaster, `PredictionRequest`, reference tables | Row export/hash + idempotent re-upsert by `ExternalID`; versioned re-import |
| Catalyst **Stratus** | Evidence / import / report objects | Object **versioning** + SHA-256 + signed-URL expiry (restore prior version) |
| AWS **RDS** (adapter-only) | Large synthetic analytics/serving corpus (read via AppSail) | `pg_dump`/row export + hash; read-replica/PITR in production (backlog SCALE) |
| AWS **S3** (KMS) | Model weights/artifacts | Immutable, versioned; redeploy from a pinned digest |

## 1. Backup (export + hash the affected rows/objects)

```text
python scripts/recovery_exercise.py --sample 200      # exports + SHA-256 a serving-row sample
# -> artifacts/phase-25/recovery/serving-rows-backup.json  (table, rows_exported, sha256)
```

- **Data Store rows:** export by table via ZCQL (page ≤ 300) to JSON; hash the canonical blob.
- **Stratus objects:** list versions; record object key + version id + SHA-256 (Phase 23 `stratus-fixture.log`).
- Store the manifest (path + hash) so a restore can be byte-verified.

## 2. Recovery drills (exercised — see `artifacts/phase-25/recovery/recovery-exercise.json`)

| Drill | Procedure | Verified |
|---|---|---|
| **Serving record** | A failed dispatch records a **terminal `failed`** state; a controlled replay (new idempotency key, adapter restored) recovers it to `dispatched`. Historical state preserved. | ✅ PASS |
| **Object version** | Restore the prior Stratus object version; verify SHA-256 + signed-URL expiry. | ✅ Live (Phase 23) |
| **Failed import / reconciliation** | A rejected import row is surfaced with a reason (never silently dropped); correct + re-submit; `cron_reconcile` replays failed items. | ✅ PASS |
| **Idempotent rerun** | Re-running a forecast window is a **duplicate** (no double-act); the prior authoritative record is preserved. | ✅ PASS |

## 3. Application rollback (Catalyst)

- **AppSail / functions / client** rollback + additive forward recovery is **live-proven** (Phase 23 `artifacts/phase-23/rollback-proof.log`) with **data retained** (Data Store/Stratus are additive; a code rollback does not drop rows/objects).
- Procedure: redeploy the prior known-good version via the pipeline / `catalyst deploy`; health-check `/health/ready`; verify a mandatory read; confirm Data Store counts unchanged.

## 4. Model-version / fallback rollback + queue replay

- The prediction envelope (v1.0.0) carries backend/device/**artifact digest**, so a model-version rollback is a **labelled, audited transition**, never a silent swap.
- Roll back by pinning the previous immutable ECR image digest and redeploying the endpoint (`sagemaker_ops.py deploy --image-digest …`).
- **Fail-closed:** missing CUDA/weights/licence/schema aborts the run rather than degrading silently; the CPU/in-context path is explicitly labelled.
- **Queue / failed-job replay:** `prediction_event` (Signal target) + `cron_reconcile` replay terminal-`failed` records idempotently (Signals retries up to 20×; the idempotency key prevents double-action).

## 5. Retention / legal-hold + deterministic demo reset

- **Retention / legal-hold:** synthetic markers + retention notes are present; production deletion/legal-hold is **backlog SEC-4** (not enforced on real classes here).
- **Deterministic synthetic reset:** re-seed the demo to a known state:
  - `python services/ml/seed_demo_board.py` (Investigation Board demo);
  - `POST /api/disaster/demo/seed` (disaster fixture);
  - Data Store upserts are idempotent by `ExternalID`, so re-seeding converges to the same state.

## 6. Shutdown / cleanup (cost control)

```text
python infra/aws/gpu-worker/sagemaker_ops.py teardown
python .kiro/skills/aws-ml-proof/scripts/aws_inventory.py --profile drishti --phase 25
# EXPECT: SageMaker endpoints = [], transform jobs = []  (temporary GPU stopped)
```

- **Confirmed 2026-07-24:** `artifacts/phase-25/aws-inventory.json` → zero SageMaker endpoints/transform-jobs; retained plane = ECR `drishti-gpu-worker`, Lambda `drishti-aws-adapter`, alarm `drishti-gpu-async2-invocations`.
- Catalyst: keep exactly one Signal + one cron active; AppSail pinned `min=max=1`; disable any canary/duplicate after evidence.
