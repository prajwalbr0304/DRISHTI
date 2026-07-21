import { test, expect } from "@playwright/test";
import { authenticate } from "./support/app";
import { overrideDelayedJson, pathIs } from "./support/stub";
import * as fx from "./fixtures";

/* ============================================================================
   Journey (d): Ask DRISHTI — grounded, cited answer + typed visualization.

   Covers        : welcome/empty state · submit a question · grounded reply with
                   inline citations, confidence, read-only SQL · a typed
                   `number` visualization renders (deterministically, never by
                   executing model output) · the accessible-table fallback.
   States        : loading (thinking bubble) · data.
   Accessibility : Enter submits from the composer · role=table fallback under
                   the chart.
   ========================================================================== */

test.describe("(d) Ask DRISHTI", () => {
  test("submits a question and renders a grounded, cited answer with a typed visualization", async ({ page }) => {
    await authenticate(page, "analyst");
    // Delay the answer so the loading (thinking) state is observable.
    await overrideDelayedJson(page, pathIs("/chat/ask"), fx.askGrounded, 600);
    await page.goto("/ask");

    // Welcome / empty state (the composer intro heading is an <h2>).
    await expect(page.getByRole("heading", { name: "Ask DRISHTI", level: 2 })).toBeVisible();

    const box = page.getByRole("textbox");
    await box.click();
    await box.fill("how many cyber crime FIRs in Bengaluru City this year");
    await page.getByRole("button", { name: /^Send$/ }).click();

    // Loading: the thinking bubble is announced.
    await expect(page.locator('[aria-label="Thinking"]')).toBeVisible();

    // Grounded, cited answer.
    await expect(page.getByText(/42 cyber-crime FIRs/i)).toBeVisible();
    await expect(page.getByText(/Sources:/i).first()).toBeVisible();
    await expect(page.getByText(/82%/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /SQL executed/i })).toBeVisible();

    // Typed visualization (number) rendered from the server-declared spec.
    // (exact: the sr-only accessible-table <caption> also contains this title.)
    await expect(page.getByText("Total FIRs", { exact: true })).toBeVisible();

    // Accessible-table fallback is always present under the chart.
    await page.getByText("Show data table").click();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("cell", { name: "42", exact: true })).toBeVisible();
  });

  test("a11y: Enter submits from the composer", async ({ page }) => {
    await authenticate(page, "analyst");
    await page.goto("/ask");

    const box = page.getByRole("textbox");
    await box.click();
    await box.fill("thefts in Mysuru this quarter");
    await box.press("Enter");

    await expect(page.getByText(/42 cyber-crime FIRs/i)).toBeVisible();
  });
});
