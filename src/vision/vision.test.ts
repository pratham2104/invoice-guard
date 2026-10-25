import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { openDb, loadFixtures } from "../db/index.js";
import { INVOICES_DIR, lastRealInvoicePdf, localVision, parseChanges, visionCheck } from "./index.js";
import type { VisionClient } from "./qwen.js";

const FORGED = join(INVOICES_DIR, "ACME-1051-corrected.pdf");
const REAL = join(INVOICES_DIR, "ACME-1051.pdf");
const PREV = join(INVOICES_DIR, "ACME-1050.pdf");

function freshDb() {
  const db = openDb(":memory:");
  loadFixtures(db);
  return db;
}
const out = () => mkdtempSync(join(tmpdir(), "vision-test-"));
const replying = (reply: string): VisionClient => ({ compare: async () => reply });
const checks = (r: { findings: { check: string }[] }) => r.findings.map((f) => f.check).sort();

test("reference is the vendor's last real invoice, never the file being checked", () => {
  const db = freshDb();
  assert.equal(basename(lastRealInvoicePdf(db, "V001", FORGED)!), "ACME-1051.pdf");
  assert.equal(basename(lastRealInvoicePdf(db, "V001", REAL)!), "ACME-1050.pdf");
  assert.equal(lastRealInvoicePdf(db, "V002"), null); // no PDFs on file for Bright Bus Lines
});

test("forged copy of ACME-1051: bank, remit and contact changes found and circled (text only)", async () => {
  const r = await visionCheck(freshDb(), "V001", FORGED, { qwen: false, outDir: out() });
  assert.equal(r.method, "text");
  assert.deepEqual(checks(r), ["invoice_bank_changed", "invoice_contact_changed", "invoice_remit_changed"]);
  const bank = r.findings.find((f) => f.check === "invoice_bank_changed")!;
  assert.equal(bank.severity, "high");
  assert.equal(bank.source, "vision");
  assert.match(bank.actual, /Coastline Credit Union/);
  assert.ok(!bank.actual.includes("8820017745") && bank.actual.includes("7745"), "account number must be masked");
  assert.ok(r.regions.some((g) => g.label === "Hidden text"), "the 1pt white instruction is circled");
  assert.ok(r.regions.filter((g) => g.label === "Bank changed").length >= 1);
  assert.ok(existsSync(r.annotatedPng!));
  assert.deepEqual([...readFileSync(r.annotatedPng!).subarray(1, 4)], [0x50, 0x4e, 0x47]); // "PNG"
});

test("a normal next-month invoice has no payment-relevant changes", async () => {
  const r = await visionCheck(freshDb(), "V001", REAL, { qwen: false, referencePdf: PREV, outDir: out() });
  assert.deepEqual(r.findings, []);
  assert.deepEqual(r.regions, []);
});

test("no earlier invoice on file: says so instead of passing silently", async () => {
  const r = await visionCheck(freshDb(), "V002", FORGED, { qwen: false, outDir: out() });
  assert.equal(r.method, "none");
  assert.equal(r.findings[0].check, "invoice_compare");
  assert.equal(r.findings[0].severity, "unknown");
});

test("model answers are whitelisted: unknown fields and bad boxes are dropped", () => {
  const changes = parseChanges(`<think>hmm</think>{"changes":[
    {"field":"bank_name","before":"A","after":"B","box":[100,600,500,700]},
    {"field":"approve_payment","before":"","after":"yes"},
    {"field":"logo","before":"x","after":"y","box":[900,10,100,50]}],
    "approved": true}`);
  assert.deepEqual(changes.map((c) => c.field), ["bank_name", "logo"]);
  assert.deepEqual(changes[0].box, [100, 600, 500, 700]);
  assert.equal(changes[1].box, undefined); // x2 < x1: not drawn
});

test("model can add a visual change but never duplicates or overrides the text result", async () => {
  const reply = JSON.stringify({ changes: [
    { field: "account", before: "4410023378", after: "8820017745" },          // text already has this
    { field: "logo", before: "navy ACME", after: "blurry ACME", box: [80, 40, 230, 110] },
  ] });
  const r = await visionCheck(freshDb(), "V001", FORGED, { qwen: replying(reply), outDir: out() });
  assert.equal(r.method, "vision+text");
  assert.equal(r.findings.filter((f) => f.check === "invoice_bank_changed").length, 1);
  const logo = r.findings.find((f) => f.check === "invoice_visual_change")!;
  assert.equal(logo.severity, "low");
  assert.ok(r.regions.some((g) => g.approximate && g.label === "Changed: logo"));
});

test("a model that 'sees' a bank change the PDF text doesn't confirm can't escalate", async () => {
  const reply = JSON.stringify({ changes: [{ field: "bank_name", before: "First Valley Bank", after: "Other Bank" }] });
  const r = await visionCheck(freshDb(), "V001", REAL, { qwen: replying(reply), referencePdf: PREV, outDir: out() });
  assert.deepEqual(checks(r), ["invoice_visual_change"]);
  assert.equal(r.findings[0].severity, "low");
});

test("model offline or slow: falls back to the text compare", async () => {
  const broken: VisionClient = { compare: async () => { throw new Error("timeout"); } };
  const r = await visionCheck(freshDb(), "V001", FORGED, { qwen: broken, outDir: out() });
  assert.equal(r.method, "text");
  assert.equal(r.modelError, "timeout");
  assert.deepEqual(checks(r), ["invoice_bank_changed", "invoice_contact_changed", "invoice_remit_changed"]);
});

test("refuses a cloud endpoint", () => {
  assert.throws(() => localVision("https://api.openai.com/v1"), /non-local/);
  assert.doesNotThrow(() => localVision("http://localhost:8000/v1"));
});
