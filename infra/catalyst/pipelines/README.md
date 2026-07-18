# infra/catalyst/pipelines — CI/CD (Phase 14 Part B, matrix row 26, workflow §1)

Catalyst Pipelines is the CI/CD component (it owns CI/CD only — data/event
workflows live in Functions/AppSail/Signals/Jobs). `catalyst-pipelines.yaml`
defines the flow; `smoke_test.py` is the post-deploy gate.

> **Deploy status:** SCAFFOLDED. The YAML + smoke test are committed and the
> smoke test runs locally. Linking the repo in **Console → Pipelines**, binding a
> runner/image, and running the credit-spending deploy stages are held for
> go-ahead.

## Stages

| Stage | Jobs | Purpose |
|---|---|---|
| `validate` | `lint`, `unit_test`, `validate_mapping` (parallel) | eslint + typecheck + web/py tests + PG→Data Store mapping-drift check |
| `scan` | `security_scan` | dependency (`npm audit`, `pip-audit`) + secret/SAST/container scans |
| `build` | `build_frontend`, `build_appsail_image` (parallel) | Vite build (+ Slate SPA config) and the linux/amd64 AppSail OCI image; artifacts → Stratus |
| `deploy` | `deploy_dev`, `rollback_dev` | dev deploy of functions/client/appsail/slate; `rollback_dev` runs only if `deploy_dev` failed |
| `release` | `smoke_dev`, `approve_prod`, `promote_prod` | smoke → human email approval → promote the **same** tested immutable digest to production (main branch only) |

Why this unblocks Docker: the local machine has no Docker, but Catalyst runners
do, so `build_appsail_image` builds the OCI image in CI. The artifact is saved as
a tar and deployed via `docker-archive://`.

## Smoke test (`smoke_test.py`)

Stdlib-only. Asserts `/health/live` and `/health/ready` are 200, that
`/internal/ping` **without** a signature is **401** (the signed-context boundary
rejects unsigned callers), and — when `ZOHO_APPSAIL_SIGNING_SECRET` is set — that
a correctly signed service context returns 200 with `scope=service`. This proves
the Node-signing ↔ Python-verification contract (report §8.2) end-to-end.

```powershell
python infra/catalyst/pipelines/smoke_test.py --base-url https://drishti-api-<zaid>.development.catalystappsail.com
```

## Idempotency, DLQ, rollback (workflow §1 contract)

- **Concurrency lock:** a single active release per environment (Console pipeline
  concurrency = 1) is the deployment lock.
- **Retry/DLQ:** transient deploy failures retry; a hard failure runs
  `rollback_dev` (redeploy last-good Slate/AppSail) and stops the pipeline.
- **Forward recovery:** Data Store is additive-schema; the `validate_mapping` job
  blocks a breaking change before deploy.
- **Immutable promotion:** production promotes the exact artifact built in
  `build` (no rebuild), after the email approval gate.
