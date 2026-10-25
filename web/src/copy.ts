// Plain-language copy for the v2 screens. Every visible sentence that comes from the API passes through here:
// no check ids, no parenthetical asides, no implementation words.
import type { AlertItem, CaseDetail, Finding, Risk } from "./types";
import { clock } from "./format";

const PHONE = /\((\d{3})\)\s?(\d{3}-\d{4})/g;

/** Drop parenthetical asides (nested too) but keep phone numbers like (559) 555-0142. */
export function plain(s: string | null | undefined): string {
  if (!s) return "";
  let t = s.replace(PHONE, "\u0001$1\u0002 $2");
  for (let i = 0; i < 4; i++) {
    const next = t.replace(/\s*\([^()]*\)/g, "");
    if (next === t) break;
    t = next;
  }
  t = t.replace(/\u0001/g, "(").replace(/\u0002/g, ")");
  t = t.replace(/Invoice Guard/g, "Halberd");
  // Never show ISO dates: 2026-10-14 → Oct 14
  t = t.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (_, y, m, d) =>
    new Date(Number(y), Number(m) - 1, Number(d)).toLocaleDateString("en-US", { month: "short", day: "numeric" }));
  return t.replace(/\s+([.,;:])/g, "$1").replace(/\s{2,}/g, " ").trim();
}

// Capitalise sentences, never a bare domain or address.
const cap = (s: string) => (s && /\s/.test(s) ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/** "First Valley Bank, routing ••••0111, account ••••3378" → "First Valley Bank ••3378" */
export function bankShort(s: string): string {
  const m = s.match(/^(.*?),?\s*routing\s+\S+,?\s*account\s+[•*xX\d]*?(\d{4})\s*$/i);
  if (m) return `${m[1].trim()} ••${m[2]}`;
  const a = s.match(/^(.*?),?\s*account\s+[•*xX\d]*?(\d{4})\s*$/i);
  if (a) return `${a[1].trim()} ••${a[2]}`;
  return s;
}

const LABEL: Record<string, string> = {
  lookalike_domain: "Sender's domain",
  freemail_sender: "Sender's address",
  unknown_sender: "Sender",
  reply_to_mismatch: "Replies go to",
  payment_change_from_unknown_sender: "Who is asking",
  bank_mismatch: "Bank account",
  bank_change_request: "Bank account",
  remit_change: "Remit-to address",
  hidden_pdf_text: "Hidden text",
  duplicate_invoice: "Invoice number",
  invoice_visual_diff: "Invoice page",
  urgency: "Tone",
  unusual_request: "Request",
  style_mismatch: "Writing style",
  bill_too_soon: "Billing timing",
  one_time_bill: "Purchase order",
  fixed_amount_changed: "Amount",
  amount_out_of_range: "Amount",
  po_mismatch: "Purchase order",
  first_bank_change: "Bank changes",
  off_cycle_date: "Billing day",
  invoice_out_of_sequence: "Invoice number",
  no_billing_history: "History",
  email_auth_failed: "Email check",
  prompt_injection: "Hidden instruction",
};

const CHANGE_ORDER = [
  "lookalike_domain", "freemail_sender", "bank_mismatch", "bank_change_request", "first_bank_change", "hidden_pdf_text",
  "invoice_visual_diff", "urgency", "unusual_request", "style_mismatch", "duplicate_invoice", "remit_change", "bill_too_soon",
  "one_time_bill", "fixed_amount_changed", "amount_out_of_range", "po_mismatch", "off_cycle_date", "reply_to_mismatch",
  "unknown_sender", "invoice_out_of_sequence",
];

export interface ChangeRow { key: string; label: string; usually: string; now: string }

export function rowFor(f: Finding): ChangeRow | null {
  const label = LABEL[f.check];
  if (!label) return null;
  let usually = plain(f.expected);
  let now = plain(f.actual);
  switch (f.check) {
    case "bank_mismatch":
    case "bank_change_request":
      usually = /routing|account/i.test(f.expected) ? bankShort(plain(f.expected)) : "The bank on file";
      now = /routing|account/i.test(f.actual) ? bankShort(plain(f.actual)) : "Asks to change it";
      break;
    case "first_bank_change": {
      const n = f.expected.match(/(\d+)\s+past emails/);
      usually = n ? `No bank change in ${n[1]} emails` : plain(f.expected) || "Never asked to change banks";
      now = "Asks to change banks";
      break;
    }
    case "duplicate_invoice":
      usually = "A new number each month";
      now = `${plain(f.actual).split(",")[0]} again`;
      break;
    case "hidden_pdf_text":
      usually = "None";
      now = plain(f.actual).replace(/^["“]|["”]$/g, "");
      now = `“${now}”`;
      break;
    case "unknown_sender":
      usually = plain(f.expected).split(",")[0];
      break;
    case "one_time_bill":
      usually = "Billed against a purchase order";
      now = "No purchase order";
      break;
  }
  const iso = (t: string) => t.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (m) => shortDate(m));
  return { key: f.check, label, usually: cap(iso(usually)), now: cap(iso(now)) };
}

