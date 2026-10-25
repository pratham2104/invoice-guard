// Try the vision check by hand:
//   npm run vision -- data/invoices/ACME-1051-corrected.pdf            (text + Qwen, vendor V001)
//   npm run vision -- data/invoices/ACME-1051-corrected.pdf --no-llm   (text compare only)
//   npm run vision -- new.pdf --vendor V002 --ref old.pdf --out ./tmp
import { openDb, loadFixtures } from "../db/index.js";
import { visionCheck } from "./index.js";

const args = process.argv.slice(2);
const flag = (name: string) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const pdf = args.find((a) => a.endsWith(".pdf") && a !== flag("--ref"));
if (!pdf) {
  console.error("usage: npm run vision -- <new-invoice.pdf> [--vendor V001] [--ref last-real.pdf] [--no-llm] [--out dir]");
  process.exit(2);
}

const db = openDb(":memory:");
loadFixtures(db);
const r = await visionCheck(db, flag("--vendor") ?? "V001", pdf, {
  qwen: args.includes("--no-llm") ? false : undefined, referencePdf: flag("--ref"), outDir: flag("--out"),
});

console.log(`compared ${pdf}\n    with ${r.referencePdf ?? "(nothing on file)"}   method=${r.method}` +
            (r.modelMs !== undefined ? `  model=${r.modelMs}ms` : "") + (r.modelError ? `  (model: ${r.modelError})` : ""));
for (const f of r.findings) console.log(`  [${f.severity.toUpperCase()}] ${f.check}: ${f.explanation}\n      was: ${f.expected}\n      now: ${f.actual}`);
if (!r.findings.length) console.log("  no payment-relevant changes");
console.log(`circled: ${r.annotatedPng}`);
