import type { CaseState, CaseSummary, Finding, Outcome } from "./types";
import type { IconName } from "./ui/Icon";

export const money = (n: number | null | undefined, cents = true) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });

export function relTime(isoTs: string | null | undefined, now = Date.now()): string {
  if (!isoTs) return "";
  const t = Date.parse(isoTs);
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} d ago`;
}

export const clock = (isoTs: string | null | undefined) => {
  if (!isoTs) return "";
  const d = new Date(isoTs);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
};
export const clockSec = (isoTs: string | null | undefined) => {
  if (!isoTs) return "";
  const d = new Date(isoTs);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
};
export const shortDate = (isoDate: string | null | undefined) => {
  if (!isoDate) return "—";
  const d = new Date(isoDate.length === 10 ? `${isoDate}T12:00:00` : isoDate);
  return Number.isNaN(d.getTime()) ? isoDate : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

/** Model id → a short human name: "nvidia/Qwen3.6-35B-A3B-NVFP4" → "Qwen3.6 35B". */
export function modelName(id: string | null | undefined): string {
  if (!id) return "local model";
  const base = id.split("/").pop() ?? id;
  const m = base.match(/^(Qwen[\d.]*)-(\d+B)/i);
  return m ? `${m[1]} ${m[2]}` : base;
}

/** Last few segments of a path, so an absolute inbox dir fits in the rail. */
export const shortPath = (p: string | null | undefined, keep = 3) => {
  if (!p) return "";
  const parts = p.split("/").filter(Boolean);
  return parts.length > keep ? parts.slice(-keep).join("/") : p;
};
export const hostOf = (url: string | null | undefined) => (url ?? "").replace(/^https?:\/\//, "").replace(/\/$/, "");

// ------------------------------------------------------------------ case status words
export type Tone = "risk" | "confirm" | "ok" | "ink" | "agent";

export const isResolved = (s: CaseState) => s === "APPROVED" || s === "REJECTED";

export function statusOf(c: Pick<CaseSummary, "outcome" | "state">): { word: string; tone: Tone } {
  if (c.outcome === "PASS") return { word: "Cleared", tone: "ok" };
  if (c.state === "APPROVED") return { word: "Released", tone: "ok" };
  if (c.state === "REJECTED") return { word: "Rejected", tone: "ink" };
  if (c.state === "READY_FOR_APPROVAL") return { word: "Verified", tone: "ok" };
  return c.outcome === "HOLD_FRAUD_RISK" ? { word: "Fraud risk", tone: "risk" } : { word: "Needs confirmation", tone: "confirm" };
}

export const OUTCOME_WORD: Record<Outcome, string> = {
  HOLD_FRAUD_RISK: "Fraud risk",
  HOLD_CONFIRM: "Needs confirmation",
  PASS: "Cleared",
};

// ------------------------------------------------------------------ findings
export type Group = "Sender" | "Vendor fingerprint" | "Invoice" | "Rules";
export const GROUP_ORDER: Group[] = ["Sender", "Vendor fingerprint", "Invoice", "Rules"];
export const GROUP_ICON: Record<Group, IconName> = {
  Sender: "Mail",
  "Vendor fingerprint": "Fingerprint",
  Invoice: "Invoice",
  Rules: "Rules",
};
export const GROUP_HINT: Record<Group, string> = {
  Sender: "Who sent it",
  "Vendor fingerprint": "Compared with this vendor's own history",
  Invoice: "The document and where it pays",
  Rules: "District AP controls",
};

const GROUP_OF: Record<string, Group> = {
  lookalike_domain: "Sender", freemail_sender: "Sender", unknown_sender: "Sender", reply_to_mismatch: "Sender",
  unknown_vendor: "Sender", email_auth_failed: "Sender",
  style_mismatch: "Vendor fingerprint", urgency: "Vendor fingerprint", unusual_request: "Vendor fingerprint",
  first_bank_change: "Vendor fingerprint", bill_too_soon: "Vendor fingerprint", fixed_amount_changed: "Vendor fingerprint",
  off_cycle_date: "Vendor fingerprint", language_checks: "Vendor fingerprint",
  bank_mismatch: "Invoice", remit_change: "Invoice", duplicate_invoice: "Invoice", invoice_out_of_sequence: "Invoice",
  hidden_pdf_text: "Invoice", amount_out_of_range: "Invoice",
  bank_change_request: "Rules", payment_change_from_unknown_sender: "Rules", prompt_injection: "Rules",
  po_mismatch: "Rules", one_time_bill: "Rules", no_billing_history: "Rules",
};
export function groupOf(f: Finding): Group {
  if (GROUP_OF[f.check]) return GROUP_OF[f.check];
  if (f.source === "vision") return "Invoice";
  if (f.source === "llm") return "Vendor fingerprint";
  return "Rules";
}

const LABEL: Record<string, string> = {
  lookalike_domain: "Lookalike domain",
  freemail_sender: "Free webmail sender",
  unknown_sender: "Unknown sender",
  reply_to_mismatch: "Reply-to redirected",
  unknown_vendor: "Not in vendor master",
  email_auth_failed: "Email authentication",
  style_mismatch: "Writing style",
  urgency: "Urgency",
  unusual_request: "Unusual request",
  first_bank_change: "First bank change ever",
  bill_too_soon: "Billing rhythm",
  fixed_amount_changed: "Fixed amount changed",
  off_cycle_date: "Billing day",
  language_checks: "Language checks",
  bank_mismatch: "Bank account",
  remit_change: "Remit-to address",
  duplicate_invoice: "Invoice number reused",
  invoice_out_of_sequence: "Invoice sequence",
  hidden_pdf_text: "Hidden text in PDF",
  amount_out_of_range: "Amount range",
  bank_change_request: "Bank change requested",
  payment_change_from_unknown_sender: "Payment change, unknown sender",
  prompt_injection: "Instruction aimed at AI",
  po_mismatch: "PO mismatch",
  one_time_bill: "No PO / one-off bill",
  no_billing_history: "First invoice ever",
  invoice_visual_diff: "Invoice image compare",
};
export const checkLabel = (check: string | null | undefined) =>
  LABEL[check ?? ""] ?? String(check ?? "check").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const SOURCE_LABEL: Record<NonNullable<Finding["source"]>, string> = {
  rule: "Rule",
  llm: "Local model",
  vision: "Vision",
};
export const SOURCE_ICON: Record<NonNullable<Finding["source"]>, IconName> = {
  rule: "Rules",
  llm: "Chip",
  vision: "Vision",
};

// ------------------------------------------------------------------ audit
const ACTION: Record<string, string> = {
  case_opened: "Held the payment and opened the case",
  callback_drafted: "Drafted a callback to the number on file",
  requester_check_drafted: "Drafted a question to the requester",
  alert_posted: "Posted the Slack summary",
  no_vendor_on_file: "No vendor on file to call",
  verification_started: "Started verification",
  vendor_confirmation: "Recorded the vendor's answer",
  requester_confirmation: "Recorded the requester's answer",
  callback_no_answer: "Called the number on file: no answer",
  no_answer: "No answer yet",
  approved: "Approved and released the payment",
  rejected: "Rejected the payment",
  passed: "Passed every check",
};
export const actionLabel = (a: string | null | undefined) => ACTION[a ?? ""] ?? String(a ?? "event").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const PEOPLE: Record<string, string> = {
  "janet.kim": "Janet Kim",
  "omar.reyes": "Omar Reyes",
  "pat.lee": "Pat Lee",
};
export const personName = (actor: string | null | undefined) =>
  PEOPLE[actor ?? ""] ?? String(actor ?? "someone").split(/[._]/).map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
export const isAgent = (actor: string | null | undefined) => !!actor && (actor === "agent" || actor === "halberd" || actor.startsWith("agent"));

/** Detail objects from the audit log as one quiet line. Never prints raw JSON braces. */
export function detailLine(action: string, detail: unknown): string {
  let d: any = detail;
  if (typeof d === "string") {
    try { d = JSON.parse(d); } catch { return d; }
  }
  if (!d || typeof d !== "object") return "";
  if (action === "case_opened" && d.score != null) return `Score ${d.score}${Array.isArray(d.checks) ? ` · ${d.checks.length} checks flagged` : ""}`;
  if (action === "callback_drafted" && d.phone) return `${d.phone}${d.contact ? ` · ask for ${d.contact}` : ""}`;
  if (action === "requester_check_drafted" && d.to) return `To ${d.to}${d.source === "llm" ? " · written by the local model" : ""}`;
  if (action === "verification_started" && d.method) return d.method === "phone" ? "By phone, number on file" : "Asked the requester";
  if ((action === "vendor_confirmation" || action === "requester_confirmation") && "confirmed" in d)
    return d.confirmed ? "Confirmed the request is genuine" : "Said they never sent it";
  if (d.reason) return String(d.reason);
  if (d.note) return String(d.note);
  if (d.channel) return String(d.channel);
  return "";
}
