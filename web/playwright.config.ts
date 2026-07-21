import { defineConfig, devices } from "@playwright/test";

/* ============================================================================
   DRISHTI web — deterministic browser E2E (Prompt 22 §C).

   Two targets, ONE set of journey specs (web/e2e/*.spec.ts):

     E2E_TARGET=local  (default)
       - webServer builds the app (VITE_AUTH_MODE=offline) and serves it with
         `vite preview` on :4173.
       - specs install Playwright route interception to stub every backend call
         with deterministic fixtures (web/e2e/support/stub.ts). No backend, no
         network, no model-authored code is ever executed.

     E2E_TARGET=live   (Prompt 23)
       - NO webServer, NO stubbing. E2E_BASE_URL points at the deployed Catalyst
         gateway; the identical specs exercise the real system.

   Chromium only (per scope). No pixel snapshots — assertions are on roles,
   text and structure so dynamic maps/graphs stay stable.
   ========================================================================== */

const IS_LOCAL = (process.env.E2E_TARGET ?? "local") === "local";
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:4173";
const API_ORIGIN = process.env.E2E_API_ORIGIN ?? "http://localhost:8000";
const PREVIEW_PORT = 4173;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },

  // Reports land in the phase evidence directory.
  reporter: [
    ["list"],
    ["html", { outputFolder: "../artifacts/phase-22/e2e/html-report", open: "never" }],
    ["json", { outputFile: "../artifacts/phase-22/e2e/results.json" }],
  ],

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
    // Accessibility: honour reduced motion everywhere (the app degrades
    // animations via a global prefers-reduced-motion rule in index.css).
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 900 },
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],

  // Local target only: deterministically build + serve the SPA. Offline auth is
  // forced via process.env, which Vite gives highest precedence (it will not be
  // overwritten by .env.production). No secrets are injected.
  webServer: IS_LOCAL
    ? {
        command: `npm run build && npm run preview -- --port ${PREVIEW_PORT} --strictPort`,
        url: `http://localhost:${PREVIEW_PORT}`,
        reuseExistingServer: !process.env.CI,
        timeout: 240_000,
        stdout: "pipe",
        stderr: "pipe",
        env: {
          VITE_AUTH_MODE: "offline",
          VITE_API_BASE_URL: API_ORIGIN,
          VITE_API_WITH_CREDENTIALS: "false",
          VITE_DEMO_BADGE: "Synthetic Hackathon Demo",
          VITE_MAPILLARY_TOKEN: "",
        },
      }
    : undefined,
});
