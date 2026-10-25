// v2 screenshots: node scripts/shoot-v2.mjs [baseUrl] [outDir]   (NODE_PATH may point at a node_modules with Playwright)
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); } catch {
  pw = require(require.resolve("playwright", { paths: (process.env.NODE_PATH ?? "").split(":").filter(Boolean) }));
}
const base = process.argv[2] ?? "http://localhost:5180";
const out = process.argv[3] ?? "screenshots/v2";
mkdirSync(out, { recursive: true });
const browser = await pw.chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
const wait = (ms) => page.waitForTimeout(ms);
const shot = async (name, full = true) => {
  await wait(450);
  await page.screenshot({ path: `${out}/${name}.png` });
  if (full) {
    const h = await page.evaluate(() => (document.querySelector(".main")?.scrollHeight ?? 900) + 64);
    await page.setViewportSize({ width: 1600, height: Math.max(1000, Math.min(h, 3600)) });
    await wait(250);
    await page.screenshot({ path: `${out}/${name}-full.png` });
    await page.setViewportSize({ width: 1600, height: 1000 });
  }
  console.log("saved", name);
};
const pick = async (text) => { await page.locator(".srow", { hasText: text }).first().click(); await wait(350); };

await page.goto(`${base}/`); await wait(900);
await pick("Bright Bus Lines"); await shot("01-near-copy-address");
await pick("Greenfield Food Service"); await shot("02-hacked-real-account");
await pick("TechNest IT Services"); await shot("03-forged-invoice");
await pick("LabWorks Science Supply"); await shot("04-unexpected-bill");
await page.locator(".side-sec", { hasText: "Cleared" }).locator(".srow").nth(1).click(); await wait(350);
await shot("05-cleared-invoice");
if (process.argv.includes("--flows")) {
  await pick("Bright Bus Lines");
  await page.getByRole("button", { name: /says it's fake/i }).click(); await wait(600);
  await shot("06-after-reject", false);
  await pick("LabWorks Science Supply");
  await page.getByRole("button", { name: /confirmed$/i }).click(); await wait(600);
  await shot("07-ready", false);
  await page.getByRole("button", { name: /^Approve$/ }).click(); await wait(600);
  await shot("08-after-approve", false);
}
await browser.close();
