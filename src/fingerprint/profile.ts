// Build a vendor's "normal" from the AP database: identity, money, rhythm, and writing style.
import type { DB } from "../db/index.js";
import type { VendorProfile } from "./types.js";
import { BANK_CHANGE_RE, URGENT_RE } from "./text.js";

const SAMPLE_SIZE = 20;

export function buildProfile(db: DB, vendorId: string): VendorProfile | null {
  const v = db.prepare("SELECT * FROM vendors WHERE id = ?").get(vendorId) as any;
  if (!v) return null;
  const contacts = db.prepare("SELECT name, email FROM vendor_contacts WHERE vendor_id = ?").all(vendorId) as any[];
  const bank = (db.prepare("SELECT bank_name, routing, account, remit_address FROM vendor_banks WHERE vendor_id = ? AND active = 1").get(vendorId) ?? {}) as any;
  const po = db.prepare("SELECT number, monthly_min, monthly_max FROM purchase_orders WHERE vendor_id = ?").get(vendorId) as any;
  const invoices = db.prepare("SELECT invoice_number, amount FROM invoices WHERE vendor_id = ? ORDER BY invoice_date, invoice_number").all(vendorId) as any[];
  const emails = db.prepare("SELECT date, subject, body FROM emails WHERE vendor_id = ? AND kind = 'history' ORDER BY date").all(vendorId) as any[];

  const amounts = invoices.map((i) => i.amount as number).sort((a, b) => a - b);
  const median = amounts.length ? amounts[Math.floor(amounts.length / 2)] : 0;

  const lines = (b: string) => b.split("\n").map((l) => l.trim()).filter(Boolean);
  const greetings = uniq(emails.map((e) => lines(e.body)[0] ?? "").filter(Boolean));
  const signoffs = uniq(emails.map((e) => lines(e.body).slice(-2).join(" ")).filter(Boolean));
  const avgLines = emails.length ? emails.reduce((n, e) => n + lines(e.body).length, 0) / emails.length : 0;

  return {
    vendorId,
    name: v.name,
    domain: v.domain,
    phoneOnFile: v.phone_on_file,
    contacts: contacts.map((c) => ({ name: c.name, email: String(c.email).toLowerCase() })),
    bank,
    billingDay: v.billing_day ?? null,
    amount: { min: amounts[0] ?? 0, max: amounts[amounts.length - 1] ?? 0, median, count: amounts.length },
    po: po ? { number: po.number, monthlyMin: po.monthly_min, monthlyMax: po.monthly_max } : null,
    invoiceNumbers: invoices.map((i) => i.invoice_number),
    everRequestedBankChange: emails.some((e) => BANK_CHANGE_RE.test(e.body) || BANK_CHANGE_RE.test(e.subject ?? "")),
    style: { greetings, signoffs, avgLines: Math.round(avgLines * 10) / 10, usesUrgentWords: emails.some((e) => URGENT_RE.test(e.body)) },
    sampleEmails: emails.slice(-SAMPLE_SIZE),
  };
}

function uniq(xs: string[]): string[] {
  const counts = new Map<string, number>();
  for (const x of xs) counts.set(x, (counts.get(x) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([x]) => x).slice(0, 5);
}
