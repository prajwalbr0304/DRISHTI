import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (c): Evidence metadata for a case.

   Covers        : evidence metadata table renders under the case file ·
                   no-extraction provenance note · SHA-256 / version columns.
   States        : data · empty · unauthorized (policymaker case-file block).
   Accessibility : accessible <table> with column headers.
   ========================================================================== */

test.describe("(c) Evidence metadata", () => {
  test("renders the evidence metadata table for a case", async ({ page }) => {
    await authenticate(page, "investigator");
    await page.goto("/cases/1001?tab=evidence");

    await expect(page.getByRole("heading", { name: /Evidence \(1\)/ })).toBeVisible();
    await expect(page.getByText(/File contents are not automatically extracted/i)).toBeVisible();

    await expect(page.getByRole("table")).toBeVisible();
    for (const col of ["Type", "Title", "Source", "Captured", "Ver", "Hash", "State"]) {
      await expect(page.getByRole("columnheader", { name: col, exact: true })).toBeVisible();
    }
    await expect(page.getByText("Scene photo near gate")).toBeVisible();
  });

  test("empty state when a case has no evidence", async ({ page }) => {
    await authenticate(page, "investigator");
    await overrideJson(page, pathIs("/evidence/items"), fx.evidenceListEmpty);
    await page.goto("/cases/1001?tab=evidence");

    await expect(page.getByRole("heading", { name: "No evidence recorded" })).toBeVisible();
  });

  test("unauthorized: policymaker cannot open a case file", async ({ page }) => {
    await authenticate(page, "policymaker");
    await page.goto("/cases/1001?tab=evidence");

    await expect(page.getByRole("heading", { name: "Not available for this role" })).toBeVisible();
  });
});
