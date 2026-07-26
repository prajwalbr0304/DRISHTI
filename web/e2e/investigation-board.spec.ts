import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (f): Investigation Board.

   Covers        : board list · open the board workspace · canvas loads
                   (react-flow) with named toolbar controls + tabs.
   States        : data · empty · cross-role access (all seats allowed).
   Notes         : no pixel snapshot of the dynamic canvas — assertions are on
                   roles/text/structure (title, tabs, "Fit view" control).
   ========================================================================== */

test.describe("(f) Investigation Board", () => {
  test("lists boards and opens the board workspace canvas", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await page.goto("/board");

    await expect(page.getByRole("heading", { name: "Investigation Board" })).toBeVisible();
    await expect(page.getByText("Operation Nightingale").first()).toBeVisible();

    await page.getByText("Operation Nightingale").first().click();
    await page.waitForURL(/\/board\/1/);

    // Workspace: title heading + canvas tabs + react-flow toolbar control.
    await expect(page.getByRole("heading", { name: "Operation Nightingale" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Canvas" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Evidence Trail" })).toBeVisible();
    // The react-flow canvas toolbar loaded (a custom control unique to it).
    await expect(page.getByRole("button", { name: "Radial tidy" })).toBeVisible();
  });

  test("empty state when there are no boards", async ({ page }) => {
    await authenticate(page, "investigating_officer");
    await overrideJson(page, pathIs("/boards"), fx.boardListEmpty);
    await page.goto("/board");

    await expect(page.getByRole("heading", { name: "No boards yet" })).toBeVisible();
  });

  // Interim access model: every command seat holds board_use, so the board is
  // reachable from a state-command seat instead of redirecting to /analytics.
  test("authorized: a state-command seat reaches the board", async ({ page }) => {
    await authenticate(page, "dgp_state_command");
    await page.goto("/board");

    await expect(page.getByRole("heading", { name: "Investigation Board" })).toBeVisible();
  });
});
