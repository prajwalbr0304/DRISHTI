import { test, expect } from "@playwright/test";
import { DEMO_BADGE, ROLE_HOME, VIEWPORT, isLocal, signInViaLoginPage } from "./support/app";
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

    for (const label of [
      "Investigator",
      "Crime Analyst",
      "Supervisor",
      "Policymaker",
      "Disaster Coordinator",
      "Super Admin",
    ]) {
      await expect(page.getByRole("button", { name: new RegExp(label) })).toBeVisible();
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

    const investigator = page.getByRole("button", { name: /Investigator/ });

    // Tab through the page until the first role option actually holds focus.
    let focused = false;
    for (let i = 0; i < 20 && !focused; i++) {
      await page.keyboard.press("Tab");
      focused = await investigator.evaluate((el) => el === document.activeElement);
    }
    await expect(investigator).toBeFocused();

    // Visible focus affordance: the app applies a :focus-visible outline ring.
    const focus = await investigator.evaluate((el) => {
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
    await page.waitForURL(new RegExp(`${ROLE_HOME.investigator.replace(/\//g, "\\/")}(\\?|$)`));
  });

  test("signs in (offline) and switches the demo view from the profile menu", async ({ page }) => {
    await signInViaLoginPage(page, "investigator");

    await expect(page.getByText(DEMO_BADGE, { exact: false }).first()).toBeVisible();
    const profile = page.getByRole("button", { name: "Profile and role" });
    await expect(profile).toBeVisible();
    await expect(profile).toContainText("Investigator");

    await profile.click();
    await page.getByRole("menuitemradio", { name: /Supervisor/ }).click();
    await expect(profile).toContainText("Supervisor");
  });

  test("a11y: the shell exposes labeled landmarks and controls", async ({ page }) => {
    await signInViaLoginPage(page, "investigator");

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
    await expect(page.getByRole("button", { name: /Investigator/ })).toBeVisible();
  });
});
