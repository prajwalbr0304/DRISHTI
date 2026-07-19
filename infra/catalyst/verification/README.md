# infra/catalyst/verification — Part K reduced demo acceptance

Part K is scoped to the **actual demo**. `acceptance-checklist.json` is the single
authoritative list of the **11** things the demo must prove; `acceptance_check.py`
is the one command that runs the runnable checks and reports the rest honestly.

## The 11 required checks

| # | Proves | Runnable now? |
|---|---|---|
| K1 | Frontend deployed through Catalyst | HELD (needs Slate/Web deploy) |
| K2 | Authentication + API Gateway work | HELD (needs deploy) |
| K3 | AppSail backend works | HELD (needs deploy) |
| K4 | Data Store serves operational data | HELD (needs deploy + `ds:import`) |
| K5 | Stratus stores one evidence file | MANUAL (upload one file post-deploy) |
| K6 | Approved FIR reaches TabFM on AWS GPU | HELD (needs the GPU plane) |
| K7 | Prediction returns to Catalyst + appears in the UI | HELD (needs deploy) |
| K8 | Drafts + evidence files do NOT invoke the model | **now** (committed tests) + live re-check |
| K9 | One Signal + one scheduled job | **now** (config) |
| K10 | No secrets in the browser | **now** (`check_no_db_url_in_web.py`) |
| K11 | AWS GPU resources are stopped | MANUAL/ops (`deploy_gpu_worker.py --teardown`) |

## Test only when that feature is enabled

**NoSQL, Cache, Mail, Push, SmartBrowz, QuickML, Circuits** are deliberately NOT in
the minimum set. Each is tested only when it is actually enabled (its
`DRISHTI_*_ENABLED` flag / region availability). See `test_only_when_enabled` in
the checklist.

## Usage

```powershell
# Offline (no deploy): runs K9 + K10 now, reports the rest HELD/MANUAL with commands.
python infra/catalyst/verification/acceptance_check.py

# Full demo acceptance (post-deploy):
python infra/catalyst/verification/acceptance_check.py `
  --base-url https://drishti-api-<zaid>.development.catalystappsail.com `
  --web-url  https://drishti-<...>.onslate.in `
  --read-endpoint /api/cases?limit=1 --result-endpoint /api/predictions?limit=1
```

Status per item: **PASS** (proven now), **FAIL** (a runnable check failed — the only
thing that fails the run), **HELD** (needs the deploy/GPU plane; command shown),
**MANUAL** (a human/ops step; command shown). Set `ZOHO_APPSAIL_SIGNING_SECRET` to
also check the signed-context happy path in K2; pass `--tabfm-live` (post-deploy) to
attempt the real K6 round-trip.

## Where each check's offline evidence already lives

- **K8** — `services/ml/tests/test_predict_runtime.py` (`test_fir_draft_produces_no_prediction`,
  `test_evidence_upload_does_not_invoke_model`) pass offline.
- **K9** — `infra/catalyst/jobs/{signals-rules.json,cron-schedules.json}` (`tier: "minimal"`).
- **K10** — `infra/aws/check_no_db_url_in_web.py` + `web/scripts/check-bundle-secrets.mjs`.
- **K6** — `test_predict_runtime.py::test_real_tabfm_cuda_prediction_succeeds` (skipif no GPU)
  + `app/predict/{runtime,validation}.py` + `services/gpu-worker/`.
- **K11** — `infra/aws/gpu-worker/deploy_gpu_worker.py --teardown` + `billing/budget.json` cleanup.
