#!/usr/bin/env pwsh
<#
.SYNOPSIS
    DRISHTI FastAPI -> Catalyst AppSail: CLI-driven local OCI build + deploy
    (Prompt 14 Part D, items 3 + 5). Fully CLI-driven so no registry/console
    action is required for a standalone Docker deploy.

.DESCRIPTION
    Builds the lightweight linux/amd64 API image from services/ml/Dockerfile.appsail
    (NO CUDA/TabFM/TimesFM/torch-geometric) and deploys it to Catalyst AppSail as
    a custom OCI runtime.

    Verified against the installed CLI (catalyst 1.27.0):
      `catalyst deploy appsail` supports: --name --build-path --stack --platform
      --command --source --port. There is NO `standalone` subcommand in this
      version, so the exact deploy call is:

        catalyst deploy appsail --name <name> --source docker://<tag> --port <port>

    SAFETY: the deploy step is credit-spending and hard to reverse, so it only
    runs when you pass -Deploy. Without it the script builds the image and PRINTS
    the exact deploy command for review (never spends credits on its own).

.PARAMETER Name
    AppSail service name. Default: drishti-api.

.PARAMETER Tag
    Local OCI image tag to build/deploy. Default: drishti-api:appsail.

.PARAMETER Port
    Container listen port AppSail routes to. Default: 9000. (Catalyst also
    injects X_ZOHO_CATALYST_LISTEN_PORT at runtime; the image binds to that.)

.PARAMETER Deploy
    Actually run `catalyst deploy appsail` after building. Omit for build-only.

.PARAMETER SkipBuild
    Skip the docker build and deploy the already-built -Tag image.

.EXAMPLE
    ./deploy.ps1                 # build only, then print the deploy command
.EXAMPLE
    ./deploy.ps1 -Deploy         # build + deploy (spends credits)
.EXAMPLE
    ./deploy.ps1 -SkipBuild -Deploy
#>
[CmdletBinding()]
param(
    [string]$Name = "drishti-api",
    [string]$Tag = "drishti-api:appsail",
    [int]$Port = 9000,
    [switch]$Deploy,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# --- Resolve paths relative to this script (infra/catalyst/appsail) ----------
$CatalystRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path            # infra/catalyst
$RepoRoot     = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path      # repo root
$Dockerfile   = Join-Path $RepoRoot "services\ml\Dockerfile.appsail"
$BuildContext = Join-Path $RepoRoot "services\ml"

function Assert-Command($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "Required tool '$cmd' not found on PATH. $hint"
    }
}

Write-Host "== DRISHTI AppSail deploy ==" -ForegroundColor Cyan
Write-Host "  name         : $Name"
Write-Host "  image tag    : $Tag"
Write-Host "  port         : $Port"
Write-Host "  dockerfile   : $Dockerfile"
Write-Host "  build context: $BuildContext"
Write-Host "  catalyst cwd : $CatalystRoot"
Write-Host ""

if (-not (Test-Path $Dockerfile)) { Write-Error "Dockerfile not found: $Dockerfile" }

# --- Preflight ----------------------------------------------------------------
Assert-Command "catalyst" "Install the Catalyst CLI: npm i -g zcatalyst-cli, then `catalyst login`."
if (-not $SkipBuild) {
    Assert-Command "docker" "Install Docker Desktop (with buildx) to build the linux/amd64 image."
    # buildx is required for --platform on non-linux/amd64 hosts.
    & docker buildx version *> $null
    if ($LASTEXITCODE -ne 0) { Write-Error "docker buildx is unavailable. Enable Buildx in Docker Desktop." }
}

# --- Build (OCI, linux/amd64, load into the local docker image store) --------
if (-not $SkipBuild) {
    Write-Host "-- Building linux/amd64 OCI image ..." -ForegroundColor Yellow
    & docker buildx build --platform linux/amd64 -f $Dockerfile -t $Tag --load $BuildContext
    if ($LASTEXITCODE -ne 0) { Write-Error "docker build failed." }
    Write-Host "-- Build OK: $Tag" -ForegroundColor Green
} else {
    Write-Host "-- SkipBuild: using existing image $Tag" -ForegroundColor Yellow
}

# --- Deploy (exact CLI 1.27.0 syntax; credit-spending, opt-in) ---------------
$deployCmd = "catalyst deploy appsail --name $Name --source docker://$Tag --port $Port"
if ($Deploy) {
    Write-Host "-- Deploying to Catalyst AppSail (project DHRISTI) ..." -ForegroundColor Yellow
    Push-Location $CatalystRoot
    try {
        & catalyst deploy appsail --name $Name --source "docker://$Tag" --port $Port
        if ($LASTEXITCODE -ne 0) { Write-Error "catalyst deploy appsail failed." }
        Write-Host "-- Deploy submitted." -ForegroundColor Green
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "Build complete. To deploy (spends credits), run from $CatalystRoot :" -ForegroundColor Cyan
    Write-Host "    $deployCmd"
    Write-Host "  or re-run this script with -Deploy."
}

# --- Post-deploy reminders (server-side config is NOT set by this script) -----
Write-Host ""
Write-Host "Next (Console -> AppSail -> $Name -> Configuration): set server-side env" -ForegroundColor Cyan
Write-Host "keys ONLY (no values in git/logs). See appsail.deploy.json env_var_keys:"
Write-Host "  required: ZOHO_APPSAIL_SIGNING_SECRET, DRISHTI_REQUIRE_GATEWAY_CONTEXT=true,"
Write-Host "            DRISHTI_CONTEXT_AUDIENCE=drishti-appsail, DRISHTI_USE_CATALYST_DATASTORE=true,"
Write-Host "            DRISHTI_STRATUS_EVIDENCE_BUCKET, DRISHTI_STRATUS_IMPORT_BUCKET,"
Write-Host "            DRISHTI_STRATUS_REPORT_BUCKET, DRISHTI_AWS_ADAPTER_URL,"
Write-Host "            DRISHTI_AWS_ADAPTER_SECRET, SEMANTIC_PLANNER_PROVIDER=aws_bedrock,"
Write-Host "            BEDROCK_MODEL_ID=zai.glm-4.7-flash, BEDROCK_REGION=ap-south-1,"
Write-Host "            BEDROCK_DIRECT_SDK_ENABLED=false"
Write-Host "  Bedrock uses the signed AWS adapter. Never set AWS access keys on AppSail."
Write-Host "  do NOT set: DATABASE_URL (the operational CRUD path uses Catalyst Data Store)."
Write-Host ""
Write-Host "Then smoke-test the deployed base URL:" -ForegroundColor Cyan
Write-Host "  python $($RepoRoot)\infra\catalyst\pipelines\smoke_test.py --base-url https://<appsail-url>"
