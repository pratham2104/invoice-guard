// Invoice vision check (T06): compare a new invoice PDF with the vendor's last real invoice and circle
// what changed. Returns Findings (source "vision") for the rules engine; it never decides.
//
//   const r = await visionCheck(db, "V001", pdfPath)               // text compare + Qwen vision
//   const r = await visionCheck(db, "V001", pdfPath, { qwen: false }) // text compare only
//
// The text compare always runs: it's exact, fast and gives the circles. Qwen adds what text can't see
// (scanned invoices with no text layer, a swapped logo). If Qwen is slow, offline or disagrees with the
// PDF text, the text result stands.
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import type { DB } from "../db/index.js";
import { REPO_ROOT } from "../db/index.js";
import type { Finding } from "../fingerprint/types.js";
import { scanPdf } from "../fingerprint/pdf.js";
import { readLayout, renderPage, type Layout, type Region } from "./layout.js";
import { compareFields, extractFields, groupInfo, hasText, type Group } from "./compare.js";
import { localVision, parseChanges, type ModelChange, type VisionClient } from "./qwen.js";

export type { Region } from "./layout.js";
export { readLayout, renderPage } from "./layout.js";
export { compareFields, extractFields, maskAccount } from "./compare.js";
export { localVision, parseChanges } from "./qwen.js";

export const INVOICES_DIR = join(REPO_ROOT, "data", "invoices");

export interface VisionOptions {
  qwen?: VisionClient | false;   // default: the local vLLM model
  referencePdf?: string;         // default: the vendor's last real invoice on file
  outDir?: string;               // where the circled PNG goes (default: OS temp dir)
}

export interface VisionResult {
  method: "vision+text" | "text" | "none";
  referencePdf: string | null;
  findings: Finding[];
  regions: Region[];
  annotatedPng: string | null;   // page 1 of the new invoice with the changes circled
  modelMs?: number;
  modelError?: string;
}

/** The vendor's most recent real invoice that we have a PDF for (paid or approved, never the file being checked). */
export function lastRealInvoicePdf(db: DB, vendorId: string, excludePath?: string): string | null {
  const rows = db.prepare(
    "SELECT invoice_number FROM invoices WHERE vendor_id = ? AND status IN ('paid','approved') ORDER BY invoice_date DESC",
  ).all(vendorId) as { invoice_number: string }[];
  for (const r of rows) {
    const p = join(INVOICES_DIR, `${r.invoice_number}.pdf`);
    if (existsSync(p) && (!excludePath || resolve(p) !== resolve(excludePath))) return p;
  }
  return null;
}

const MODEL_GROUP: Partial<Record<ModelChange["field"], Group>> = {
  bank_name: "bank", routing: "bank", account: "bank", remit_address: "remit", phone: "contact", email: "contact",
};

function modelRegion(c: ModelChange, layout: Layout, label: string, severity: Region["severity"]): Region | null {
  if (!c.box) return null;
  const { width: W, height: H } = layout.pages[0] ?? { width: 612, height: 792 };
  const [x1, y1, x2, y2] = c.box;
  return { page: 1, x: (x1 / 1000) * W, y: H - (y2 / 1000) * H, w: ((x2 - x1) / 1000) * W, h: ((y2 - y1) / 1000) * H,
           label, severity, approximate: true };
}

function hiddenRegions(hidden: Awaited<ReturnType<typeof scanPdf>>["hidden"]): Region[] {
  // Circled for the clerk; the finding itself (hidden_pdf_text) comes from the fingerprint (T05).
  return hidden.map((h) => ({ page: h.page, x: h.x, y: h.y - h.size * 0.25, w: Math.max(h.text.length * h.size * 0.5, 40),
                              h: Math.max(h.size * 1.2, 6), label: "Hidden text", severity: "high" as const }));
}