/** At most three rows for "What changed", strongest first, no repeats of the same label. */
export function changes(findings: Finding[], max = 3): ChangeRow[] {
  const hasMismatch = findings.some((f) => f.check === "bank_mismatch");
  const sorted = [...findings]
    .filter((f) => f.severity !== "unknown" && f.severity !== "info")
    .filter((f) => !(hasMismatch && f.check === "bank_change_request"))
    .sort((a, b) => rank(a) - rank(b));
  const out: ChangeRow[] = [];
  const seen = new Set<string>();
  for (const f of sorted) {
    const r = rowFor(f);
    if (!r || seen.has(r.label)) continue;
    seen.add(r.label);
    out.push(r);
    if (out.length === max) break;
  }
  return out;
}
const rank = (f: Finding) => {
  const i = CHANGE_ORDER.indexOf(f.check);
  return i === -1 ? 100 : i;
};

const WHY_ORDER = [
  "lookalike_domain", "freemail_sender", "hidden_pdf_text", "bank_mismatch", "urgency", "unusual_request", "first_bank_change",
  "payment_change_from_unknown_sender", "duplicate_invoice", "one_time_bill", "bill_too_soon", "fixed_amount_changed", "amount_out_of_range",
];

/** One plain sentence for "Why Halberd held it". */
export function whyOf(d: CaseDetail): string {
  if (d.why) return plain(d.why);
  for (const check of WHY_ORDER) {
    const f = d.findings.find((x) => x.check === check && x.explanation);
    if (f) return firstSentences(plain(f.explanation), check === "first_bank_change" ? 2 : 1);
  }
  const high = d.findings.find((f) => f.severity === "high" && f.explanation);
  if (high) return firstSentences(plain(high.explanation), 1);
  return firstSentences(plain(d.decision.reasons[0] ?? d.case.reason ?? ""), 1);
}
const firstSentences = (s: string, n: number) => {
  // Split only where punctuation is followed by a space, so "acme-supp1y.com" stays whole.
  return s.split(/(?<=[.!?])\s+/).slice(0, n).join(" ").trim();
};

/** "What Halberd did", in plain lines. */
export function whatHalberdDid(d: CaseDetail, alert: AlertItem | null): string[] {
  const ev = d.audit.events;
  const opened = ev.find((e) => e.action === "case_opened");
  const lines = [`Held the payment at ${clock(opened?.ts ?? d.case.createdAt)}.`];
  if (ev.some((e) => e.action === "callback_drafted")) lines.push("Drafted a call to the number on file.");
  if (ev.some((e) => e.action === "requester_check_drafted")) {
    const who = d.requesterChecks[0]?.recipientName;
    lines.push(who ? `Drafted a question for ${who}.` : "Drafted a question for the person who ordered.");
  }
  if (alert) lines.push(alert.sent ? "Alerted the AP team in Slack." : "Alerted the AP team.");
  return lines;
}

export const possessive = (name: string) => (/s$/i.test(name) ? `${name}'` : `${name}'s`);

export const RISK_WORD: Record<Risk, string> = { fraud: "Fraud risk", confirm: "Needs confirmation", cleared: "Cleared" };

/** Sidebar date: time today, "Oct 1" this year, "Nov 1, 2025" otherwise. */
export function dateLabel(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (iso.length > 10 && d.toDateString() === now.toDateString()) return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

export const longDate = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

/** "2026-10-14" -> "Oct 14" this year, "Oct 14, 2025" otherwise. */
function shortDate(iso: string, now = new Date()): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
}

/** Display label for an invoice number: "TN-2211" -> "Invoice #11". The real number stays in the data. */
export function invoiceLabel(num: string | null | undefined): string {
  if (!num) return "No invoice";
  const m = num.match(/(\d+)\D*$/);
  if (!m) return `Invoice ${num}`;
  const n = Number(m[1]) % 100 || 100;
  return `Invoice #${n}`;
}

/** "Greenfield Food Service" -> "Greenfield"; keeps short names whole. */
export const shortName = (name: string) => {
  const first = name.split(/\s+/)[0];
  return first.length >= 4 ? first : name;
};
