import { test, expect } from "@playwright/test";
import { VIEWPORT, authenticate } from "./support/app";
import { overrideError, overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (e): Case investigation.

   Covers        : case explorer lists cases · open a case file · sub-nav tabs
                   render.
   States        : data · empty · error · cross-role access (all seats allowed).
   Responsive    : mobile 390x844 (case list) + desktop 1440x900 (default).
   ========================================================================== */

test.describe("(e) Case investigation", () => {
  test("lists cases and opens a case file with its sub-navigation", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await page.goto("/cases");

    await expect(page.getByRole("heading", { name: "Case Explorer" })).toBeVisible();
    await expect(page.getByText("2 cases")).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();

    await page.getByText("CR-1001/2026").first().click();
    await page.waitForURL(/\/cases\/1001/);

    await expect(page.getByRole("heading", { name: "CR-1001/2026" })).toBeVisible();
    for (const tab of ["Overview", "Timeline", "Evidence", "Network", "AI Summary"]) {
      await expect(page.getByRole("button", { name: tab, exact: true })).toBeVisible();
    }
  });

  test("empty state when no cases match", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await overrideJson(page, pathIs("/cases"), fx.caseListEmpty);
    await page.goto("/cases");

    await expect(page.getByText("No cases match these filters.")).toBeVisible();
  });

  test("error state when the case list fails", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await overrideError(page, pathIs("/cases"), 500);
    await page.goto("/cases");

    await expect(page.getByRole("heading", { name: "Couldn't load cases" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  // Interim access model: every command seat holds case_read, so a state-command
  // seat browses cases too (the server still enforces the real decision).
  test("authorized: a state-command seat can browse individual cases", async ({ page }) => {
    await authenticate(page, "dgp_state_command");
    await page.goto("/cases");

    await expect(page.getByRole("heading", { name: "Case Explorer" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Not available for this role" })).toBeHidden();
  });

  test("responsive: the case list renders on a mobile viewport", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await page.setViewportSize(VIEWPORT.mobile);
    await page.goto("/cases");

    await expect(page.getByRole("heading", { name: "Case Explorer" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
  });
});
