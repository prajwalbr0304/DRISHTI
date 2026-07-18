# infra/catalyst — Zoho Catalyst deployment config (Phase 14)

This directory holds the Catalyst project binding and deployment config for the
DRISHTI app. It is intentionally isolated here so the repo root and the existing
application layout (`services/ml`, `web`, `infra/aws`) are preserved.

## Binding (DONE)

The CLI is logged in (India DC) and this directory is bound to the credited
project **DHRISTI**:

| Field | Value |
|---|---|
| Project | DHRISTI |
| Project ID | `48361000000030003` |
| Org ID | `60075362708` |
| Environment | Development |
| Dev domain | `dhristi-60075362708.development` |
| Data center | IN (India) |

Binding file: `.catalystrc` (committed — contains IDs only, **no tokens**). The
CLI auth token lives **outside this repo** in the OS user-data dir managed by the
CLI (via `env-paths`). On this Windows machine that is
`%APPDATA%\zcatalyst-cli-nodejs\` (verified: `C:\Users\Prajwal\AppData\Roaming\zcatalyst-cli-nodejs`,
holding `.zcatalyst-cli-key`, `zcatalyst-cli-v1.json`, `Config/`). It is never
written into the repository, so nothing here needs to be gitignored for it.

Re-verify at any time (run from this directory):

```powershell
catalyst whoami
catalyst project:list        # DHRISTI should show "(active) (base)"
```

Do **not** run `catalyst init` again for a different project here — it would
create a duplicate binding. Use `catalyst project:use 48361000000030003` if the
active project ever needs to be reset.

## Component layout (created as deployment proceeds)

```
infra/catalyst/
  .catalystrc            # project binding (committed, no tokens)
  catalyst.json          # created by functions/client/appsail scaffolding
  functions/             # Gateway facade + event/notification Functions (Node)
  client/                # React (web/) hosting link (Slate or Web Client)
  app-config.json        # AppSail config (custom OCI runtime)
```

## Deployment runbook

> Steps that spend real credits/money are marked **$**. They are held for an
> explicit go-ahead — the finite hackathon budget (~INR 1,800) and the
> hard-to-reverse nature of some steps make silent execution unsafe.

Prerequisite: **Docker** must be installed to build the OCI images (it is not
present on the current machine). A CI runner with Docker also works.

```powershell
# 1. Build the lightweight FastAPI AppSail image (linux/amd64, no GPU stack).
docker buildx build --platform linux/amd64 `
  -f ../../services/ml/Dockerfile.appsail `
  -t drishti-api:appsail --load ../../services/ml

# 2. Scaffold Catalyst components (creates catalyst.json).
catalyst functions:add        # Gateway facade + event functions
catalyst client:setup         # React hosting (or: catalyst slate:create / slate:link)
catalyst apig:enable          # API Gateway in front of Functions

# 3. Deploy to the Development environment.  $
catalyst deploy appsail --name drishti-api --source docker://drishti-api:appsail --port 9000
catalyst deploy slate         # or the current Web Client deploy command
catalyst deploy --only functions,client

# 4. Migrate the curated serving subset (upsert by ExternalID, <=5000/table dev cap).  $
catalyst ds:import --table Case --config ./ds-import/Case.import-config.json
#   ... repeat per table; capture job ids / row counts / rejected rows.

# 5. Smoke tests (see docs/phase-reports/PHASE_14_REPORT.md §10), then promote
#    the exact tested immutable digests to production (may need console/payment).
```

## AWS custom-model plane (external, justified)

The GPU/foundation-model workloads (TabFM/TimesFM/ST-GNN) run on AWS
(SageMaker/AWS Batch), never inside AppSail. See `services/gpu-worker/` and the
protected adapter contract. RDS stays private; no `0.0.0.0/0` ingress; no browser
or AppSail CRUD path to AWS. Capability-gap justifications are in the phase report.

## Cost note

No CLI billing command exists in v1.27.0; monitor usage/budget in the Catalyst
console. Baseline (console screenshot): 17 Jul – 17 Aug 2026, INR 1,500 Basic +
INR 300 Free. Configure budget alerts at ~50/75/90% where supported.
