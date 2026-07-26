import { test, expect } from "@playwright/test";
import {
  DEMO_BADGE, ROLE_HOME, ROLE_IDS, ROLE_LABEL, VIEWPORT, escapeRe, isLocal,
  signInViaLoginPage,
} from "./support/app";
import { installLocalStubs } from "./support/stub";

/* ============================================================================
   Journey (a): Login & role context.

   Covers        : login page render · synthetic-demo badge · offline role
                   selection · in-app role switch.
   States        : unauthorized (protected route → /login redirect).
   Responsive    : mobile 390x844 (this file) + desktop 1440x900 (default).
   Accessibility : keyboard reach + visible focus ring + Enter activation ·
                   labeled shell landmarks/controls · role="navigation".

   The offline synthetic-identity picker is a LOCAL-target mechanic (the live
   Catalyst sign-in is Prompt 23), so this journey is guarded to local.
   ========================================================================== */

test.describe("(a) Login & role context", () => {
  test.skip(!isLocal(), "Offline login picker is local-only; live Catalyst login is Prompt 23.");

  test("login page renders with the synthetic-demo badge and every role option", async ({ page }) => {
    await installLocalStubs(page);
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: /Choose your operational view/i })).toBeVisible();
    await expect(page.getByText(DEMO_BADGE, { exact: false }).first()).toBeVisible();
    await expect(page.getByText(/Synthetic data only/i)).toBeVisible();

    // Every command seat is offered, each with its synthetic demo officer.
    for (const role of ROLE_IDS) {
      await expect(
        page.getByRole("button", { name: new RegExp(escapeRe(ROLE_LABEL[role])) }).first(),
      ).toBeVisible();
    }
  });

  test("unauthorized: a protected route redirects to /login", async ({ page }) => {
    await installLocalStubs(page); // no offline session seeded → unauthenticated
    await page.goto("/cases");
    await page.waitForURL(/\/login$/);
    await expect(page.getByRole("heading", { name: /Choose your operational view/i })).toBeVisible();
  });

  test("a11y: a role option is keyboard-reachable, shows a visible focus ring, and activates", async ({ page }) => {
    await installLocalStubs(page);
    await page.goto("/login");

    const firstRole = ROLE_IDS[0];
    const option = page
      .getByRole("button", { name: new RegExp(escapeRe(ROLE_LABEL[firstRole])) })
      .first();

    // Tab through the page until the first role option actually holds focus.
    let focused = false;
    for (let i = 0; i < 20 && !focused; i++) {
      await page.keyboard.press("Tab");
      focused = await option.evaluate((el) => el === document.activeElement);
    }
    await expect(option).toBeFocused();

    // Visible focus affordance: the app applies a :focus-visible outline ring.
    const focus = await option.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        focusVisible: el.matches(":focus-visible"),
        outlineStyle: s.outlineStyle,
        outlineWidth: s.outlineWidth,
        boxShadow: s.boxShadow,
      };
    });
    const visibleFocus =
      focus.focusVisible ||
      (focus.outlineStyle !== "none" && focus.outlineWidth !== "0px") ||
      focus.boxShadow !== "none";
    expect(visibleFocus).toBeTruthy();

    // Enter activates the focused role and lands on its home.
    await page.keyboard.press("Enter");
    await page.waitForURL(new RegExp(`${ROLE_HOME[firstRole].replace(/\//g, "\\/")}(\\?|$)`));
  });

  test("signs in (offline) and switches the demo view from the profile menu", async ({ page }) => {
    await signInViaLoginPage(page, "investigating_officer");

    await expect(page.getByText(DEMO_BADGE, { exact: false }).first()).toBeVisible();
    const profile = page.getByRole("button", { name: "Profile and role" });
    await expect(profile).toBeVisible();
    await expect(profile).toContainText(ROLE_LABEL.investigating_officer);

    await profile.click();
    await page.getByRole("menuitemradio", { name: new RegExp(escapeRe(ROLE_LABEL.cyber_cell)) }).click();
    await expect(profile).toContainText(ROLE_LABEL.cyber_cell);
  });

  test("a11y: the shell exposes labeled landmarks and controls", async ({ page }) => {
    await signInViaLoginPage(page, "investigating_officer");

    await expect(page.getByRole("navigation").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Profile and role" })).toBeVisible();
    await expect(page.getByRole("button", { name: /open command palette/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Alerts \(/ })).toBeVisible();
  });

  test("responsive: login renders on a mobile viewport", async ({ page }) => {
    await page.setViewportSize(VIEWPORT.mobile);
    await installLocalStubs(page);
    await page.goto("/login");

    await expect(page.getByRole("heading", { name: /Choose your operational view/i })).toBeVisible();
    await expect(
      page.getByRole("button", { name: new RegExp(escapeRe(ROLE_LABEL[ROLE_IDS[0]])) }).first(),
    ).toBeVisible();
  });
});
