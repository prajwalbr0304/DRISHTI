<#
.SYNOPSIS
  Builds the landing page's background films from the archived stock-footage
  frame sequences.

.DESCRIPTION
  The original stock footage (UI-VIDEOS/VIDEO-*.mp4) is no longer on disk. What
  survives is the extracted 12fps WebP frame sequences under
  `media/landing-sequences/sequence-NN/`, which are the source of truth.

  This script re-encodes each sequence into a small, seekable MP4 loop plus a
  poster still, written to `public/landing/films/`. Frames are motion-blended up
  to 24fps so the slow camera moves read smoothly, then compressed hard — every
  film is decorative background sitting under a dark scrim, so detail loss is
  invisible while the byte budget stays sane for a public page.

  Frame sequences deliberately live OUTSIDE `public/` so Vite does not copy ~44MB
  of stills into `dist/`.

.PARAMETER FfmpegPath
  Explicit ffmpeg binary. Defaults to `ffmpeg` on PATH, then to a locally
  installed `ffmpeg-static` package.

.EXAMPLE
  pwsh web/scripts/build-landing-films.ps1
#>
param(
  [string]$FfmpegPath = "",
  [string]$SourceDirectory = "",
  [int]$Fps = 24
)

$ErrorActionPreference = "Stop"

$webRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $webRoot "public\landing\films"))

if (-not $outputRoot.StartsWith($webRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to write films outside the web workspace."
}

if ([string]::IsNullOrWhiteSpace($SourceDirectory)) {
  $SourceDirectory = [System.IO.Path]::GetFullPath((Join-Path $webRoot "media\landing-sequences"))
}

if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
  throw "Frame-sequence directory does not exist: $SourceDirectory"
}

if ([string]::IsNullOrWhiteSpace($FfmpegPath)) {
  $onPath = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if ($onPath) {
    $FfmpegPath = $onPath.Source
  }
  else {
    $candidate = Join-Path $webRoot "node_modules\ffmpeg-static\ffmpeg.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { $FfmpegPath = $candidate }
  }
}

if ([string]::IsNullOrWhiteSpace($FfmpegPath) -or -not (Test-Path -LiteralPath $FfmpegPath)) {
  throw "ffmpeg not found. Pass -FfmpegPath, put ffmpeg on PATH, or `npm i -D ffmpeg-static`."
}

# Slug, source sequence, poster frame, and encode budget per film. The hero
# carries the first impression, so it gets more bits than the scroll panels.
$films = @(
  @{ slug = "vision";    sequence = "sequence-01"; poster = 30; width = 1600; crf = 30 }
  @{ slug = "reasoning"; sequence = "sequence-02"; poster = 40; width = 1280; crf = 34 }
  @{ slug = "statewide"; sequence = "sequence-03"; poster = 40; width = 1280; crf = 34 }
  @{ slug = "hotspots";  sequence = "sequence-04"; poster = 40; width = 1280; crf = 34 }
  @{ slug = "response";  sequence = "sequence-05"; poster = 40; width = 1280; crf = 34 }
  @{ slug = "command";   sequence = "sequence-06"; poster = 40; width = 1280; crf = 34 }
  @{ slug = "ksp";       sequence = "sequence-07"; poster = 40; width = 1440; crf = 32 }
)

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

foreach ($film in $films) {
  $sequenceDirectory = Join-Path $SourceDirectory $film.sequence
  if (-not (Test-Path -LiteralPath $sequenceDirectory -PathType Container)) {
    throw "Missing frame sequence: $sequenceDirectory"
  }

  $frameCount = (Get-ChildItem -LiteralPath $sequenceDirectory -Filter "frame-*.webp" -File).Count
  if ($frameCount -lt 24) {
    throw "Sequence $($film.sequence) has only $frameCount frames; refusing to encode."
  }

  $inputPattern = Join-Path $sequenceDirectory "frame-%03d.webp"
  $videoTarget = Join-Path $outputRoot ("{0}.mp4" -f $film.slug)
  $posterTarget = Join-Path $outputRoot ("{0}-poster.webp" -f $film.slug)
  $videoFilter = "scale={0}:-2:flags=lanczos,minterpolate=fps={1}:mi_mode=blend" -f $film.width, $Fps

  & $FfmpegPath -hide_banner -loglevel error -y -framerate 12 -i $inputPattern `
    -vf $videoFilter -c:v libx264 -profile:v high -pix_fmt yuv420p `
    -crf $film.crf -preset slower -g 48 -movflags +faststart -an $videoTarget

  if ($LASTEXITCODE -ne 0) { throw "Film encode failed for $($film.slug)" }

  $posterSource = Join-Path $sequenceDirectory ("frame-{0:D3}.webp" -f $film.poster)
  if (-not (Test-Path -LiteralPath $posterSource -PathType Leaf)) {
    throw "Missing poster frame: $posterSource"
  }

  & $FfmpegPath -hide_banner -loglevel error -y -i $posterSource `
    -vf ("scale={0}:-2:flags=lanczos" -f $film.width) -c:v libwebp -q:v 58 `
    -compression_level 6 -frames:v 1 $posterTarget

  if ($LASTEXITCODE -ne 0) { throw "Poster encode failed for $($film.slug)" }

  $videoKb = [math]::Round((Get-Item -LiteralPath $videoTarget).Length / 1KB)
  $posterKb = [math]::Round((Get-Item -LiteralPath $posterTarget).Length / 1KB)
  Write-Output ("{0,-10} film {1,6} KB   poster {2,4} KB   ({3} frames)" -f $film.slug, $videoKb, $posterKb, $frameCount)
}

$total = (Get-ChildItem -LiteralPath $outputRoot -File | Measure-Object Length -Sum).Sum
Write-Output ("Total landing film payload: {0} MB" -f [math]::Round($total / 1MB, 2))
