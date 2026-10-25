// Alerts (T09): a short Slack summary + an in-app alert feed.
// Ported from Prerna's prototype (prerna-1, prototype/ap-guard/apguard/slack_app.py `case_blocks`):
// summary only — vendor, decision, top reason, case id. NEVER invoice numbers, amounts, sender, bank numbers.
// Webhook only: interactive buttons need a public URL, so humans act in the app / CLI, not in Slack.
import type { DB } from "../db/index.js";
import type { Finding } from "../fingerprint/types.js";
import type { Outcome } from "../rules/index.js";

export interface Alert {
  caseId: string;
  vendorName: string | null;
  outcome: Outcome;
  state: string;
  headline: string;   // "HOLD-0003 · payment HELD: fraud risk"
  reason: string;     // plain phrase for the top finding(s)
  text: string;       // Slack fallback text
  blocks: unknown[];  // Slack Block Kit
}

/** Plain words for each check. No data from the message ever goes into an alert. */
export const PHRASES: Record<string, string> = {
  lookalike_domain: "sender domain imitates the vendor",
  freemail_sender: "sent from a free webmail address",
  payment_change_from_unknown_sender: "unknown sender asking to change payment details",
  unknown_sender: "sender isn't a known contact",
  reply_to_mismatch: "replies would go to a different domain",
  bank_change_request: "asks to change bank details",
  first_bank_change: "first bank change this vendor has ever asked for",
  bank_mismatch: "bank account differs from the one on file",
  remit_change: "remit-to address changed",
  duplicate_invoice: "invoice number already received",
  invoice_out_of_sequence: "invoice number out of sequence",
  po_mismatch: "PO doesn't belong to this vendor",
  amount_out_of_range: "amount outside the usual range",
  off_cycle_date: "billed off the usual day",
  hidden_pdf_text: "invoice contains hidden text",
  prompt_injection: "email contains instructions aimed at an AI",
  email_auth_failed: "email authentication failed",
  unknown_vendor: "sender isn't in the vendor master",
  bill_too_soon: "billed sooner than usual",
  fixed_amount_changed: "fixed monthly amount changed",
  one_time_bill: "one-off bill / no PO",
  no_billing_history: "first invoice from this vendor",
  urgency: "pressure to pay fast",
  style_mismatch: "writing style doesn't match the vendor",
  unusual_request: "unusual request",
};

const OUTCOME_LABEL: Record<Outcome, string> = {
  PASS: "passed",
  HOLD_FRAUD_RISK: "HELD: fraud risk, phone callback to the number on file",
  HOLD_CONFIRM: "HELD: waiting for the requester to confirm the order",
};
const EMOJI: Record<Outcome, string> = { PASS: ":white_check_mark:", HOLD_FRAUD_RISK: ":rotating_light:", HOLD_CONFIRM: ":large_yellow_circle:" };

/** Belt and braces: strip anything that looks like an account/routing/amount or an email address. */
export function scrub(s: string): string {
  return s.replace(/[\w.+-]+@[\w.-]+/g, "[address]").replace(/\$?\d[\d,.]{4,}/g, "[number]");
}

export function buildAlert(a: { caseId: string; vendorName: string | null; outcome: Outcome; state: string; top: Finding[] }): Alert {
  const reasons = [...new Set(a.top.map((f) => PHRASES[f.check] ?? f.check.replace(/_/g, " ")))].slice(0, 3);
  const reason = reasons.join("; ") || "no specific reason";
  const vendor = scrub(a.vendorName ?? "unknown vendor");
  const headline = `${a.caseId} · payment ${OUTCOME_LABEL[a.outcome]}`;
  const text = scrub(`${a.caseId}: ${vendor} — ${OUTCOME_LABEL[a.outcome]}. Why: ${reason}.`);
  const blocks = [
    { type: "header", text: { type: "plain_text", text: scrub(headline).slice(0, 150) } },
    { type: "section", text: { type: "mrkdwn", text: scrub(
      `${EMOJI[a.outcome]} *Vendor:* ${vendor}\n*State:* \`${a.state}\`\n*Why:* ${reason}\n` +
      `_Alerts are a heads-up; the data stays on the box. Open ${a.caseId} in Invoice Guard to act._`) } },
  ];
  return { caseId: a.caseId, vendorName: a.vendorName, outcome: a.outcome, state: a.state, headline, reason, text, blocks };
}

export interface SlackResult { sent: boolean; status?: number; reason?: string }

/** Post to SLACK_WEBHOOK_URL if set. Pass `fetchImpl` in tests: no network in tests. */
export async function postToSlack(alert: Alert, opts: { webhookUrl?: string; fetchImpl?: typeof fetch } = {}): Promise<SlackResult> {
  const url = opts.webhookUrl ?? process.env.SLACK_WEBHOOK_URL ?? "";
  if (!url) return { sent: false, reason: "SLACK_WEBHOOK_URL not set" };
  if (!/^https:\/\/hooks\.slack\.com\//.test(url)) return { sent: false, reason: "not a Slack webhook URL" };
  try {
    const res = await (opts.fetchImpl ?? fetch)(url, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: alert.text, blocks: alert.blocks }),
      signal: AbortSignal.timeout(10_000),
    });
    return res.ok ? { sent: true, status: res.status } : { sent: false, status: res.status, reason: `Slack HTTP ${res.status}` };
  } catch (err) {
    return { sent: false, reason: (err as Error).message };
  }
}

// --- in-app alert feed (fully local)
export function ensureAlertsTable(db: DB) {
  db.exec(`CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    vendor_name TEXT,
    outcome TEXT NOT NULL,
    state TEXT,
    headline TEXT NOT NULL,
    reason TEXT NOT NULL,
    slack_sent INTEGER NOT NULL DEFAULT 0,
    slack_note TEXT
  )`);
}

export function recordAlert(db: DB, alert: Alert, slack?: SlackResult): number {
  ensureAlertsTable(db);
  const r = db.prepare("INSERT INTO alerts (case_id, created_at, vendor_name, outcome, state, headline, reason, slack_sent, slack_note) VALUES (?,?,?,?,?,?,?,?,?)")
    .run(alert.caseId, new Date().toISOString(), alert.vendorName, alert.outcome, alert.state, alert.headline, alert.reason,
         slack?.sent ? 1 : 0, slack?.reason ?? null);
  return Number(r.lastInsertRowid);
}

export function listAlerts(db: DB, limit = 50): any[] {
  ensureAlertsTable(db);
  return db.prepare("SELECT * FROM alerts ORDER BY id DESC LIMIT ?").all(limit) as any[];
}

/** Build, post (if configured) and record. Returns what happened. */
export async function raiseAlert(db: DB, a: Parameters<typeof buildAlert>[0], opts: Parameters<typeof postToSlack>[1] = {}) {
  const alert = buildAlert(a);
  const slack = await postToSlack(alert, opts);
  const id = recordAlert(db, alert, slack);
  return { id, alert, slack };
}
