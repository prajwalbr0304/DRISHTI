// Prerender the public landing page into dist/index.html.
//
// WHY
// ---
// DRISHTI ships as a client-rendered Vite SPA. Before this step, the deployed
// document was a ~1.5 KB shell whose <body> held nothing but an empty
// <div id="root">. AI crawlers and assistant retrieval agents (GPTBot,
// ClaudeBot, PerplexityBot, CCBot, ...) read raw HTML and do not execute the
// bundle, so the only text they could find was <title> and the description
// meta tag. index.html therefore carries a hand-written static summary inside
// #root as the guaranteed floor, and this script upgrades that floor to the
// REAL rendered landing page by driving headless Chromium over the built
// output and snapshotting the resulting DOM.
//
// SAFETY CONTRACT
// ---------------
// This step is strictly an enhancement and is never allowed to make the
// deployed document worse. The snapshot replaces dist/index.html only if it
// passes validation (expected landing copy present, sane size, non-empty
// #root). On any failure — missing browser binary, navigation timeout, thin
// capture — the script logs a warning, leaves the committed static fallback in
// place and exits 0 so the build still succeeds.
//
// Escape hatch: set DRISHTI_SKIP_PRERENDER=1 to bypass entirely.
//
// Runs after `vite build` and after postbuild-slate.mjs. See package.json.

import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const distDir = join(here, "..", "dist");
const indexPath = join(distDir, "index.html");

const TAG = "[prerender]";

/** Route to snapshot. Slate rewrites every path to /index.html, so there is a
 *  single HTML document to own and "/" is the only one worth capturing. */
const ROUTE = "/";

/** Copy that must survive into the snapshot, else the capture is rejected.
 *  Sourced from HERO.headline in src/routes/landing/landing.data.ts. */
const REQUIRED_TEXT = ["See more clearly", "Act more accountably"];

/** A real render of the landing page is far larger than this; the shell is
 *  ~1.5 KB and the static fallback ~14 KB. Guards against thin captures. */
const MIN_BYTES = 20_000;

/** Markers around the fallback-only <style> block in index.html, stripped from
 *  the snapshot because the markup it styles is replaced by the real render. */
const STYLE_OPEN = "<!-- prerender:fallback-style:start -->";
const STYLE_CLOSE = "<!-- prerender:fallback-style:end -->";

if (process.env.DRISHTI_SKIP_PRERENDER === "1") {
  console.log(`${TAG} DRISHTI_SKIP_PRERENDER=1 — keeping the static fallback.`);
  process.exit(0);
}

if (!existsSync(indexPath)) {
  console.error(`${TAG} dist/index.html not found — run \`vite build\` first.`);
  process.exit(1);
}

/** Give up rather than fail the build. */
function bail(reason, error) {
  console.warn(`${TAG} skipped: ${reason}`);
  if (error) console.warn(`${TAG} ${error.message ?? error}`);
  console.warn(
    `${TAG} dist/index.html keeps its static fallback, so crawlers still ` +
      `receive readable content.`,
  );
  process.exit(0);
}

/* --------------------------------------------------------------------------
   Playwright is a devDependency and its browser binaries are installed
   separately (`npx playwright install chromium`). Treat both the package and
   the binary as optional.
   ----------------------------------------------------------------------- */
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch (error) {
  bail("the `playwright` package is not installed", error);
}

/* --------------------------------------------------------------------------
   Minimal static server over dist/, with the same SPA fallback Slate applies.
   Hand-rolled rather than `vite preview` so the snapshot cannot be perturbed
   by vite.config.ts (it calls loadEnv and can register a dev proxy).
   ----------------------------------------------------------------------- */
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".geojson": "application/geo+json",
};

const server = createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);

    // Contain path traversal: resolve inside distDir or fall back to the shell.
    const resolved = normalize(join(distDir, pathname));
    const inside = resolved === distDir || resolved.startsWith(distDir + sep);

    let filePath = indexPath;
    if (inside && extname(resolved) !== "" && existsSync(resolved)) {
      filePath = resolved;
    }

    const body = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": MIME[extname(filePath).toLowerCase()] ?? "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(body);
  } catch (error) {
    res.writeHead(500, { "Content-Type": "text/plain" });
    res.end(`prerender server error: ${error.message}`);
  }
});

