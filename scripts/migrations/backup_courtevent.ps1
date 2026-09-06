<#
.SYNOPSIS
  Logical backup of CourtEvent before migration 036 populates pending hearings.
.DESCRIPTION
  036 is purely ADDITIVE — it inserts one scheduled hearing per pending-trial case
  and marks each row in Detail so the rollback can delete exactly what it added,
  touching no pre-existing row. A dump is still cheap insurance against getting
  that predicate wrong, and CourtEvent is the only table involved.

  Same generated-script approach as backup_affected.ps1: nesting the mixed-case
  quoting through PowerShell -> docker -> sh silently drops it.
.EXAMPLE
  ./scripts/migrations/backup_courtevent.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir = "backups",
    [string]$EnvFile = ".env",
    [string]$Image = "postgis/postgis:17-3.5-alpine"
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path

$url = $null
foreach ($line in Get-Content (Join-Path $repo $EnvFile)) {
    if ($line -match '^\s*(DATABASE_URL|TARGET_DATABASE_URL)\s*=\s*(.+)$') {
        $url = $Matches[2].Trim().Trim('"').Trim("'"); break
    }
}
if (-not $url) { throw "no DATABASE_URL in $EnvFile" }

$dir = Join-Path $repo $OutDir
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$name  = "pre-036-courtevent-$stamp.dump"

$sh = @()
$sh += '#!/bin/sh'
$sh += 'set -e'
$sh += 'pg_dump "$PGCONN" -Fc --no-owner --no-acl \'
$sh += "  -t 'public.`"CourtEvent`"' \"
$sh += "  -f /out/$name"
$sh += "pg_restore -l /out/$name | grep -c 'TABLE DATA' > /out/.ce_tablecount"
$sh += "ls -lh /out/$name"

$shPath = Join-Path $dir ".backup_ce.sh"
Set-Content -Path $shPath -Value ($sh -join "`n") -NoNewline -Encoding ASCII

& docker run --rm -e "PGCONN=$url" -v "${dir}:/out" $Image sh /out/.backup_ce.sh
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

# A dump that silently contains no table data is worse than no dump, because it
# looks like insurance. Refuse it.
$countFile = Join-Path $dir ".ce_tablecount"
$count = [int](Get-Content $countFile -Raw).Trim()
if ($count -lt 1) { throw "dump contains no TABLE DATA sections - refusing to proceed" }

$dump = Join-Path $dir $name
$size = (Get-Item $dump).Length
Write-Host "backup ok: $name ($([math]::Round($size/1MB,2)) MB, $count table)"
Remove-Item $shPath, $countFile -ErrorAction SilentlyContinue
