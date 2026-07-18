// Fail the build if a secret-shaped string reached the static bundle.
//
// Phase 14 Part C rule: no DATABASE_URL, signing secret, AWS URL/keys or any
// credential may be inlined into the browser bundle (VITE_* only carries public
// values). This scans dist/ for high-confidence secret patterns (fatal) and the
// unconfigured production API placeholder (warning).

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const distDir = join(here, "..", "dist");

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

// Non-fatal reminders.
const WARN = [
  {
    name: "Unconfigured production API base URL placeholder — set VITE_API_BASE_URL before deploying",
    re: /REPLACE-WITH-CATALYST-API-GATEWAY-ORIGIN/,
  },
];

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

const files = walk(distDir);
const fatalHits = [];
const warnHits = [];

for (const file of files) {
  const text = readFileSync(file, "utf8");
  const rel = relative(distDir, file);
  for (const pat of FATAL) {
    const m = text.match(pat.re);
    if (m) fatalHits.push({ rel, name: pat.name, sample: m[0].slice(0, 60) });
  }
  for (const pat of WARN) {
    if (pat.re.test(text)) warnHits.push({ rel, name: pat.name });
  }
}

for (const w of warnHits) console.warn(`[check-bundle-secrets] WARN  ${w.name}  (${w.rel})`);

if (fatalHits.length) {
  console.error(`\n[check-bundle-secrets] FAIL — ${fatalHits.length} secret-shaped string(s) in dist/:`);
  for (const h of fatalHits) console.error(`  - ${h.name}: "${h.sample}"  (${h.rel})`);
  console.error("\nRemove the value from any VITE_* var / source; secrets must stay server-side.");
  process.exit(1);
}

console.log(
  `[check-bundle-secrets] OK — scanned ${files.length} file(s); no secrets in the bundle.` +
    (warnHits.length ? ` (${warnHits.length} warning(s))` : ""),
);
