# infra/catalyst/appsail — FastAPI custom OCI runtime (Phase 14 Part D)

The full DRISHTI FastAPI service (`services/ml`) is the AppSail application
(matrix rows 2 + 3: Docker image deployment + full managed web app). AppSail
runs the persistent process; the browser reaches it only through the API Gateway
→ `gateway_api` function → AppSail path.

> **Status:** CODE COMPLETE, deploy HELD. The image artifact
> (`Dockerfile.appsail`, `requirements.appsail.txt`), the deploy descriptor
> (`appsail.deploy.json`), the health/readiness endpoints, the **inbound
> signed-context enforcement** (`app/gateway_enforcement.py`), the **audience
> claim** and **structured redacted access logging** (`app/obs.py`) are DONE and
> locally verified. The image **build requires Docker** (absent on this machine)
> and `catalyst deploy appsail` is a **credit-spending** step held for go-ahead.

## Why no `app-config.json` here

Catalyst custom (Docker) runtimes do **not** use `app-config.json` — that file
is only for Catalyst-managed runtimes. For an OCI image the stack/command/port
are baked into the image, and remaining config is supplied via
`catalyst deploy appsail` flags and the Console. `appsail.deploy.json` is our
own reviewed descriptor of those intended values (consumed by the CI/CD pipeline
and `deploy.ps1`); it stores only env-var **keys**, never secret values.

## Port contract

The container binds to `X_ZOHO_CATALYST_LISTEN_PORT` (Catalyst injects it;
default 9000). `Dockerfile.appsail`'s `CMD` uses
`${X_ZOHO_CATALYST_LISTEN_PORT:-${APP_PORT:-9000}}`, and Catalyst verifies the
process is listening within 10s of instance start. `EXPOSE 9000` is Docker
documentation only.

## Build + deploy (held; requires Docker + go-ahead)

Use the CLI-driven script (preferred). It builds the linux/amd64 OCI image and,
only with `-Deploy`, runs the deploy (credit-spending). Without `-Deploy` it
builds and prints the exact deploy command for review:

```powershell
# build only, then print the deploy command:
./deploy.ps1
# build + deploy (spends credits):
./deploy.ps1 -Deploy
```

Equivalent raw commands:

```powershell
# 1. Build the lightweight linux/amd64 image (no GPU/foundation stack).
docker buildx build --platform linux/amd64 `
  -f ../../../services/ml/Dockerfile.appsail `
  -t drishti-api:appsail --load ../../../services/ml

# 2. Standalone Docker deploy from infra/catalyst (project DHRISTI).  $
catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000
```

> **CLI syntax note:** the installed CLI is **catalyst 1.27.0**, whose
> `catalyst deploy appsail` supports `--name --build-path --stack --platform
> --command --source --port`. There is **no `standalone` subcommand** in this
> version, so the deploy call is exactly the one above (the `... appsail
> standalone ...` form from the brief is not valid here). Re-inspect with
> `catalyst deploy appsail --help` before deploying on a different CLI version.

## Configuration (Console → AppSail → drishti-api → Configuration)

- **Memory** 512 MB, **disk** 256 MB, **instances** min 1 / max 2 (scale-to-low
  for credit control), scale-up at 80%.
- **catalyst_auth = false** — DRISHTI uses its own gateway facade + signed
  context (§8.2); the Catalyst SSO wrapper would intercept and break it.
- **Health check** path `/health/ready`; liveness `/health/live` (RDS is
  advisory only and never flips readiness — the operational CRUD path uses
  Catalyst Data Store, not RDS).
- **Env vars** (keys in `appsail.deploy.json`; set values Console-side, never in
  git/logs):
  - `ZOHO_APPSAIL_SIGNING_SECRET` — HMAC secret shared with the Functions.
  - `DRISHTI_REQUIRE_GATEWAY_CONTEXT=true` — turns ON inbound signed-context
    enforcement so unauthenticated browser CRUD is rejected (items 10/12).
  - `DRISHTI_CONTEXT_AUDIENCE=drishti-appsail` — audience the context must carry.
  - `DRISHTI_USE_CATALYST_DATASTORE=true`, `DRISHTI_USE_CATALYST_STRATUS=true` +
    the three `DRISHTI_STRATUS_*_BUCKET` names.
  - `DRISHTI_ACCESS_LOG_ENABLED=true` — structured redacted access logs.
  - `DRISHTI_AWS_ADAPTER_URL` + `DRISHTI_AWS_ADAPTER_SECRET` — required signed
    server-to-server boundary. The secret is configured in AppSail and AWS
    Secrets Manager only; it is never committed, logged, or sent to the browser.
  - `SEMANTIC_PLANNER_PROVIDER=aws_bedrock`,
    `BEDROCK_MODEL_ID=zai.glm-4.7-flash`, and `BEDROCK_REGION=us-east-1`.
    Prefer `BEDROCK_DIRECT_SDK_ENABLED=false` so AppSail signs requests to the AWS
    adapter. The dedicated least-privilege `AWS_ACCESS_KEY_ID` and
    `AWS_SECRET_ACCESS_KEY` server-side variables enable direct failover when the
    retained adapter is unavailable; the flag remains useful for local profiles.
  - **`DATABASE_URL` is NOT set** for the operational CRUD path — it is only ever
    an optional read-only analytics adapter, never required for readiness, and
    never shipped to the browser.

## Inbound trust boundary (items 10 + 12)

`app/gateway_enforcement.py` (enabled by `DRISHTI_REQUIRE_GATEWAY_CONTEXT`)
verifies the signed `X-DRISHTI-Context` / `X-DRISHTI-Signature` headers
(**signature → audience → scope → expiry → replay**, see
`services/ml/app/gateway_context.py`) *before* handling any non-health request.
On success it strips client identity headers and injects the **server-trusted**
role so the per-domain role gates act on the verified identity — never a
spoofable client `X-Role`. CORS is never treated as authentication.

Verify after deploy:

```powershell
python ../pipelines/smoke_test.py --base-url https://<appsail-url>
```

The smoke test asserts `/health/live` + `/health/ready` are 200, an unsigned
`/internal/ping` is 401, and a validly signed service context is 200.
