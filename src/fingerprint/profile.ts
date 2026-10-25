// Build a vendor's "normal" from the AP database: identity, money, rhythm, and writing style.
import type { DB } from "../db/index.js";
import type { Rhythm, VendorProfile } from "./types.js";
import { BANK_CHANGE_RE, URGENT_RE } from "./text.js";

const SAMPLE_SIZE = 20;

export function buildProfile(db: DB, vendorId: string): VendorProfile | null {
  const v = db.prepare("SELECT * FROM vendors WHERE id = ?").get(vendorId) as any;
  if (!v) return null;
  const contacts = db.prepare("SELECT name, email FROM vendor_contacts WHERE vendor_id = ?").all(vendorId) as any[];
  const bank = (db.prepare("SELECT bank_name, routing, account, remit_address FROM vendor_banks WHERE vendor_id = ? AND active = 1").get(vendorId) ?? {}) as any;
  const po = db.prepare("SELECT number, monthly_min, monthly_max FROM purchase_orders WHERE vendor_id = ?").get(vendorId) as any;
  const invoices = db.prepare("SELECT invoice_number, invoice_date, amount FROM invoices WHERE vendor_id = ? ORDER BY invoice_date, invoice_number").all(vendorId) as any[];
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
    rhythm: learnRhythm(invoices.map((i) => ({ date: String(i.invoice_date), amount: Number(i.amount) }))),
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

const DAY = 86_400_000;
export const daysBetween = (a: string, b: string) => Math.round((Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10))) / DAY);
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0; };

/** Cadence, typical gap, next expected date, and whether the amount is fixed. */
export function learnRhythm(history: { date: string; amount: number }[]): Rhythm {
  const h = [...history].sort((a, b) => a.date.localeCompare(b.date));
  if (!h.length) return { cadence: "none", intervalDays: null, lastInvoiceDate: null, expectedNextDate: null, fixedAmount: false, typicalAmount: null };
  const last = h[h.length - 1].date.slice(0, 10);
  const typical = median(h.map((x) => x.amount));
  const fixedAmount = h.length >= 3 && h.every((x) => Math.abs(x.amount - typical) <= typical * 0.075);
  if (h.length < 2) return { cadence: "irregular", intervalDays: null, lastInvoiceDate: last, expectedNextDate: null, fixedAmount: false, typicalAmount: typical };
  const gaps = h.slice(1).map((x, i) => daysBetween(h[i].date, x.date));
  const gap = median(gaps);
  const allWithin = (lo: number, hi: number) => gaps.every((g) => g >= lo && g <= hi);
  const cadence: Rhythm["cadence"] =
    gap >= 25 && gap <= 35 && allWithin(20, 40) ? "monthly" :
    gap >= 80 && gap <= 100 && allWithin(70, 110) ? "quarterly" : "irregular";
  const next = cadence === "irregular" ? null : new Date(Date.parse(last) + gap * DAY).toISOString().slice(0, 10);
  return { cadence, intervalDays: gap, lastInvoiceDate: last, expectedNextDate: next, fixedAmount, typicalAmount: typical };
}
