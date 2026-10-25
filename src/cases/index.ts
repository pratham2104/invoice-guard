// Cases (T15): state machine, approval controls, tamper-evident audit log.
// Ported from Prerna's prototype (prerna-1, prototype/ap-guard/apguard/cases.py).
//
//   OPEN ─start_verification─▶ AWAITING_VENDOR    (HOLD_FRAUD_RISK: phone callback to the number on file)
//        └────────────────────▶ AWAITING_REQUESTER (HOLD_CONFIRM: "did you order this?" to the PO requester)
//   AWAITING_* ─record_confirmation(yes)─▶ READY_FOR_APPROVAL ─approve (manager, not the verifier)─▶ APPROVED
//   AWAITING_* ─record_confirmation(no)──▶ REJECTED;  any non-terminal ─reject─▶ REJECTED
//
// The agent opens cases and drafts the callback / requester message. Every step after that is human-only.
import { createHash } from "node:crypto";
import type { DB } from "../db/index.js";
import type { IncomingMessage } from "../fingerprint/types.js";
import type { LlmClient } from "../fingerprint/llm.js";
import { draftRequesterConfirmation } from "../fingerprint/confirm.js";
import type { Decision } from "../rules/index.js";

export type CaseState = "OPEN" | "AWAITING_VENDOR" | "AWAITING_REQUESTER" | "READY_FOR_APPROVAL" | "APPROVED" | "REJECTED";
export const TERMINAL = new Set<CaseState>(["APPROVED", "REJECTED"]);
export const AGENT = "agent";

export class ControlError extends Error {
  constructor(message: string) { super(message); this.name = "ControlError"; }
}

/** Users and roles (Slack user IDs in production). Override with IG_USERS='{"U012":"ap_manager"}'. */
export function users(): Record<string, string> {
  if (process.env.IG_USERS) return JSON.parse(process.env.IG_USERS);
  return { "janet.kim": "ap_clerk", "omar.reyes": "ap_manager", "pat.lee": "ap_manager" };
}
export const APPROVER_ROLES = new Set(["ap_manager"]);

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

/** Mask anything account-length (6+ digits) to its last 4, for storage and audit. */
export function mask(s: string): string {
  return s.replace(/\d{6,}/g, (d) => `••••${d.slice(-4)}`);
}

// ------------------------------------------------------------------ audit log
function hashEvent(prev: string, caseId: string, ts: string, actor: string, action: string, detail: string): string {
  return createHash("sha256").update([prev, caseId, ts, actor, action, detail].join("|")).digest("hex");
}

export function addEvent(db: DB, caseId: string, actor: string, action: string, detail: Record<string, unknown> = {}) {
  const detailJson = mask(JSON.stringify(detail, Object.keys(detail).sort()));
  const prev = (db.prepare("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1").get() as any)?.hash ?? "";
  const ts = now();
  db.prepare("INSERT INTO audit_events (case_id, ts, actor, action, detail_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?)")
    .run(caseId, ts, actor, action, detailJson, prev, hashEvent(prev, caseId, ts, actor, action, detailJson));
}

/** Recompute the whole chain. Any edited, deleted or reordered row breaks it. */
export function verifyAuditChain(db: DB): { ok: boolean; firstBadId: number | null; events: number } {
  let prev = "";
  const rows = db.prepare("SELECT * FROM audit_events ORDER BY id").all() as any[];
  for (const r of rows) {
    if (r.prev_hash !== prev || r.hash !== hashEvent(prev, r.case_id, r.ts, r.actor, r.action, r.detail_json)) {
      return { ok: false, firstBadId: r.id, events: rows.length };
    }
    prev = r.hash;
  }
  return { ok: true, firstBadId: null, events: rows.length };
}

export function caseEvents(db: DB, caseId: string): any[] {
  return db.prepare("SELECT id, ts, actor, action, detail_json FROM audit_events WHERE case_id = ? ORDER BY id").all(caseId) as any[];
}

// ------------------------------------------------------------------ cases
export function getCase(db: DB, caseId: string): any {
  const c = db.prepare("SELECT * FROM holds WHERE id = ?").get(caseId);
  if (!c) throw new ControlError(`No such case: ${caseId}`);
  return c;
}

export function listCases(db: DB): any[] {
  return db.prepare("SELECT id, vendor_id, outcome, state, severity, score, created_at FROM holds ORDER BY id").all() as any[];
}

