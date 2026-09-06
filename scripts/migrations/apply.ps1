<#
.SYNOPSIS
  Apply (or roll back) migrations 026-035 against the configured database.

.DESCRIPTION
  Runs each file in order with ON_ERROR_STOP, aborting on the first failure.
  Every migration is internally transactional, so a failure leaves the database
  at the last completed migration rather than half-way through one.

.EXAMPLE
  ./scripts/migrations/apply.ps1 -WhatIf        # list what would run
  ./scripts/migrations/apply.ps1
  ./scripts/migrations/apply.ps1 -Down
  ./scripts/migrations/apply.ps1 -Only 026_org_wing_range
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$Down,
    [string]$Only,
    [string]$EnvFile = ".env",
    [string]$Image = "postgis/postgis:17-3.5-alpine"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path

$ORDER = @(
    "026_org_wing_range",
    "027_users_scope_profile",
    "028_roles_six_app_roles",
    "029_role_ui_grants",
    "030_role_settings",
    "031_jurisdiction_range_level",
    "032_dashboard_rollup",
    "033_org_roster_seed",
    "034_district_commissionerates",
    "035_custom_roles"
)

$seq = if ($Down) { $ORDER[($ORDER.Count - 1)..0] } else { $ORDER }
if ($Only) { $seq = @($Only) }

$url = $null
foreach ($line in Get-Content (Join-Path $repo $EnvFile)) {
    if ($line -match '^\s*(DATABASE_URL|TARGET_DATABASE_URL)\s*=\s*(.+)$') {
        $url = $Matches[2].Trim().Trim('"').Trim("'"); break
    }
}
if (-not $url) { throw "no DATABASE_URL in $EnvFile" }

$suffix = if ($Down) { ".down.sql" } else { ".sql" }
Write-Host ("=== {0} migrations ===" -f $(if ($Down) { "ROLLING BACK" } else { "APPLYING" }))

foreach ($m in $seq) {
    $rel = "services/ml/sql/$m$suffix"
    if (-not (Test-Path (Join-Path $repo $rel))) { throw "missing: $rel" }

    if (-not $PSCmdlet.ShouldProcess($rel, "psql -f")) { continue }

    # Must go through `sh -c` so $PGCONN expands inside the container. Invoking
    # psql directly passes the literal string "$PGCONN", which psql ignores and
    # then falls back to a local unix socket that does not exist.
    $t0 = Get-Date
    & docker run --rm -e "PGCONN=$url" -v "${repo}:/repo:ro" $Image `
        sh -c "psql `"`$PGCONN`" -v ON_ERROR_STOP=1 -q -f '/repo/$rel'"
    $rc = $LASTEXITCODE
    $ms = [int]((Get-Date) - $t0).TotalMilliseconds

    if ($rc -ne 0) {
        Write-Host ("FAILED  {0}  (exit {1})" -f $m, $rc) -ForegroundColor Red
        Write-Host "Database is at the last successfully completed migration." -ForegroundColor Yellow
        exit $rc
    }
    Write-Host ("ok      {0}  ({1} ms)" -f $m, $ms)
}

Write-Host "=== done ==="
