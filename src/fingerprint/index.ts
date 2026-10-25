// Vendor fingerprint: compare one incoming message to the claimed vendor's own normal.
// Usage:
//   const r = await fingerprint(db, msg)               // rules + local Qwen
//   const r = await fingerprint(db, msg, { llm: false }) // rules only
import { join } from "node:path";
import type { DB } from "../db/index.js";
import { REPO_ROOT } from "../db/index.js";
import type { Finding, IncomingMessage, VendorProfile } from "./types.js";
import { buildProfile } from "./profile.js";
import { ruleChecks } from "./rules.js";
import { languageChecks, type LlmClient } from "./llm.js";
import { compareDomains, domainOf } from "./domain.js";
import { scanPdf } from "./pdf.js";
import { extractBank } from "./text.js";

export * from "./types.js";
export { buildProfile } from "./profile.js";
export { ruleChecks } from "./rules.js";
export { languageChecks, localLlm, isLocalHost } from "./llm.js";
export { compareDomains, skeleton } from "./domain.js";
export { scanPdf } from "./pdf.js";

export interface FingerprintResult {
  vendorId: string | null;
  impersonating: boolean;      // sender is not the vendor's real domain
  profile: VendorProfile | null;
  findings: Finding[];
}

/** Which vendor does this message claim to be? Exact domain, then lookalike, then display name. */
export function resolveVendor(db: DB, msg: IncomingMessage): { vendorId: string | null; impersonating: boolean } {
  const vendors = db.prepare("SELECT id, name, domain FROM vendors").all() as { id: string; name: string; domain: string }[];
  const d = domainOf(msg.from);
  const exact = vendors.find((v) => v.domain === d);
  if (exact) return { vendorId: exact.id, impersonating: false };
  const look = vendors.find((v) => compareDomains(d, v.domain).lookalike);
  if (look) return { vendorId: look.id, impersonating: true };
  const name = (msg.fromName ?? "").toLowerCase();
  const byName = vendors.find((v) => name && (name.includes(v.name.toLowerCase()) || v.name.toLowerCase().includes(name)));
  if (byName) return { vendorId: byName.id, impersonating: true };
  if (msg.vendorId) return { vendorId: msg.vendorId, impersonating: true };
  return { vendorId: null, impersonating: false };
}

export async function fingerprint(db: DB, msg: IncomingMessage, opts: { llm?: LlmClient | false } = {}): Promise<FingerprintResult> {
  const { vendorId, impersonating } = resolveVendor(db, msg);
  if (!vendorId) {
    return { vendorId: null, impersonating: false, profile: null, findings: [{
      check: "unknown_vendor", severity: "info", source: "rule", expected: "a vendor on file", actual: msg.from,
      explanation: "Sender doesn't match any vendor on file.",
    }] };
  }
  const profile = buildProfile(db, vendorId)!;
  const scans = await Promise.all((msg.pdfPaths ?? []).map((p) => scanPdf(p)));
  const withBank = { ...msg, requestedBank: msg.requestedBank ?? extractBank(msg.body) };
  const findings = ruleChecks(profile, withBank, scans);
  if (opts.llm !== false) findings.push(...(await languageChecks(profile, withBank, opts.llm || undefined)));
  return { vendorId, impersonating, profile, findings };
}

/** Convert an entry of data/fixtures/incoming.json into an IncomingMessage. */
export function messageFromFixture(x: any): IncomingMessage {
  return {
    id: x.id, vendorId: x.vendor_id, from: x.from, fromName: x.from_name, replyTo: x.reply_to,
    date: x.date, subject: x.subject, body: x.body, invoice: x.invoice, requestedBank: x.requested_bank,
    pdfPaths: (x.attachments ?? []).filter((a: string) => a.endsWith(".pdf")).map((a: string) => join(REPO_ROOT, "data", "invoices", a)),
  };
}
