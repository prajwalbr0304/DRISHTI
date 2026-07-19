# infra/catalyst/pipelines — CI/CD (Phase 14 Part B + Part I scoping, matrix row 26, workflow §1)

Catalyst Pipelines is the CI/CD component (it owns CI/CD only — data/event
workflows live in Functions/AppSail/Signals/Jobs). `catalyst-pipelines.yaml`
defines the flow; `smoke_test.py` is the post-deploy gate.

> **Deploy status:** SCAFFOLDED. The YAML + smoke test are committed and the
> smoke test runs locally. Linking the repo in **Console → Pipelines**, binding a
> runner/image, and running the credit-spending deploy stages are held for
> go-ahead.

## Part I — the sufficient hackathon pipeline

```
install dependencies -> lint/test -> build frontend + API -> scan for secrets
  -> deploy to Catalyst development -> health/auth/prediction smoke tests
  -> retain the previous deploy for rollback
```

| Stage | Jobs | Purpose |
|---|---|---|
| `validate` | `lint`, `test` (parallel) | install deps + eslint/typecheck + web/py tests + PG→Data Store mapping-drift check |
| `build` | `build_frontend`, `build_api_image` (parallel) | Vite build (+ Slate SPA config) and the linux/amd64 **AppSail API** OCI image; artifacts → Stratus |
| `scan` | `secret_scan` | scan for secrets (gitleaks/trufflehog) + a light, non-blocking dep audit |
| `deploy_dev` | `deploy_dev`, `rollback_dev` | dev deploy of functions/client/appsail/slate; `rollback_dev` runs only if `deploy_dev` failed (retain previous deploy) |
| `smoke` | `smoke_dev` | health + auth + prediction smoke tests |

Why this unblocks Docker: the local machine has no Docker, but Catalyst runners
do, so `build_api_image` builds the OCI image in CI. The artifact is saved as a
tar and deployed via `docker-archive://`.

## Deferred (documented, intentionally out of the pipeline)

- Full **SBOM + licence** automation (a basic secret scan + non-blocking dep audit
  is kept).
- **Production artifact-promotion gates** (approve → promote to prod) — dev deploy
  only for the hackathon.
- **GPU image rebuilding in the pipeline** — the GPU worker is built + pushed and
  the SageMaker endpoint created **separately** with AWS CLI/SageMaker scripts
  (see `infra/aws/gpu-worker/`) and referenced by **immutable image/model
  versions**.
- Automated **Data Store export + forward-recovery simulation**.
- **Deployment concurrency locks** (parallel deploys are not expected here).
- **Deliberately-failed-deployment recovery testing**.

## Smoke test (`smoke_test.py`)

Stdlib-only. Asserts `/health/live` and `/health/ready` are 200; that
`/internal/ping` **without** a signature is **401** (the signed-context boundary
rejects unsigned callers) and — when `ZOHO_APPSAIL_SIGNING_SECRET` is set — that a
correctly signed service context returns 200 with `scope=service` (the Node-signing
↔ Python-verification contract, report §8.2); and that the **prediction plane** is
live via `GET /predict/health` (200) and `GET /predict/enablement` (200 with the
enabled model tasks present). No GPU call is made — the real TabFM run is the held
cloud step.

```powershell
python infra/catalyst/pipelines/smoke_test.py --base-url https://drishti-api-<zaid>.development.catalystappsail.com
```

## Rollback (workflow §1 contract)

- **Retain previous deploy:** the prior deployment is retained; a hard `deploy_dev`
  failure runs `rollback_dev` (redeploy the last-good AppSail/Slate) and stops the
  pipeline.
- The `validate` mapping-drift check blocks a breaking Data Store change before
  deploy (Data Store schema is additive).
