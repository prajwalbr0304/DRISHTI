import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (g): Emergency Response — Situation Overview.

   Covers        : ER dashboard loads · readiness KPI tiles · active hazard and
                   alert content.
   States        : data · empty (nothing seeded) · stale (a stale data feed is
                   surfaced) · read-only for a crime role.
   ========================================================================== */

test.describe("(g) Emergency Response", () => {
  test("renders the situation overview with readiness KPIs and a stale-feed signal", async ({ page }) => {
    await authenticate(page, "disaster_coordinator");
    await page.goto("/er");

    await expect(page.getByRole("heading", { name: "Situation Overview" })).toBeVisible();

    for (const kpi of [
      "Active hazards",
      "Open alerts",
      "Low-confidence",
      "Stale feeds",
      "Available resources",
      "Open tasks",
    ]) {
      await expect(page.getByText(kpi, { exact: false }).first()).toBeVisible();
    }

    // Stale-state coverage: the freshness banner surfaces the stale feed.
    await expect(page.getByText("Data freshness")).toBeVisible();
    await expect(page.getByText("stale").first()).toBeVisible();

    // Active hazard + alert content.
    await expect(page.getByText(/Flood warning . Bengaluru Urban/)).toBeVisible();
  });

  test("empty state when nothing is seeded", async ({ page }) => {
    await authenticate(page, "disaster_coordinator");
    await overrideJson(page, pathIs("/disaster/overview"), fx.disasterOverviewEmpty);
    await overrideJson(page, pathIs("/disaster/alerts"), { alerts: [] });
    await page.goto("/er");

    await expect(page.getByText("No Emergency Response data yet.")).toBeVisible();
  });

  test("reads are open to a crime role (read-only view)", async ({ page }) => {
    await authenticate(page, "analyst");
    await page.goto("/er");

    await expect(page.getByRole("heading", { name: "Situation Overview" })).toBeVisible();
    // A crime role does not get the coordinator's write actions.
    await expect(page.getByRole("button", { name: /Seed demo scenario/ })).toHaveCount(0);
  });
});
