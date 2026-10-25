// Screenshots for review: node scripts/shoot.mjs [baseUrl] [outDir] [--live]
// Needs Playwright; NODE_PATH can point at any node_modules that has it.
import { createRequire } from "node:module";
// Resolve Playwright from this package or from NODE_PATH (ESM imports ignore NODE_PATH).
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); } catch {
  const paths = (process.env.NODE_PATH ?? "").split(":").filter(Boolean);
  pw = require(require.resolve("playwright", { paths }));
}
const { chromium } = pw;
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://localhost:5180";
const out = process.argv[3] ?? "screenshots";
const live = process.argv.includes("--live");
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
page.on("console", (m) => { if (m.type() === "error") console.log("console:", m.text()); });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
const wait = (ms) => page.waitForTimeout(ms);
const shot = async (name, full = false) => {
  await wait(500);
  await page.screenshot({ path: `${out}/${name}.png` });
  if (full) {
    // the case view scrolls inside its column: capture it whole too
    const h = await page.evaluate(() => {
      const el = document.querySelector(".case-scroll");
      return el ? el.scrollHeight + 56 + 90 + 80 : 1000;
    });
    await page.setViewportSize({ width: 1600, height: Math.max(1000, Math.min(h, 3200)) });
    await wait(300);
    await page.screenshot({ path: `${out}/${name}-full.png` });
    await page.setViewportSize({ width: 1600, height: 1000 });
  }
  console.log("saved", name);
};
const pick = async (id) => { await page.locator(".qrow", { hasText: id }).first().click(); await wait(400); };

const q = live ? "" : "?mock=1";
if (!live) {
  await page.goto(`${base}/?mock=empty`); await wait(800);
  await shot("01-empty");
}
await page.goto(`${base}/${q}`); await wait(1200);
for (const [id, name] of [["HOLD-0001", "02-scenario1-lookalike"], ["HOLD-0002", "03-scenario2-hacked-real"], ["HOLD-0003", "04-scenario3-copied-invoice"], ["HOLD-0004", "05-surprise-confirm"]]) {
  await pick(id);
  await shot(name, true);
}
if (live && !process.argv.includes("--act")) { await browser.close(); process.exit(0); }
// reject path: scenario 1, vendor says it's fake
await pick("HOLD-0001");
await page.getByRole("button", { name: /confirmed it's fake/i }).click(); await wait(800);
await shot("06-after-reject", true);
// approve path: surprise invoice, requester confirms, manager approves
await pick("HOLD-0004");
await page.getByRole("button", { name: /confirmed the order/i }).click(); await wait(800);
await shot("07-ready-for-approval");
await page.getByRole("button", { name: /Approve release/i }).click(); await wait(800);
await shot("08-after-approve", true);
await page.getByRole("button", { name: /Demo controls/i }).click(); await wait(300);
await shot("09-demo-menu");
if (live && process.argv.includes("--cycle")) {
  // Reset through the UI, then send every scenario email again with N, as in the video.
  await page.getByRole("menuitem", { name: /Reset demo/i }).click(); await wait(1500);
  await shot("10-live-empty-after-reset");
  await page.keyboard.press("n"); await wait(700);
  await shot("11-live-ingesting");
  await wait(2500);
  await shot("12-live-new-case-arrived");
  for (let i = 0; i < 4; i++) { await page.keyboard.press("n"); await wait(3500); }
  await shot("13-live-all-scenarios-sent");
}
await browser.close();
