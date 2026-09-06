// Temporary visual-verification harness for the landing page rebuild.
// Screenshots each section by aligning its top edge under the fixed header,
// so framing does not depend on guessed scroll offsets. Delete after review.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.SHOT_BASE ?? "http://localhost:5199";
const OUT = new URL("./out/", import.meta.url).pathname.replace(/^\//, "");
mkdirSync(OUT, { recursive: true });

const SECTIONS = [
  ["01-hero", ".lp-hero"],
  ["02-pillars", ".lp-pillars"],
  ["03-platform", ".lp-platform"],
  ["04-showcase-intro", ".lp-showcase-intro"],
  ["05-panel-command", "#command"],
  ["06-panel-geospatial", "#geospatial"],
  ["07-panel-casework", "#casework"],
  ["08-panel-ask", "#ask"],
  ["09-panel-forecasting", "#forecasting"],
  ["10-panel-response", "#response"],
  ["11-product", ".lp-product"],
  ["12-audience", ".lp-audience"],
  ["13-scale", ".lp-scale"],
  ["14-governance", ".lp-governance"],
  ["15-mission", ".lp-mission"],
  ["16-final", ".lp-final"],
  ["17-footer", ".lp-footer"],
];

const browser = await chromium.launch();

async function open(width, height) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(BASE + "/", { waitUntil: "networkidle" });
  // Walk the page once so every [data-reveal] and every lazy film has fired.
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.6;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 90));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(900);
  return page;
}

async function shootSections(page, prefix) {
  for (const [name, selector] of SECTIONS) {
    const target = page.locator(selector).first();
    if ((await target.count()) === 0) {
      console.warn("MISSING", selector);
      continue;
    }
    await target.evaluate((element) => {
      const top = element.getBoundingClientRect().top + window.scrollY;
      window.scrollTo(0, Math.max(0, top));
    });
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${OUT}${prefix}${name}.png` });
  }
}

const desktop = await open(1440, 900);
await shootSections(desktop, "d-");
await desktop.close();

const mobile = await open(414, 860);
await shootSections(mobile, "m-");
await mobile.close();

// Full-page reference at a narrow scale so overall rhythm is reviewable.
const full = await open(1280, 900);
await full.screenshot({ path: `${OUT}z-fullpage.png`, fullPage: true });
await full.close();

await browser.close();
console.log("shots written to", OUT);
