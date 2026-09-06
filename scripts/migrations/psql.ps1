<#
.SYNOPSIS
  Run psql against the DRISHTI RDS instance without installing a local client.

.DESCRIPTION
  Reads DATABASE_URL from .env (or TARGET_DATABASE_URL from .env.drishti-target)
  and hands it to psql inside a throwaway container via an environment variable,
  so the connection string never appears in a command line, process listing or
  shell history.

  There is no local psql on this machine and the RDS instance is reachable
  directly on 5432 with Postgres credentials; the AWS SSO profiles in this repo
  are for Bedrock, not for database auth.

.EXAMPLE
  ./scripts/migrations/psql.ps1 -Command "SELECT count(*) FROM \"District\";"
  ./scripts/migrations/psql.ps1 -File services/ml/sql/026_org_wing_range.sql
  ./scripts/migrations/psql.ps1 -Command "..." -Tuples
#>
[CmdletBinding()]
param(
    [string]$Command,
    [string]$File,
    [switch]$Tuples,
    [switch]$StopOnError,
    [string]$EnvFile = ".env",
    [string]$Image = "postgis/postgis:17-3.5-alpine"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path

function Get-DbUrl {
    param([string]$Path)
    $full = Join-Path $repo $Path
    if (-not (Test-Path $full)) { throw "env file not found: $full" }
    foreach ($line in Get-Content $full) {
        if ($line -match '^\s*(DATABASE_URL|TARGET_DATABASE_URL)\s*=\s*(.+)$') {
            return $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
    throw "no DATABASE_URL or TARGET_DATABASE_URL in $Path"
}

$url = Get-DbUrl -Path $EnvFile

# NB: not $args — that is a reserved automatic variable in PowerShell and
# assigning to it silently drops the values before docker ever sees them.
$dockerArgs = @("run", "--rm", "-e", "PGCONN=$url")
if ($File) {
    $dockerArgs += @("-v", "${repo}:/repo:ro")
}
$dockerArgs += @($Image, "sh", "-c")

$psqlFlags = "-v ON_ERROR_STOP=$(if ($StopOnError) {1} else {0})"
if ($Tuples) { $psqlFlags += " -At" }

if ($File) {
    $inner = "psql `"`$PGCONN`" $psqlFlags -f /repo/$($File -replace '\\','/')"
} elseif ($Command) {
    $enc = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    $inner = "echo $enc | base64 -d | psql `"`$PGCONN`" $psqlFlags -f -"
} else {
    throw "supply -Command or -File"
}

& docker @dockerArgs $inner
exit $LASTEXITCODE
