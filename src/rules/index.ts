// AP control rules (T04). Deterministic: same findings in, same decision out. No model in here.
// Ported from Prerna's prototype (prerna-1, prototype/ap-guard/apguard/rules.py `evaluate` / `_finish`):
// points per finding, "any high holds", fail closed. Findings come from src/fingerprint; this file adds
// only the two message-level checks her prototype had and the fingerprint doesn't (prompt-injection wording
// and failed SPF/DKIM/DMARC), then decides.
import type { Finding, IncomingMessage } from "../fingerprint/types.js";

export type Outcome = "PASS" | "HOLD_FRAUD_RISK" | "HOLD_CONFIRM";
export type NextStep = "none" | "phone_callback" | "requester_confirmation";

export interface Decision {
  outcome: Outcome;
  nextStep: NextStep;
  score: number;                 // 0–100, sum of finding points (capped), as in the prototype
  severity: Finding["severity"]; // worst finding
  reasons: string[];             // why this outcome, plain sentences, no invoice or bank data
  top: Finding[];                // up to 3 findings that matter most
  findings: Finding[];           // everything considered (fingerprint + message checks)
}

/** Points per severity: one high, or two mediums, reaches the prototype's HOLD_SCORE of 40. */
export const POINTS: Record<Finding["severity"], number> = { high: 45, medium: 20, low: 5, info: 0, unknown: 0 };
export const HOLD_SCORE = 40;

/** Any of these means money could go somewhere new → phone callback to the number on file. */
export const BANK_CHECKS = new Set(["bank_change_request", "first_bank_change", "bank_mismatch", "remit_change",
  "payment_change_from_unknown_sender"]);

/** Money/rhythm anomalies the internal requester can settle ("did you order this?"). */
export const CONFIRM_CHECKS = new Set(["bill_too_soon", "fixed_amount_changed", "one_time_bill", "no_billing_history",
  "amount_out_of_range", "po_mismatch", "invoice_out_of_sequence"]);

// Ported from the prototype's extractor.INJECTION: instructions aimed at an AI/automation system.
const INJECTION: RegExp[] = [
  /ignore\s+(?:all\s+|any\s+|your\s+|the\s+)*(?:previous|prior|above)?\s*(?:instructions|rules)/i,
  /disregard\s+(?:all\s+|your\s+|the\s+)*(?:previous|prior)?\s*(?:instructions|rules|policy)/i,
  /system\s+(?:notice|prompt|message)/i, /\bto\s+(?:the\s+)?ai\b/i, /\bai\s+(?:assistant|system|agent)\b/i,
  /you\s+are\s+now\b/i, /mark\s+(?:this\s+)?(?:as\s+)?(?:approved|verified)/i, /pre-?approved/i,
  /do\s+not\s+(?:flag|hold|escalate)/i, /release\s+(?:the\s+)?payment/i,
  /bypass\s+(?:the\s+)?(?:controls?|checks?|verification)/i, /approve\s+this\s+invoice/i,
];

const rule = (check: string, severity: Finding["severity"], expected: string, actual: string, explanation: string): Finding =>
  ({ check, severity, expected, actual, explanation, source: "rule" });

/** Message-level checks the fingerprint doesn't do. `authResults` = the Authentication-Results header, if any. */
export function messageChecks(msg: IncomingMessage, authResults?: string): Finding[] {
  const out: Finding[] = [];
  const text = `${msg.subject}\n${msg.body}`;
  const hits = INJECTION.filter((re) => re.test(text)).map((re) => text.match(re)![0]);
  if (hits.length) {
    out.push(rule("prompt_injection", "high", "no instructions to automated systems", hits.slice(0, 3).map((h) => `"${h}"`).join(", "),
      "The email contains instructions aimed at an AI system. Treated as hostile; the agent has no approve tool."));
  }
  const ar = (authResults ?? "").toLowerCase();
  if (ar) {
    const failed = ["spf", "dkim", "dmarc"].filter((k) => new RegExp(`${k}=(?:fail|softfail|none|permerror|temperror)`).test(ar));
    if (failed.length) {
      out.push(rule("email_auth_failed", "high", "spf, dkim and dmarc pass", `${failed.join(", ")} failed`,
        `Email authentication failed (${failed.join(", ")}): the sender may be forged.`));
    }
  }
  return out;
}

const SEV_RANK: Record<Finding["severity"], number> = { unknown: 0, info: 0, low: 1, medium: 2, high: 3 };

/**
 * Decide. Order matters and is the whole policy:
 *  1. HOLD_FRAUD_RISK: any high, any bank/remit change, score >= 40 (2+ mediums), or an unknown vendor
 *     sending an invoice (fail closed: nobody to pay, nobody to call). → phone callback to the number on file.
 *  2. HOLD_CONFIRM: otherwise, any finding that asks for requester confirmation or any money/rhythm anomaly.
 *     → "did you order this?" to the internal PO requester.
 *  3. PASS.
 * "unknown" findings (a check that couldn't run, e.g. model offline) add no points and never clear a hold.
 */
export function decide(findings: Finding[], ctx: { hasInvoice?: boolean } = {}): Decision {
  const score = Math.min(100, findings.reduce((n, f) => n + POINTS[f.severity], 0));
  const severity = findings.reduce<Finding["severity"]>((w, f) => (SEV_RANK[f.severity] > SEV_RANK[w] ? f.severity : w), "info");
  const top = [...findings].filter((f) => f.severity !== "unknown")
    .sort((a, b) => POINTS[b.severity] - POINTS[a.severity] || Number(BANK_CHECKS.has(b.check)) - Number(BANK_CHECKS.has(a.check)))
    .slice(0, 3);
  const checks = new Set(findings.map((f) => f.check));

  const fraud: string[] = [];
  if (findings.some((f) => f.severity === "high")) fraud.push("a high-risk finding");
  if ([...checks].some((c) => BANK_CHECKS.has(c))) fraud.push("a change to where the money goes");
  if (score >= HOLD_SCORE && !fraud.length) fraud.push(`risk score ${score} ≥ ${HOLD_SCORE}`);
  if (checks.has("unknown_vendor") && ctx.hasInvoice) fraud.push("an invoice from a sender not in the vendor master");
  if (fraud.length) {
    return { outcome: "HOLD_FRAUD_RISK", nextStep: "phone_callback", score, severity, top, findings,
      reasons: [`Held for ${fraud.join(", ")}. Verify by phone using the number on file, never the email.`] };
  }

  const confirm = findings.filter((f) => f.action === "confirm_with_requester" || CONFIRM_CHECKS.has(f.check));
  if (confirm.length) {
    return { outcome: "HOLD_CONFIRM", nextStep: "requester_confirmation", score, severity, top: top.length ? top : confirm.slice(0, 3), findings,
      reasons: [`Held until the requester confirms the order (${[...new Set(confirm.map((f) => f.check))].join(", ")}).`] };
  }
  return { outcome: "PASS", nextStep: "none", score, severity, top, findings, reasons: ["Nothing unusual for this vendor."] };
}
