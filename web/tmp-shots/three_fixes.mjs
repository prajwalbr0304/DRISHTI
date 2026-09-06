// Throwaway: verify the three requested fixes in a real browser.
import { chromium } from "@playwright/test";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.addInitScript(() => {
  localStorage.setItem("drishti.auth.offline", JSON.stringify({ demoRole: "system_admin" }));
  localStorage.setItem("drishti.role", "system_admin");
});
await page.goto("http://localhost:5173/watch", { waitUntil: "domcontentloaded", timeout: 90_000 });
await page.getByRole("heading", { name: "Live Watch Wall" }).waitFor({ timeout: 40_000 });
await page.locator('select[aria-label="District"]').selectOption("5");
await page.waitForTimeout(1200);
await page.getByRole("button", { name: /Seed camera estate/i }).click();
await page.waitForTimeout(3500);

// --- FIX 1: only the two clip cameras are watched, only they raise alerts ----
const tile = await page.getByText("Cameras watched").first()
  .locator("xpath=../..").textContent();
console.log("FIX 1  cameras tile:", (tile || "").replace(/\s+/g, " ").slice(0, 60));

const rows = () => page.locator("button").filter({ hasText: /confident/ });

// A SINGLE pass must surface both cameras — that is the demo flow.
await page.getByRole("button", { name: /Run analysis pass/i }).click();
await page.waitForTimeout(2500);
const afterOne = await rows().count();
console.log(`${afterOne === 2 ? "OK " : "!! "}   ONE analysis pass produced ${afterOne} alert(s)`);

for (let i = 0; i < 8 && (await rows().count()) < 2; i++) {
  await page.getByRole("button", { name: /Run analysis pass/i }).click();
  await page.waitForTimeout(1500);
}
const labels = (await rows().allTextContents()).map((t) => t.replace(/\s+/g, " "));
console.log(`FIX 1  queue has ${labels.length} alert(s):`);
labels.forEach((l) => console.log("         " + l.slice(0, 78)));
const onlyClipCams = labels.every((l) =>
  l.includes("MG Road Lightpost 04") || l.includes("Trinity Circle Mast 01"));
console.log(`${onlyClipCams ? "OK " : "!! "}   every alert is on a camera with footage`);

// Extra passes must NOT pile up duplicates.
for (let i = 0; i < 6; i++) {
  await page.getByRole("button", { name: /Run analysis pass/i }).click();
  await page.waitForTimeout(1200);
}
const after = await rows().count();
console.log(`${after <= 2 ? "OK " : "!! "}   after 6 more passes the queue is still ${after}`);

// --- FIX 2: selecting another alert REPLACES the feed ------------------------
const countTiles = () => page.locator("video, div").filter({
  has: page.locator("text=/No stream configured|live/"),
}).count();

async function openNth(n) {
  await rows().nth(n).click();
  await page.waitForTimeout(2800);
  return page.evaluate(() => ({
    videos: [...document.querySelectorAll("video")].map((v) =>
      (v.currentSrc || v.src).split("/").pop()),
    headers: [...document.querySelectorAll("span.text-13.font-semibold, button.text-13")]
      .map((e) => e.textContent?.trim()).filter(Boolean),
  }));
}

const total = await rows().count();
const a = await openNth(0);
console.log(`FIX 2  after opening alert #1 -> videos on screen: [${a.videos.join(", ")}]`);
let swapped = false;
if (total >= 2) {
  const b = await openNth(1);
  console.log(`FIX 2  after opening alert #2 -> videos on screen: [${b.videos.join(", ")}]`);
  swapped = b.videos.length === 1 && a.videos.length === 1 && b.videos[0] !== a.videos[0];
} else {
  console.log("FIX 2  only one alert available; cannot test the swap");
}
console.log(`${swapped ? "OK " : "!! "}   exactly one feed at a time, and it changed`);
await page.screenshot({ path: "tmp-shots/fix-feed-swap.png" });

// --- FIX 3: no synthetic boxes drawn over real footage -----------------------
const overlay = await page.evaluate(() => {
  // The overlay renders absolutely-positioned bordered divs with a label chip.
  const boxes = [...document.querySelectorAll("div.pointer-events-none.absolute.inset-0 > div")];
  return {
    boxCount: boxes.length,
    labels: boxes.map((b) => b.textContent?.trim()).slice(0, 4),
  };
});
console.log(`FIX 3  detection boxes rendered over the video: ${overlay.boxCount}`
  + (overlay.boxCount ? ` (${overlay.labels.join(", ")})` : ""));
console.log(`${overlay.boxCount === 0 ? "OK " : "!! "}   synthetic boxes suppressed`);

const noteEl = page.getByText(/Overlay off — boxes not measured/i).first();
const note = await noteEl.isVisible().catch(() => false);
if (note) {
  const box = await noteEl.boundingBox();
  const full = await noteEl.evaluate((e) => ({
    shown: e.textContent, scroll: e.scrollWidth, client: e.clientWidth,
    title: e.getAttribute("title")?.slice(0, 40),
  }));
  console.log(`       footer text fits: ${full.scroll <= full.client + 1} `
    + `(${full.scroll}px in ${full.client}px), title present: ${Boolean(full.title)}`);
}
console.log(`${note ? "OK " : "!! "}   absence is explained in the tile footer`);

// The alert card must still report the tracked count (that data is not hidden).
const tracked = await page.getByText(/tracked$/).first().textContent().catch(() => null);
console.log(`FIX 3  card still reports: ${tracked ?? "(none)"}`);

await page.screenshot({ path: "tmp-shots/fix-no-boxes.png" });
console.log("\nerrors:", errors.filter((e) => !/mapillary|favicon/i.test(e)).slice(0, 6));
await browser.close();