export async function visionCheck(db: DB, vendorId: string, pdfPath: string, opts: VisionOptions = {}): Promise<VisionResult> {
  const ref = opts.referencePdf ?? lastRealInvoicePdf(db, vendorId, pdfPath);
  if (!ref) {
    return { method: "none", referencePdf: null, regions: [], annotatedPng: null, findings: [{
      check: "invoice_compare", severity: "unknown", source: "vision", expected: "an earlier real invoice PDF on file",
      actual: "none found", explanation: "Couldn't compare the invoice image: no earlier real invoice from this vendor to compare with.",
    }] };
  }
  const vendor = db.prepare("SELECT name FROM vendors WHERE id = ?").get(vendorId) as { name: string } | undefined;
  const [refLayout, newLayout, scan] = await Promise.all([readLayout(ref), readLayout(pdfPath), scanPdf(pdfPath)]);
  const textOk = hasText(refLayout) && hasText(newLayout);

  // 1. Text compare (exact, no model)
  const text = textOk ? compareFields(extractFields(refLayout), extractFields(newLayout))
                      : { findings: [] as Finding[], regions: [] as Region[], changed: new Set<Group>() };
  const findings = [...text.findings];
  const regions = [...text.regions, ...hiddenRegions(scan.hidden)];

  // 2. Qwen vision (optional, add-only)
  let method: VisionResult["method"] = textOk ? "text" : "none";
  let modelMs: number | undefined, modelError: string | undefined;
  if (opts.qwen !== false) {
    const t0 = Date.now();
    try {
      const client = opts.qwen ?? localVision();
      const [refPng, newPng] = await Promise.all([renderPage(ref, 1, 1.25), renderPage(pdfPath, 1, 1.25)]);
      const changes = parseChanges(await client.compare(refPng, newPng, vendor?.name ?? vendorId));
      modelMs = Date.now() - t0;
      method = "vision+text";
      for (const c of changes) {
        const g = MODEL_GROUP[c.field];
        if (g && text.changed.has(g)) continue;                 // text already found it, with an exact circle
        if (g && !textOk) {                                     // scanned invoice: the model is our only reader
          const info = groupInfo(g);
          findings.push({ check: info.check, severity: info.severity, source: "vision",
                          expected: `${c.field}: ${c.before}`, actual: `${c.field}: ${c.after}`,
                          explanation: `${info.why} (Read from the image; this invoice has no text layer.)` });
          const r = modelRegion(c, newLayout, info.label, info.severity);
          if (r) regions.push(r);
          continue;
        }
        // Either a field text can't check (logo, layout) or the model disagrees with the PDF text: report, don't escalate.
        findings.push({ check: "invoice_visual_change", severity: "low", source: "vision",
                        expected: `${c.field}: ${c.before}`, actual: `${c.field}: ${c.after}`,
                        explanation: g ? `The model saw a change in ${c.field} that the invoice text doesn't confirm; worth a look.`
                                       : `The model saw a visual change (${c.field}) from the last real invoice.` });
        const r = modelRegion(c, newLayout, `Changed: ${c.field}`, "low");
        if (r) regions.push(r);
      }
    } catch (err) {
      modelMs = Date.now() - t0;
      modelError = (err as Error).message;
    }
  }

  if (method === "none") {
    findings.push({ check: "invoice_compare", severity: "unknown", source: "vision", expected: "a readable invoice",
                    actual: "no text layer and the model was unavailable",
                    explanation: `Couldn't compare the invoice: it has no readable text and the vision model didn't answer (${modelError ?? "disabled"}).` });
  }

  const outDir = opts.outDir ?? join(tmpdir(), "invoice-guard-vision");
  mkdirSync(outDir, { recursive: true });
  const annotatedPng = join(outDir, `${basename(pdfPath, ".pdf")}.circled.png`);
  writeFileSync(annotatedPng, await renderPage(pdfPath, 1, 2, regions));

  return { method, referencePdf: ref, findings, regions, annotatedPng, modelMs, modelError };
}
