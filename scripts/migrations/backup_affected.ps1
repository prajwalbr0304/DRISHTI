<#
.SYNOPSIS
  Logical backup of every table migrations 026-035 modify, before applying them.

.DESCRIPTION
  The migrations all ship tested rollbacks, but 034 re-parents stations and
  officers and rewrites boundary rows, so a restorable copy of the affected
  tables is cheap insurance. Writes a single custom-format dump.

  Deliberately narrow: this is NOT a full-database backup. CaseMaster and its
  100k children are untouched by these migrations and are excluded to keep the
  dump small and fast.

.EXAMPLE
  ./scripts/migrations/backup_affected.ps1
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
$name  = "pre-026-035-$stamp.dump"

# Tables the migrations read or write.
# Mixed-case identifiers need double quotes for pg_dump AND single quotes to
# survive the shell. Nesting those through PowerShell -> docker -> sh silently
# dropped the quoting on the first attempt and produced a dump containing only
# the three lowercase tables. Generating a script file avoids the nesting
# entirely, and the verification step below refuses to accept a short dump.
$tables = @(
    'District', 'Unit', 'UnitLocation', 'Employee', 'JurisdictionBoundary',
    'roles', 'users', 'role_permissions'
)

$sh = @()
$sh += '#!/bin/sh'
$sh += 'set -e'
$sh += 'pg_dump "$PGCONN" -Fc --no-owner --no-acl \'
foreach ($t in $tables) { $sh += "  -t 'public.`"$t`"' \" }
$sh += "  -f /out/$name"
$sh += "pg_restore -l /out/$name | grep -c 'TABLE DATA' > /out/.tablecount"
$sh += "ls -lh /out/$name"

$shPath = Join-Path $dir ".backup.sh"
Set-Content -Path $shPath -Value ($sh -join "`n") -NoNewline -Encoding ASCII

& docker run --rm -e "PGCONN=$url" -v "${dir}:/out" $Image sh /out/.backup.sh
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

# Verify every requested table actually made it in. A dump that silently omits
# tables is worse than no dump, because it looks like protection.
$count = [int](Get-Content (Join-Path $dir ".tablecount")).Trim()
Remove-Item (Join-Path $dir ".tablecount"), $shPath -Force
if ($count -ne $tables.Count) {
    throw "dump contains $count tables, expected $($tables.Count) - refusing to treat this as a backup"
}
Write-Host "verified: $count of $($tables.Count) tables captured"

Write-Host ""
Write-Host "Backup written: $OutDir/$name"
Write-Host "Restore a single table with:"
Write-Host "  pg_restore -d `"`$DATABASE_URL`" --data-only -t '\`"District\`"' $OutDir/$name"