const port = await new Promise((resolve, reject) => {
  server.once("error", reject);
  // Port 0 = let the OS pick a free port, so this never collides with a dev
  // server or the :4173 Playwright preview.
  server.listen(0, "127.0.0.1", () => resolve(server.address().port));
}).catch((error) => bail("could not start the local static server", error));

const origin = `http://127.0.0.1:${port}`;
console.log(`${TAG} serving dist/ on ${origin}`);

let browser;
try {
  browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
} catch (error) {
  server.close();
  bail("headless Chromium is unavailable (run `npx playwright install chromium`)", error);
}

let snapshot;
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    // landing.css hides every [data-reveal] block at opacity:0 until an
    // IntersectionObserver adds .is-revealed, but its reduced-motion branch
    // pins them to opacity:1. Reduced motion therefore yields a fully visible
    // page without scroll-driving it, and also stills the background films.
    reducedMotion: "reduce",
    javaScriptEnabled: true,
  });

  // Keep the capture hermetic and quick: allow only the local origin. Google
  // Fonts, the deployed API (AuthProvider probes it on mount) and any other
  // third party are aborted. PublicLanding renders <LandingPage /> for every
  // auth status except "authenticated", so a failed auth probe is harmless.
  await context.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith(origin) || url.startsWith("data:") || url.startsWith("blob:")) {
      // Films and posters contribute nothing to indexable text and cost the
      // most bytes; drop them so the snapshot is fast and deterministic.
      if (/\.(mp4|webm|mp3|wav)$/i.test(new URL(url).pathname)) return route.abort();
      return route.continue();
    }
    return route.abort();
  });

  const page = await context.newPage();

  const consoleErrors = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto(`${origin}${ROUTE}`, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });

  // React has mounted and the landing tree is real once the hero <h1> exists
  // (id from LandingPage.tsx). This also proves #root was replaced.
  await page.waitForSelector("#lp-hero-title", { state: "attached", timeout: 45_000 });
  await page.waitForFunction(
    () => (document.getElementById("lp-hero-title")?.textContent ?? "").trim().length > 0,
    null,
    { timeout: 15_000 },
  );

  // Let deferred sections and the reveal observer settle.
  await page.waitForTimeout(1_200);

  // Belt-and-braces on top of reducedMotion: mark every reveal block visible
  // and drop the scroll-cue/loader chrome that only makes sense mid-animation.
  await page.evaluate(() => {
    document
      .querySelectorAll("[data-reveal]")
      .forEach((el) => el.classList.add("is-revealed"));
  });

  snapshot = await page.evaluate(() => `<!doctype html>\n${document.documentElement.outerHTML}`);

  if (consoleErrors.length) {
    console.warn(`${TAG} page reported ${consoleErrors.length} runtime error(s):`);
    consoleErrors.slice(0, 5).forEach((message) => console.warn(`${TAG}   ${message}`));
  }
} catch (error) {
  await browser.close().catch(() => {});
  server.close();
  bail("the page did not render in time", error);
} finally {
  await browser?.close().catch(() => {});
  server.close();
}

/* --------------------------------------------------------------------------
   Validate before overwriting. A bad snapshot is worse than no snapshot.
   ----------------------------------------------------------------------- */
const missing = REQUIRED_TEXT.filter((text) => !snapshot.includes(text));
if (missing.length) {
  bail(`the capture is missing expected landing copy (${missing.join(", ")})`);
}
if (snapshot.length < MIN_BYTES) {
  bail(`the capture is only ${snapshot.length} bytes (expected >= ${MIN_BYTES})`);
}
if (/<div id="root">\s*<\/div>/.test(snapshot)) {
  bail("the capture still has an empty #root");
}
if (!snapshot.includes("<script")) {
  bail("the capture lost its module script tag, so the app would never boot");
}

// The fallback-only stylesheet targets [data-static-shell], which the real
// render replaces. Strip it by marker (plain indexOf, no regex fragility).
let output = snapshot;
const open = output.indexOf(STYLE_OPEN);
const close = output.indexOf(STYLE_CLOSE);
if (open !== -1 && close > open) {
  output = output.slice(0, open) + output.slice(close + STYLE_CLOSE.length);
}

const before = (await readFile(indexPath, "utf8")).length;
await writeFile(indexPath, output, "utf8");

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
console.log(
  `${TAG} wrote dist/index.html — ${kb(before)} static fallback -> ${kb(output.length)} rendered landing page.`,
);