/** Callback script to the vendor master's phone number. Never anything from the suspicious message. */
export function draftCallback(db: DB, vendorId: string) {
  const v = db.prepare("SELECT name, phone_on_file FROM vendors WHERE id = ?").get(vendorId) as any;
  const contact = db.prepare("SELECT name FROM vendor_contacts WHERE vendor_id = ? ORDER BY rowid LIMIT 1").get(vendorId) as any;
  const script = [
    `Call ONLY ${v.phone_on_file} (from the vendor master, not from the email).`,
    `Ask for ${contact?.name ?? "the registered contact"} at ${v.name}.`,
    `Ask: did ${v.name} recently send a request about an invoice payment or bank details?`,
    "If they say a bank change was requested: ask them to read back the last four digits of the NEW account. Do not read out anything from the email.",
    "Record the result in Invoice Guard (confirmed or denied).",
  ];
  return { phone: v.phone_on_file as string, contact: (contact?.name ?? null) as string | null, script };
}

export interface OpenCaseInput {
  decision: Decision;
  vendorId: string | null;
  messageId: string;
  invoiceNumber?: string | null;
  msg: IncomingMessage;
  sourceFile?: string;
}

/** Agent action: open a case for a HOLD and draft the next step. Nothing is sent. */
export async function openCase(db: DB, input: OpenCaseInput, opts: { llm?: LlmClient | false } = {}) {
  const { decision: d } = input;
  if (d.outcome === "PASS") throw new ControlError("PASS decisions don't open cases.");
  const n = (db.prepare("SELECT COUNT(*) AS n FROM holds").get() as any).n + 1;
  const caseId = `HOLD-${String(n).padStart(4, "0")}`;
  const ts = now();
  db.prepare(`INSERT INTO holds (id, invoice_id, email_id, vendor_id, reason, findings, status, outcome, next_step, state, severity, score,
              source_file, created_at, updated_at) VALUES (?,?,?,?,?,?, 'held', ?,?, 'OPEN', ?,?,?,?,?)`)
    .run(caseId, input.invoiceNumber ?? null, input.messageId, input.vendorId, d.reasons.join(" "), mask(JSON.stringify(d.findings)),
         d.outcome, d.nextStep, d.severity, d.score, input.sourceFile ?? null, ts, ts);
  addEvent(db, caseId, AGENT, "case_opened", { outcome: d.outcome, score: d.score, severity: d.severity, checks: d.findings.map((f) => f.check) });

  let callback: ReturnType<typeof draftCallback> | null = null;
  let requester: Awaited<ReturnType<typeof draftRequesterConfirmation>> = null;
  if (d.nextStep === "phone_callback") {
    if (input.vendorId) {
      callback = draftCallback(db, input.vendorId);
      db.prepare("INSERT INTO callbacks (id, hold_id, vendor_id, phone, script, status, created_at) VALUES (?,?,?,?,?, 'open', ?)")
        .run(`CB-${caseId}`, caseId, input.vendorId, callback.phone, callback.script.join("\n"), ts);
      addEvent(db, caseId, AGENT, "callback_drafted", { phone: callback.phone, contact: callback.contact });
    } else {
      addEvent(db, caseId, AGENT, "no_vendor_on_file", { note: "sender not in the vendor master: nobody to call; reject or onboard the vendor first" });
    }
  } else if (input.vendorId) {
    requester = await draftRequesterConfirmation(db, input.vendorId, input.msg, d.findings, { llm: opts.llm, force: true });
    if (requester) {
      db.prepare(`INSERT INTO requester_checks (id, hold_id, recipient_name, recipient_contact, recipient_department, text, source, status, created_at)
                  VALUES (?,?,?,?,?,?,?, 'open', ?)`)
        .run(`RQ-${caseId}`, caseId, requester.recipient?.name ?? null, requester.recipient?.contact ?? null,
             requester.recipient?.department ?? null, requester.text, requester.source, ts);
      addEvent(db, caseId, AGENT, "requester_check_drafted", { to: requester.recipient?.name ?? "AP lead", source: requester.source });
    }
  }
  return { caseId, callback, requester };
}

function requireHuman(user: string): string {
  if (user === AGENT) throw new ControlError("human-only action: the agent can open cases and draft messages, nothing more.");
  const role = users()[user];
  if (!role) throw new ControlError(`Unknown user '${user}'.`);
  return role;
}

