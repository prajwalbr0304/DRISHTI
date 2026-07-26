import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideError, overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (b): FIR intake inbox + New FIR action.

   Covers        : intake inbox lists drafts · "New FIR" starts a draft flow.
   States        : data · empty · error · cross-role access (all seats allowed).
   Accessibility : accessible <table> with column headers · named actions.
   ========================================================================== */

test.describe("(b) FIR intake", () => {
  test("lists intake drafts and exposes the New FIR action", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await page.goto("/intake");

    await expect(page.getByRole("heading", { name: "Intake inbox" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Draft" })).toBeVisible();
    await expect(page.getByRole("button", { name: "SYN-DRAFT-0001" })).toBeVisible();
    await expect(page.getByRole("button", { name: /New FIR/ }).first()).toBeVisible();
  });

  test("New FIR starts a fresh draft flow", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await page.goto("/intake");

    await page.getByRole("button", { name: /New FIR/ }).first().click();
    // NewFir creates a draft then redirects into the wizard route.
    await page.waitForURL(/\/intake\/fir\//);
  });

  test("empty state when there are no drafts", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await overrideJson(page, pathIs("/intake/drafts"), fx.intakeDraftsEmpty);
    await page.goto("/intake");

    await expect(page.getByRole("heading", { name: "No drafts yet" })).toBeVisible();
    await expect(page.getByRole("button", { name: /New FIR/ }).first()).toBeVisible();
  });

  test("error state when the drafts request fails", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await overrideError(page, pathIs("/intake/drafts"), 500);
    await page.goto("/intake");

    await expect(page.getByRole("heading", { name: "Couldn't load drafts" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  // Interim access model: every command seat holds intake_write/intake_review.
  test("authorized: a state-command seat can open the intake inbox", async ({ page }) => {
    await authenticate(page, "dgp_state_command");
    await page.goto("/intake");

    await expect(page.getByRole("heading", { name: "Intake inbox" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Not available for this role" })).toBeHidden();
  });
});
