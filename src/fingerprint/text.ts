// Text patterns shared by the profile builder and the rule checks.
import type { Bank } from "./types.js";

/** Mentions changing / new bank or remittance details. */
export const BANK_CHANGE_RE =
  /\b(new|change[ds]?|changing|update[ds]?|updating|switch(?:ed)?|moved?|corrected)\b[^.\n]{0,40}\b(bank(?:ing)?|account|remit(?:tance)?|routing|ACH|wire)\b|\b(bank(?:ing)?|remit(?:tance)?|routing)\b[^.\n]{0,30}\b(change[ds]?|updated?|new)\b/i;

/** Pressure words a normal vendor rarely uses. */
export const URGENT_RE =
  /\b(urgent|immediately|asap|end of day|suspend(?:ed)?|final notice|right away|confidential)\b|\b(pay|paid|payment|process(?:ed)?|wire|transfer)\b[^.\n]{0,40}\btoday\b/i;

/** Pull bank details out of free text (email body or invoice PDF text). */
export function extractBank(text: string): Bank | undefined {
  const routing = text.match(/routing(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*(\d{9})/i)?.[1];
  const account = text.match(/account(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*(\d{6,17})/i)?.[1];
  const bank_name = text.match(/\bbank\s*(?:name)?\s*:\s*([^\n]+)/i)?.[1]?.trim();
  const remit_address = text.match(/remit(?:tance)?\s*address\s*:\s*([^\n]+)/i)?.[1]?.trim();
  if (!routing && !account && !bank_name && !remit_address) return undefined;
  return { bank_name, routing, account, remit_address };
}

/** Parse the fields we care about from invoice PDF text (label and value are separate text runs). */
export function parseInvoiceText(text: string): { invoice_number?: string; invoice_date?: string; po_number?: string; amount?: number; bank?: Bank } {
  const after = (label: RegExp) => text.match(new RegExp(label.source + String.raw`\s*\n\s*([^\n]+)`, "i"))?.[1]?.trim();
  const total = text.match(/TOTAL DUE[^\n]*\n\s*([\d,]+\.\d{2})/i)?.[1];
  return {
    invoice_number: after(/Invoice #/),
    invoice_date: after(/\bDate\b/),
    po_number: after(/\bPO\b/),
    amount: total ? Number(total.replace(/,/g, "")) : undefined,
    bank: extractBank(text),
  };
}
