# infra/catalyst/pipelines — CI/CD (Prompt 22 E; Phase 14 Part B origin)

Catalyst Pipelines is the CI/CD component (it owns CI/CD only — data/event
workflows live in Functions / AppSail / Signals / Jobs). `catalyst-pipelines.yaml`
defines the flow; `preflight_deploy.py` is the mandatory pre-deploy gate and
`smoke_test.py` is the post-deploy gate.

> **Deploy status:** the install/lint/test/build/security/preflight stages are
> fully runnable and are mirrored 1:1 by `python scripts/release_gate.py`
> locally. The credit-spending **deploy/smoke/rollback** stages run on a linked
> Catalyst runner (Console → Pipelines) with a bound, authenticated,
> non-interactive context; live proof is **Prompt 23**.

## Lean, blocking sequence (Prompt 22 E.2)

```
install -> lint/type/test -> build (web + AppSail image) -> security scans
  -> MANDATORY pre-deploy preflight -> deploy development
  -> Auth/Gateway/AppSail/Slate/Data Store/prediction smoke -> retain rollback
```

| Stage | Jobs | Purpose |
|---|---|---|
| `validate` | `lint`, `test` | web `npm ci` + eslint (locked flat config, 0 errors) + `tsc` typecheck + vitest; DB-free backend pytest (`DRISHTI_DISABLE_DB_TESTS=1`); PG→Data Store mapping-drift check |
| `build` | `build_frontend`, `build_api_image`, `gpu_worker_static` | **release** Vite build from `web` (`build:release` → FAILS on unset/invalid `VITE_API_BASE_URL` or a bundled secret); linux/amd64 **AppSail** OCI image → Stratus tar; GPU worker **static/contract check only** (py-compile + `docker build --check`) |
| `security` | `security_scan` | **real, blocking** gates (no `|| true`): `scripts/security/secret_scan.py`, `dep_audit.py`, `static_checks.py`, `infra/aws/check_no_db_url_in_web.py`, `tools/route_data_boundary.py --check`, `check:bundle:release` |
| `preflight` | `preflight_deploy` | **mandatory** `preflight_deploy.py --require-live`: project/env == DHRISTI `48361000000030003` (India DC), synthetic marker, DB-free AppSail posture, **no-duplicate** project/service |
| `deploy_dev` | `deploy_dev`, `rollback_dev` | dev deploy of functions/client/appsail/slate **from `infra/catalyst`**; `rollback_dev` runs only if `deploy_dev` failed (redeploy the retained last-good version) |
| `smoke` | `smoke_dev` | Auth + **API Gateway** (`/api/*`) + AppSail + Data Store readiness + prediction smoke, plus strict reduced acceptance |

## Corrections applied in Prompt 22 (vs the Phase-14 scaffold)

1. **Working directories / paths** — the frontend build runs from `web`; every
   `catalyst` binding/deploy command runs from `infra/catalyst`; the AppSail
   deploy uses the intended linux/amd64 image built from
   `services/ml/Dockerfile.appsail`.
2. **No `|| true`** on any mandatory audit / deploy / smoke / rollback step — a
   failed gate stops the pipeline (the previous `npm audit … || true`,
   `pip-audit … || true`, and `catalyst … --rollback || true` are gone).
3. **Real security stage** — the echo-only "secret scan" is replaced by the
   executable `scripts/security/*` gates (the same ones the local release gate
   runs), so CI and local are identical.
4. **Smoke through Auth + API Gateway** — `smoke_test.py --gateway-url` exercises
   the public `/api/*` path (Gateway → gateway_api → signed context → AppSail),
   not only the direct AppSail URL; an unauthenticated protected read is asserted
   to be refused (401/403).
5. **Mandatory pre-deploy preflight** — project/env, synthetic marker and
   no-duplicate checks must pass before any deploy.
6. **GPU worker kept separate** — this pipeline only static-checks the GPU
   Dockerfile/contract; the GPU image is built + pushed and its endpoint
   registered separately (`infra/aws/gpu-worker/`, Prompt 24) by immutable digest.

## Local equivalent

`python scripts/release_gate.py` runs the identical toolchain/lint/type/test/
build/security/route-boundary/E2E gates locally and writes a machine-readable
summary to `artifacts/phase-22/release-gate.json` (exit 0 only for a genuine
candidate). Run the pre-deploy preflight standalone with:

```powershell
python infra/catalyst/pipelines/preflight_deploy.py            # offline + best-effort live
python infra/catalyst/pipelines/smoke_test.py --base-url <appsail> --gateway-url <gateway>
```

## Deferred (documented, intentionally out of the pipeline)

- Full **SBOM + licence** automation (a real dependency vulnerability audit with
  an accepted-exception allowlist is in the `security` stage).
- **Production artifact-promotion** (approve → promote to prod) — dev deploy only.
- **GPU image rebuild in the pipeline** — built + pushed separately (Prompt 24).
- Automated **Data Store export + forward-recovery simulation** (Prompt 25).
- **Deployment concurrency locks** and **deliberately-failed-deploy recovery**.

## Rollback (workflow contract)

- **Retain previous deploy:** the prior deployment is retained; a hard
  `deploy_dev` failure runs `rollback_dev` (redeploy the last-good AppSail/Slate)
  and stops the pipeline.
- The `validate` mapping-drift check blocks a breaking Data Store change before
  deploy (Data Store schema is additive).
