# Rasterise the generated SVG diagrams to PNG at 2x for PowerPoint embedding.
# python-pptx cannot embed SVG, so the deck needs bitmaps.
# Uses the Playwright browser already installed for web/ end-to-end tests.
#
#   pwsh scripts/rasterise_diagrams.ps1
#
param(
    [string]$SvgDir = "docs/assets/diagrams",
    [int]$Scale = 2
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$svgPath = Join-Path $repo $SvgDir
$pngPath = Join-Path $svgPath "png"
New-Item -ItemType Directory -Force -Path $pngPath | Out-Null

# The helper must live inside web/ so Node can resolve @playwright/test from
# web/node_modules; a script in $env:TEMP cannot see it.
$script = Join-Path $repo "web/.drishti-rasterise.mjs"
@'
import { chromium } from "@playwright/test";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, basename } from "node:path";

const [svgDir, pngDir, scaleArg] = process.argv.slice(2);
const scale = Number(scaleArg) || 2;
const files = readdirSync(svgDir).filter((f) => f.endsWith(".svg"));

const browser = await chromium.launch();
for (const file of files) {
  const svg = readFileSync(join(svgDir, file), "utf8");
  const w = Number(/width="(\d+)"/.exec(svg)?.[1] ?? 1600);
  const h = Number(/height="(\d+)"/.exec(svg)?.[1] ?? 900);
  const page = await browser.newPage({
    viewport: { width: w, height: h },
    deviceScaleFactor: scale,
  });
  await page.setContent(
    `<!doctype html><meta charset="utf-8">
     <style>html,body{margin:0;padding:0;background:#fff}</style>${svg}`,
    { waitUntil: "load" }
  );
  const out = join(pngDir, basename(file, ".svg") + ".png");
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: w, height: h } });
  await page.close();
  console.log(`  ${basename(out)}  ${w * scale}x${h * scale}`);
}
await browser.close();
'@ | Set-Content -Path $script -Encoding UTF8

Push-Location (Join-Path $repo "web")
try {
    node $script $svgPath $pngPath $Scale
}
finally {
    Pop-Location
    Remove-Item $script -ErrorAction SilentlyContinue
}
Write-Output "PNGs written to $SvgDir/png"
