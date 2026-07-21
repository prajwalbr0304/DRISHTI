import type { Page } from "@playwright/test";
import { installLocalStubs } from "./stub";

/* ============================================================================
   Shared app harness helpers.

   The journey specs are IDENTICAL across the two targets — only these helpers
   branch on E2E_TARGET:
     - "local" (default): install deterministic route stubs and sign in with a
       synthetic offline identity (VITE_AUTH_MODE=offline, seeded into
       localStorage before the app boots).
     - "live" (Prompt 23): no stubbing; the real Catalyst session is expected to
       be provided out-of-band (e.g. Playwright storageState). `authenticate`
       becomes a no-op so the same navigation + assertions run unchanged.
   ========================================================================== */

export type Role =
  | "investigator"
  | "analyst"
  | "supervisor"
  | "policymaker"
  | "disaster_coordinator"
  | "super_admin";

/** Home route each role lands on after sign-in (mirrors config/roles.ts). */
export const ROLE_HOME: Record<Role, string> = {
  investigator: "/cases",
  analyst: "/command",
  supervisor: "/command",
  policymaker: "/analytics",
  disaster_coordinator: "/er",
  super_admin: "/command",
};

/** Login-page RolePicker button label per role (config/roles.ts labels). */
export const ROLE_LABEL: Record<Role, string> = {
  investigator: "Investigator",
  analyst: "Crime Analyst",
  supervisor: "Supervisor",
  policymaker: "Policymaker",
  disaster_coordinator: "Disaster Coordinator",
  super_admin: "Super Admin",
};

export const VIEWPORT = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
} as const;

export function isLocal(): boolean {
  return (process.env.E2E_TARGET ?? "local") === "local";
}

/**
 * Seed a synthetic offline identity into localStorage BEFORE any app script
 * runs, so the shell boots already authenticated as `role`. Mirrors
 * src/auth/offline.ts (drishti.auth.offline) + RoleProvider (drishti.role).
 */
async function seedOfflineSession(page: Page, role: Role): Promise<void> {
  await page.addInitScript((r: string) => {
    try {
      window.localStorage.setItem("drishti.auth.offline", JSON.stringify({ demoRole: r }));
      window.localStorage.setItem("drishti.role", r);
    } catch {
      /* storage unavailable — ignore */
    }
  }, role);
}

/**
 * Prepare an authenticated context for `role`. In local mode this installs the
 * deterministic backend and seeds the offline session; in live mode it assumes
 * a real session is already present (storageState) and only returns.
 *
 * Call this FIRST in a test; register any per-spec state overrides AFTER it so
 * they take precedence, then navigate.
 */
export async function authenticate(page: Page, role: Role): Promise<void> {
  if (isLocal()) {
    await installLocalStubs(page);
    await seedOfflineSession(page, role);
  }
  // live: no-op — the journey navigates against the real, already-authenticated app.
}

/**
 * Local-only: drive the real offline login page (synthetic-identity picker).
 * Used by the login/role journey to exercise the actual sign-in flow rather
 * than pre-seeding. Installs stubs so the post-login landing page is
 * deterministic.
 */
export async function signInViaLoginPage(page: Page, role: Role): Promise<void> {
  await installLocalStubs(page);
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(ROLE_LABEL[role]) }).click();
  await page.waitForURL(new RegExp(`${ROLE_HOME[role].replace(/\//g, "\\/")}(\\?|$|\\/)`));
}

/** The persistent synthetic-demo badge text (runtime.demoBadge / intake status). */
export const DEMO_BADGE = "Synthetic Hackathon Demo";
