// Fail the build if a secret-shaped string reached the static bundle, and — in
// RELEASE mode — if the production API Gateway URL is unset/invalid.
//
// Phase 14 Part C rule: no DATABASE_URL, signing secret, AWS URL/keys or any
// credential may be inlined into the browser bundle (VITE_* only carries public
// values). This scans dist/ for high-confidence secret patterns (always fatal).
//
// Prompt 22 §B.5 / §D: a RELEASE build MUST FAIL if VITE_API_BASE_URL is unset
// or invalid — warning-only is not acceptable for release mode. Enable release
// mode with `--release` or DRISHTI_RELEASE_BUILD=1. In release mode:
//   * the unconfigured production placeholder in dist/ is FATAL (not a warning);
//   * the build-time VITE_API_BASE_URL must be a valid https Catalyst API
//     Gateway origin routing `/api` — never empty, http, localhost, an AWS URL,
//     or a raw AppSail URL.
// In non-release (local dev) builds the placeholder stays a warning so a
// standalone `vite build` still succeeds.

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const distDir = join(here, "..", "dist");

const RELEASE =
  process.argv.includes("--release") ||
  ["1", "true", "yes"].includes(String(process.env.DRISHTI_RELEASE_BUILD || "").toLowerCase());

const PLACEHOLDER = "REPLACE-WITH-CATALYST-API-GATEWAY-ORIGIN";

if (!existsSync(distDir)) {
  console.error("[check-bundle-secrets] dist/ not found — run `vite build` first.");
  process.exit(1);
}

// High-confidence secrets / disallowed values that must never ship to a browser.
const FATAL = [
  { name: "PostgreSQL connection string (DATABASE_URL)", re: /postgres(?:ql)?:\/\/[^\s"']+/i },
  { name: "PEM private key", re: /-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----/ },
  { name: "AWS access key id", re: /\bAKIA[0-9A-Z]{16}\b/ },
  { name: "AWS URL exposed to the browser", re: /[a-z0-9.-]+\.amazonaws\.com/i },
  { name: "AppSail HMAC signing secret env key", re: /ZOHO_APPSAIL_SIGNING_SECRET/ },
  { name: "Server DB env key", re: /\bREADONLY_ROLE\b|\bSYNTHETIC_ENV_EXPECTED\b/ },
];

// The unconfigured production API placeholder. WARN locally, FATAL in release.
const PLACEHOLDER_PAT = {
  name: "Unconfigured production API base URL placeholder — set VITE_API_BASE_URL before deploying",
  re: new RegExp(PLACEHOLDER),
};

const SCAN_EXT = new Set([".js", ".mjs", ".cjs", ".css", ".html", ".json", ".map"]);

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...walk(full));
    else if (SCAN_EXT.has(extname(full))) out.push(full);
  }
  return out;
}

// --- Release-mode API Gateway URL validation (build-time env) ---------------
// Mirrors the contract in src/config/runtime.ts + web/.env.production: one
// PUBLIC https Catalyst API Gateway origin that routes `/api/*`. Never an AWS
// URL, never a raw AppSail URL, never localhost, never http.
function validateReleaseApiUrl(rawUrl) {
  const url = (rawUrl ?? "").trim();
  if (!url) return { ok: false, reason: "VITE_API_BASE_URL is unset/empty" };
  if (url.includes(PLACEHOLDER)) return { ok: false, reason: "still the unconfigured placeholder" };
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return { ok: false, reason: `not a valid absolute URL: "${url}"` };
  }
  if (parsed.protocol !== "https:") return { ok: false, reason: `must be https:// (got "${parsed.protocol}//")` };
  const host = parsed.hostname.toLowerCase();
  if (host === "localhost" || host === "127.0.0.1" || host === "::1" || host.endsWith(".local"))
    return { ok: false, reason: `must not be localhost/loopback (got "${host}")` };
  if (/amazonaws\.com/i.test(host) || /\.aws\b/i.test(host))
    return { ok: false, reason: `must be the Catalyst API Gateway, never an AWS URL (got "${host}")` };
  if (/catalystappsail\.com$/i.test(host))
    return { ok: false, reason: `must be the API Gateway origin, not a raw AppSail URL (got "${host}")` };
  const path = parsed.pathname.replace(/\/+$/, "");
  if (!path.endsWith("/api"))
    return { ok: false, reason: `the gateway base URL must route "/api" (got path "${parsed.pathname || "/"}")` };
  return { ok: true, reason: `valid Catalyst API Gateway origin (${host}${parsed.pathname})` };
}

const files = walk(distDir);
const fatalHits = [];
const warnHits = [];
let placeholderInDist = false;

for (const file of files) {
  const text = readFileSync(file, "utf8");
  const rel = relative(distDir, file);
  for (const pat of FATAL) {
    const m = text.match(pat.re);
    if (m) fatalHits.push({ rel, name: pat.name, sample: m[0].slice(0, 60) });
  }
  if (PLACEHOLDER_PAT.re.test(text)) {
    placeholderInDist = true;
    if (RELEASE) fatalHits.push({ rel, name: PLACEHOLDER_PAT.name, sample: PLACEHOLDER });
    else warnHits.push({ rel, name: PLACEHOLDER_PAT.name });
  }
}

console.log(`[check-bundle-secrets] mode=${RELEASE ? "RELEASE" : "local"}  scanned ${files.length} file(s) in dist/.`);

// In release mode, validate the effective build-time API Gateway URL.
if (RELEASE) {
  const res = validateReleaseApiUrl(process.env.VITE_API_BASE_URL);
  if (res.ok) {
    console.log(`[check-bundle-secrets] RELEASE API URL OK — ${res.reason}.`);
  } else {
    fatalHits.push({
      rel: "(build env) VITE_API_BASE_URL",
      name: "Invalid/unset production API Gateway URL in RELEASE build",
      sample: res.reason,
    });
  }
}

for (const w of warnHits) console.warn(`[check-bundle-secrets] WARN  ${w.name}  (${w.rel})`);

if (fatalHits.length) {
  console.error(`\n[check-bundle-secrets] FAIL (${RELEASE ? "RELEASE" : "local"}) — ${fatalHits.length} blocking issue(s):`);
  for (const h of fatalHits) console.error(`  - ${h.name}: "${h.sample}"  (${h.rel})`);
  if (RELEASE && (placeholderInDist || !process.env.VITE_API_BASE_URL)) {
    console.error(
      "\nSet a valid VITE_API_BASE_URL (the https Catalyst API Gateway origin ending in /api) " +
        "before a release build, e.g. VITE_API_BASE_URL=https://<gateway-origin>/api.",
    );
  }
  console.error("Secrets must stay server-side; the release API URL must be a valid API Gateway origin.");
  process.exit(1);
}

console.log(
  `[check-bundle-secrets] OK — no secrets in the bundle` +
    (RELEASE ? " and the release API Gateway URL is valid" : "") +
    `.` +
    (warnHits.length ? ` (${warnHits.length} warning(s))` : ""),
);
