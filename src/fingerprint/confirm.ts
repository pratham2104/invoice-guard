// Draft the internal "did you order this?" message for a surprise bill.
// Goes to the district staff member who requested the PO, NEVER to the email sender or vendor.
// Drafts only: delivery (Slack / in-app) is T09's job. No bank details in the text.
import type { DB } from "../db/index.js";
import type { Finding, IncomingMessage } from "./types.js";
import { localLlm, type LlmClient } from "./llm.js";
import { domainOf } from "./domain.js";

export interface Requester { name: string; contact: string; department?: string }

export interface RequesterDraft {
  recipient: Requester | null;      // null = no requester on file; route to the AP lead
  poNumber: string | null;
  text: string;
  source: "llm" | "template";
  triggeredBy: string[];            // finding checks that asked for confirmation
  note?: string;
}

const money = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The requester for an invoice: its PO's requester, else the vendor's usual PO requester. Internal only. */
export function findRequester(db: DB, vendorId: string, poNumber?: string | null): { requester: Requester | null; poNumber: string | null } {
  const row = (poNumber
    ? db.prepare("SELECT number, requester_name, requester_contact, requester_department FROM purchase_orders WHERE number = ?").get(poNumber)
    : undefined) ?? db.prepare("SELECT number, requester_name, requester_contact, requester_department FROM purchase_orders WHERE vendor_id = ? ORDER BY number DESC").get(vendorId);
  const r = row as any;
  if (!r?.requester_contact) return { requester: null, poNumber: poNumber ?? null };
  return { requester: { name: r.requester_name, contact: r.requester_contact, department: r.requester_department ?? undefined }, poNumber: poNumber ?? null };
}

export function templateText(p: { firstName: string; vendor: string; amount: number; invoiceNumber: string; date: string; poNumber: string | null; usualPo: string | null; description?: string }): string {
  const what = p.description ? ` for ${p.description[0].toLowerCase()}${p.description.slice(1)}` : "";
  const po = p.poNumber ? `on ${p.poNumber}` : `with no PO number${p.usualPo ? ` (their usual PO is ${p.usualPo})` : ""}`;
  return `Hi ${p.firstName}, an invoice from ${p.vendor} came in ${po}: ${p.invoiceNumber}, ${money(p.amount)}${what}, dated ${p.date}. ` +
    `Did you order this? Please reply yes or no. Payment is on hold until you confirm. (Invoice Guard, Accounts Payable)`;
}

/** Reject model output that could mislead or leak: must name vendor + amount + yes/no; no long digit runs, no sender address. */
function acceptable(text: string, vendor: string, amount: number, sender: string): boolean {
  const amt = Math.round(amount).toLocaleString("en-US");
  return text.length > 20 && text.length < 600 &&
    text.includes(vendor) && text.includes(amt) && /\byes\b/i.test(text) && /\bno\b/i.test(text) &&
    !/\d{6,}/.test(text.replace(/\$[\d,]+(?:\.\d+)?/g, "")) &&   // no account/routing-length numbers
    !text.toLowerCase().includes(sender.toLowerCase());
}

export async function draftRequesterConfirmation(db: DB, vendorId: string, msg: IncomingMessage, findings: Finding[],
                                                 opts: { llm?: LlmClient | false; force?: boolean } = {}): Promise<RequesterDraft | null> {
  const triggeredBy = findings.filter((f) => f.action === "confirm_with_requester").map((f) => f.check);
  if (!triggeredBy.length && !opts.force) return null;
  if (!msg.invoice) return null;
  const vendor = (db.prepare("SELECT name FROM vendors WHERE id = ?").get(vendorId) as any)?.name ?? "the vendor";
  const inv = msg.invoice;
  const { requester, poNumber } = findRequester(db, vendorId, inv.po_number);
  const usualPo = (db.prepare("SELECT number FROM purchase_orders WHERE vendor_id = ? ORDER BY number DESC").get(vendorId) as any)?.number ?? null;

  // never route the confirmation back to whoever sent the invoice
  if (requester && (requester.contact.toLowerCase() === msg.from.toLowerCase() || domainOf(requester.contact) === domainOf(msg.from))) {
    return { recipient: null, poNumber, text: "", source: "template", triggeredBy, note: "requester contact matches the sender; route to the AP lead" };
  }

  const firstName = requester?.name.replace(/^(dr|mr|mrs|ms)\.?\s+/i, "").split(/\s+/)[0] ?? "there";
  const base = { firstName, vendor, amount: inv.amount, invoiceNumber: inv.invoice_number, date: inv.invoice_date, poNumber: inv.po_number ?? null, usualPo, description: inv.description };
  const fallback = templateText(base);
  const note = requester ? undefined : "no requester on file for this PO; route to the AP lead";

  if (opts.llm !== false) {
    try {
      const client = opts.llm || localLlm();
      const raw = await client.complete([
        { role: "system", content: "You write short internal messages for a school district's accounts-payable team. Plain, friendly, 2-3 sentences. Never include bank details. Reply with JSON only: {\"message\": \"...\"}" },
        { role: "user", content:
          `Write a message to ${requester?.name ?? "the budget owner"}${requester?.department ? ` (${requester.department})` : ""} asking if they ordered this. ` +
          `Facts: vendor ${vendor}; invoice ${inv.invoice_number}; amount ${money(inv.amount)}; dated ${inv.invoice_date}; ` +
          `${inv.po_number ? `PO ${inv.po_number}` : `no PO number${usualPo ? ` (usual PO ${usualPo})` : ""}`}` +
          `${inv.description ? `; description: ${inv.description}` : ""}. Reasons it looks unusual: ${triggeredBy.join(", ")}. ` +
          `Say payment is on hold until they confirm, and ask them to reply yes or no.` },
      ]);
      const clean = raw.replace(/<think>[\s\S]*?<\/think>/g, "");
      const j = JSON.parse(clean.slice(clean.indexOf("{"), clean.lastIndexOf("}") + 1));
      const text = String(j.message ?? "").trim();
      if (acceptable(text, vendor, inv.amount, msg.from)) return { recipient: requester, poNumber, text, source: "llm", triggeredBy, note };
    } catch { /* model offline or bad output: use the template */ }
  }
  return { recipient: requester, poNumber, text: fallback, source: "template", triggeredBy, note };
}
