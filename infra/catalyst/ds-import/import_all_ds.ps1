<#
  DRISHTI — bulk Catalyst Data Store import (Prompt 23 B.2)

  Runs `catalyst ds:import` for every curated serving-export CSV that has a
  matching import config, NON-INTERACTIVELY (pipes Enter to answer the
  "select a staging bucket" prompt -> first bucket). Idempotent: each config is
  operation=upsert, find_by=ExternalID, so re-running never duplicates.

  Tables must already exist in the Console (ds:import does NOT create tables —
  confirmed: it returns "No such Table with the given name exists"). Missing
  tables are reported as NOT_FOUND and skipped; create them and re-run.

  Records per-table status + imported/rejected lines + source CSV SHA-256 to a
  summary JSON for the reconciliation evidence.

  Usage (from infra/catalyst/ds-import):
    # validate on one table first
    ./import_all_ds.ps1 -Tables State
    # import a batch
    ./import_all_ds.ps1 -Tables State,District,CaseCategory,Employee,CaseMaster
    # import everything with data
    ./import_all_ds.ps1
#>
[CmdletBinding()]
param(
  [string[]] $Tables = @(),                       # optional filter (base names)
  [string]   $ExportDir = "serving-export",
  [string]   $ConfigDir = "configs",
  [string]   $Out = "..\..\..\artifacts\phase-23\ds-import-results.json"
)

$ErrorActionPreference = "Stop"
$results = @()
$csvFiles = Get-ChildItem -Path $ExportDir -Filter *.csv -File | Sort-Object Name

foreach ($csv in $csvFiles) {
  $base = [System.IO.Path]::GetFileNameWithoutExtension($csv.Name)
  if ($Tables.Count -gt 0 -and ($Tables -notcontains $base)) { continue }

  $config = Join-Path $ConfigDir "$base.import.json"
  if (-not (Test-Path $config)) { continue }         # no config for this CSV -> skip

  # data rows = total lines - 1 header; skip header-only (empty) exports
  $lineCount = (Get-Content $csv.FullName | Measure-Object -Line).Lines
  $dataRows = [Math]::Max(0, $lineCount - 1)
  if ($dataRows -le 0) {
    $results += [pscustomobject]@{ table=$base; status="EMPTY_SKIPPED"; data_rows=0 }
    continue
  }

  $sha = (Get-FileHash -Algorithm SHA256 -Path $csv.FullName).Hash.ToLower()
  Write-Host "[import] $base ($dataRows rows) ..." -NoNewline

  # Pipe Enter to answer the staging-bucket prompt (selects the first bucket).
  $raw = ("`n" | catalyst ds:import ("$ExportDir/$base.csv") --config $config 2>&1 | Out-String)
  $exit = $LASTEXITCODE

  $status = "UNKNOWN"
  if ($raw -match "No such Table")                              { $status = "TABLE_NOT_FOUND" }
  elseif ($raw -match "(?i)failed|error")                       { $status = "ERROR" }
  elseif ($raw -match "(?i)job_?id|success|report|completed")   { $status = "OK" }

  Write-Host " $status"
  $results += [pscustomobject]@{
    table = $base; status = $status; data_rows = $dataRows
    source_sha256 = $sha; exit_code = $exit
    output_tail = ($raw -split "`n" | Select-Object -Last 6) -join " | "
  }
}

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToString("o")
  total        = $results.Count
  ok           = ($results | Where-Object status -eq "OK").Count
  not_found    = ($results | Where-Object status -eq "TABLE_NOT_FOUND").Count
  error        = ($results | Where-Object status -eq "ERROR").Count
  empty        = ($results | Where-Object status -eq "EMPTY_SKIPPED").Count
  results      = $results
}
$outPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Out))
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($outPath)) | Out-Null
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $outPath -Encoding UTF8
Write-Host "`n[summary] OK=$($summary.ok) NOT_FOUND=$($summary.not_found) ERROR=$($summary.error) EMPTY=$($summary.empty) -> $outPath"