function setState(db: DB, caseId: string, state: CaseState, extra: Record<string, string | null> = {}) {
  const cols = Object.keys(extra).map((k) => `, ${k} = ?`).join("");
  db.prepare(`UPDATE holds SET state = ?, updated_at = ?${cols} WHERE id = ?`).run(state, now(), ...Object.values(extra), caseId);
}

/** Human kicks off the out-of-band check: phone callback (fraud) or requester question (confirm). */
export function startVerification(db: DB, caseId: string, user: string) {
  requireHuman(user);
  const c = getCase(db, caseId);
  if (c.state !== "OPEN") throw new ControlError(`Cannot start verification from state ${c.state}.`);
  const next: CaseState = c.next_step === "requester_confirmation" ? "AWAITING_REQUESTER" : "AWAITING_VENDOR";
  setState(db, caseId, next, { verification_started_by: user });
  if (next === "AWAITING_VENDOR") {
    const cb = db.prepare("SELECT phone, script FROM callbacks WHERE hold_id = ?").get(caseId) as any;
    addEvent(db, caseId, user, "verification_started", { method: "phone", callback_phone: cb?.phone ?? null });
    return { state: next, phone: cb?.phone ?? null, script: cb?.script ?? null };
  }
  const rq = db.prepare("SELECT recipient_name, recipient_contact, text FROM requester_checks WHERE hold_id = ?").get(caseId) as any;
  addEvent(db, caseId, user, "verification_started", { method: "requester", to: rq?.recipient_name ?? "AP lead" });
  return { state: next, recipient: rq?.recipient_contact ?? null, text: rq?.text ?? null };
}

/** Log the answer from the TRUSTED party (vendor by phone on file, or the internal requester). */
export function recordConfirmation(db: DB, caseId: string, user: string, confirmed: boolean, note = "") {
  requireHuman(user);
  const c = getCase(db, caseId);
  if (c.state !== "AWAITING_VENDOR" && c.state !== "AWAITING_REQUESTER") throw new ControlError(`Cannot record confirmation from state ${c.state}.`);
  const ts = now();
  if (c.state === "AWAITING_VENDOR") {
    db.prepare("UPDATE callbacks SET status = ?, outcome = ?, completed_at = ? WHERE hold_id = ?")
      .run(confirmed ? "confirmed_legit" : "confirmed_fraud", note, ts, caseId);
    addEvent(db, caseId, user, "vendor_confirmation", { confirmed, note });
  } else {
    db.prepare("UPDATE requester_checks SET status = ?, reply = ?, completed_at = ? WHERE hold_id = ?")
      .run(confirmed ? "confirmed" : "denied", note, ts, caseId);
    addEvent(db, caseId, user, "requester_confirmation", { confirmed, note });
  }
  if (confirmed) setState(db, caseId, "READY_FOR_APPROVAL");
  else {
    setState(db, caseId, "REJECTED", { status: "rejected", resolved_at: ts, resolved_by: user });
    addEvent(db, caseId, user, "rejected", { reason: c.state === "AWAITING_VENDOR" ? "vendor denied the request" : "requester did not order this" });
  }
}

/** Release the payment. Manager only, after verification, and not the person who verified. */
export function approve(db: DB, caseId: string, user: string) {
  const role = requireHuman(user);
  const c = getCase(db, caseId);
  if (!APPROVER_ROLES.has(role)) throw new ControlError(`${user} (role: ${role}) is not allowed to approve.`);
  if (c.state !== "READY_FOR_APPROVAL") throw new ControlError(`Cannot approve from state ${c.state}: verification is required first.`);
  if (c.verification_started_by === user) throw new ControlError("Segregation of duties: the approver must differ from the person who ran verification.");
  const ts = now();
  setState(db, caseId, "APPROVED", { status: "released", resolved_at: ts, resolved_by: user });
  addEvent(db, caseId, user, "approved", {});
}

export function reject(db: DB, caseId: string, user: string, reason = "") {
  requireHuman(user);
  const c = getCase(db, caseId);
  if (TERMINAL.has(c.state)) throw new ControlError(`Case already ${c.state}.`);
  const ts = now();
  setState(db, caseId, "REJECTED", { status: "rejected", resolved_at: ts, resolved_by: user });
  addEvent(db, caseId, user, "rejected", { reason });
}
