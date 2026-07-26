import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (g): Emergency Response — Situation Overview.

   Covers        : ER dashboard loads · readiness KPI tiles · active hazard and
                   alert content.
   States        : data · empty (nothing seeded) · stale (a stale data feed is
                   surfaced) · cross-role access (all seats allowed).
   ========================================================================== */

test.describe("(g) Emergency Response", () => {
  test("renders the situation overview with readiness KPIs and a stale-feed signal", async ({ page }) => {
    await authenticate(page, "dysp_acp");
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
    await authenticate(page, "dysp_acp");
    await overrideJson(page, pathIs("/disaster/overview"), fx.disasterOverviewEmpty);
    await overrideJson(page, pathIs("/disaster/alerts"), { alerts: [] });
    await page.goto("/er");

    await expect(page.getByText("No Emergency Response data yet.")).toBeVisible();
  });

  // Interim access model: every command seat holds disaster_write, so a crime
  // staff seat reaches the same situational view (server-enforced regardless).
  test("the situational view is open to a crime staff seat", async ({ page }) => {
    await authenticate(page, "crime_analyst");
    await page.goto("/er");

    await expect(page.getByRole("heading", { name: "Situation Overview" })).toBeVisible();
  });
});
