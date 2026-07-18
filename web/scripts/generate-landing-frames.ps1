param(
  [string]$SourceDirectory = "",
  [int]$FramesPerSecond = 12,
  [int]$Width = 1600,
  [int]$Quality = 62
)

$ErrorActionPreference = "Stop"

$webRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $webRoot "public\landing"))

if (-not $outputRoot.StartsWith($webRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to write landing frames outside the web workspace."
}

if ([string]::IsNullOrWhiteSpace($SourceDirectory)) {
  $SourceDirectory = [System.IO.Path]::GetFullPath((Join-Path $webRoot "..\..\UI-VIDEOS"))
}

if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
  throw "Video source directory does not exist: $SourceDirectory"
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  throw "ffmpeg is required to generate the landing-page frame sequences."
}

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

1..7 | ForEach-Object {
  $sequence = $_
  $source = Join-Path $SourceDirectory ("VIDEO-{0}.mp4" -f $sequence)
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing source video: $source"
  }

  $sequenceDirectory = Join-Path $outputRoot ("sequence-{0:D2}" -f $sequence)
  New-Item -ItemType Directory -Force -Path $sequenceDirectory | Out-Null

  Get-ChildItem -LiteralPath $sequenceDirectory -Filter "frame-*.webp" -File |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }

  $target = Join-Path $sequenceDirectory "frame-%03d.webp"
  $filter = "fps=$FramesPerSecond,scale=$Width`:-2:flags=lanczos"

  & ffmpeg -hide_banner -loglevel error -y -i $source -vf $filter `
    -c:v libwebp -q:v $Quality -compression_level 6 $target

  if ($LASTEXITCODE -ne 0) {
    throw "Frame generation failed for $source"
  }

  $count = (Get-ChildItem -LiteralPath $sequenceDirectory -Filter "frame-*.webp" -File).Count
  Write-Output ("Generated sequence {0:D2}: {1} frames" -f $sequence, $count)
}

