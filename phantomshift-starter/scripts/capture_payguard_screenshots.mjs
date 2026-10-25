#!/usr/bin/env node
/**
 * Capture PAYGUARD UI screenshots. Requires: server on BASE_URL, playwright chromium.
 * Usage: node scripts/capture_payguard_screenshots.mjs [--base http://127.0.0.1:8767]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

// Headless Chromium on minimal hosts: extend loader path for libasound (user-local, no sudo).
const extraLib = [
  process.env.HOME + "/.local/lib",
  process.env.HOME + "/.everframe/runtimes/browser/lib",
  process.env.HOME + "/.local/lib/asound_pkg/usr/lib/x86_64-linux-gnu",
].join(":");
process.env.LD_LIBRARY_PATH = [extraLib, process.env.LD_LIBRARY_PATH].filter(Boolean).join(":");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "artifacts", "demo");
const baseArg = process.argv.find((a) => a.startsWith("--base="));
const BASE = baseArg ? baseArg.split("=")[1] : "http://127.0.0.1:8767";

const shots = [
  { name: "blacksite-1440x900-control", width: 1440, height: 900, path: "/payguard/", wait: 4500 },
  { name: "blacksite-1280x800-control", width: 1280, height: 800, path: "/payguard/", wait: 3500 },
  { name: "blacksite-768x1024-tablet", width: 768, height: 1024, path: "/payguard/", wait: 3500 },
  { name: "blacksite-390x844-mobile", width: 390, height: 844, path: "/payguard/", wait: 3000 },
  { name: "blacksite-1440-policy-lab", width: 1440, height: 900, path: "/payguard/", wait: 2000, tab: "Policy lab" },
  { name: "blacksite-disconnected", width: 1440, height: 900, path: "/payguard/", wait: 1500, disconnect: true },
];

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ colorScheme: "dark" });
  const page = await context.newPage();

  for (const s of shots) {
    await page.setViewportSize({ width: s.width, height: s.height });
    await page.goto(BASE + s.path, { waitUntil: "networkidle", timeout: 120_000 });
    if (s.tab) {
      await page.getByRole("button", { name: new RegExp(s.tab, "i") }).click({ timeout: 8000 }).catch(() => {});
      await page.waitForTimeout(600);
    }
    if (s.disconnect) {
      await page.getByText(/simulate disconnect/i).click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(800);
    }
    await page.waitForTimeout(s.wait);
    const file = path.join(OUT, `${s.name}.png`);
    await page.screenshot({ path: file, fullPage: s.height > 800 });
    console.log("wrote", file);
  }

  const approval = await page.locator('[data-testid="approval-json"]').textContent().catch(() => "");
  await writeFile(
    path.join(OUT, "payguard-capture-meta.json"),
    JSON.stringify({ base: BASE, captured_at: new Date().toISOString(), approval_snippet: approval?.slice(0, 200) }, null, 2),
  );
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
