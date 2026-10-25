// Read models for the dashboard API (T03b). Pure reads over the DB + the files the pipeline saw.
// No business logic lives here: decisions come from src/rules, state changes from src/cases.
// Every response is passed through `maskDeep` so no account-length number (6+ digits) ever leaves the API.
import { existsSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import { FIXTURES_DIR, type DB } from "../db/index.js";
import type { Finding } from "../fingerprint/types.js";
import { scanPdf } from "../fingerprint/index.js";
import { parseInvoiceText } from "../fingerprint/text.js";
import { parseEml } from "../pipeline/index.js";
import { decide } from "../rules/index.js";
import { caseEvents, mask, verifyAuditChain } from "../cases/index.js";
import { listAlerts, scrub } from "../alerts/index.js";

export interface InvoiceLine { lineNo: number; description: string | null; qty: number | null; unitPrice: number | null; amount: number | null }
export interface InvoiceView {
  invoiceNumber: string | null; invoiceDate: string | null; poNumber: string | null; amount: number | null;
  bankName: string | null; routingLast4: string | null; accountLast4: string | null; remitAddress: string | null;
  lines: InvoiceLine[]; pdfUrl: string | null;
}

export interface Paths { inboxDir: string; invoicesDir: string }

/** Last 4 digits only. Full bank numbers never leave the box. */
export const last4 = (s: string | null | undefined): string | null => {
  const d = (s ?? "").replace(/\D/g, "");
  return d ? d.slice(-4) : null;
};

/** Backstop: mask every 6+ digit run in every string of a response. */
export function maskDeep<T>(v: T): T {
  if (typeof v === "string") return mask(v) as T;
  if (Array.isArray(v)) return v.map(maskDeep) as T;
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, maskDeep(x)])) as T;
  return v;
}

const num = (s: string | undefined) => (s === undefined ? null : Number(s.replace(/,/g, "")));

/** Line items off an invoice PDF's text ("1. Compound microscopes\n6\n520.00\n3,120.00"). */
export function parseInvoiceLines(text: string): InvoiceLine[] {
  const re = /^(\d+)\.\s+([^\n]+)\n\s*([\d.,]+)\n\s*([\d,]+\.\d{2})\n\s*([\d,]+\.\d{2})\s*$/gm;
  return [...text.matchAll(re)].map((m) => ({ lineNo: Number(m[1]), description: m[2].trim(), qty: num(m[3]), unitPrice: num(m[4]), amount: num(m[5]) }));
}

let incomingFixtures: Map<string, any> | null = null;
function incomingFixture(id: string): any {
  if (!incomingFixtures) {
    try {
      const rows = JSON.parse(readFileSync(join(FIXTURES_DIR, "incoming.json"), "utf8")) as any[];
      incomingFixtures = new Map(rows.map((r) => [r.id, r]));
    } catch { incomingFixtures = new Map(); }
  }
  return incomingFixtures.get(id) ?? null;
}

const emailIdOf = (sourceFile: string | null) => (sourceFile ? basename(sourceFile).replace(/\.eml$/i, "") : null);

function pdfUrlFor(paths: Paths, name: string | null | undefined): string | null {
  if (!name || !/\.pdf$/i.test(name)) return null;
  return existsSync(join(paths.invoicesDir, basename(name))) ? `/files/invoices/${encodeURIComponent(basename(name))}` : null;
}

/**
 * The invoice the incoming email carried, read the way the pipeline reads it: the attached PDF first
 * (parseInvoiceText, as processEml does), else the invoice fields the demo fixture says the email carries.
 */
export async function currentInvoice(db: DB, paths: Paths, hold: any): Promise<InvoiceView | null> {
  const emailId = emailIdOf(hold.source_file);
  const row = emailId ? (db.prepare("SELECT attachments FROM emails WHERE id = ?").get(emailId) as any) : null;
  const attachments: string[] = row?.attachments ? JSON.parse(row.attachments) : [];
  const fx = emailId ? incomingFixture(emailId) : null;

  let fromPdf: ReturnType<typeof parseInvoiceText> | null = null;
  let lines: InvoiceLine[] = [];
  const emlPath = hold.source_file ? join(paths.inboxDir, basename(hold.source_file)) : null;
  if (emlPath && existsSync(emlPath)) {
    const { msg } = await parseEml(emlPath);
    if (msg.pdfPaths?.length) {
      const text = (await scanPdf(msg.pdfPaths[0])).text;
      fromPdf = parseInvoiceText(text);
      lines = parseInvoiceLines(text);
    }
  }
  const inv = fx?.invoice ?? null;
  if (!fromPdf?.invoice_number && !inv) return null;
  const bank = fromPdf?.bank ?? inv?.bank ?? {};
  if (!lines.length && Array.isArray(inv?.lines)) {
    lines = inv.lines.map((l: any, i: number) => ({ lineNo: i + 1, description: l.description ?? null, qty: l.qty ?? null, unitPrice: l.unit_price ?? null, amount: l.amount ?? null }));
  }
  return {
    invoiceNumber: fromPdf?.invoice_number ?? inv?.invoice_number ?? hold.invoice_id ?? null,
    invoiceDate: fromPdf?.invoice_date ?? inv?.invoice_date ?? null,
    poNumber: fromPdf?.po_number ?? inv?.po_number ?? null,
    amount: fromPdf?.amount ?? inv?.amount ?? null,
    bankName: bank.bank_name ?? null,
    routingLast4: last4(bank.routing),
    accountLast4: last4(bank.account),
    remitAddress: bank.remit_address ?? null,
    lines,
    pdfUrl: pdfUrlFor(paths, attachments.find((a) => /\.pdf$/i.test(a))),
  };
}

/** The vendor's most recent invoice we actually paid or approved: the "last real one" to compare against. */
export function lastRealInvoice(db: DB, paths: Paths, vendorId: string | null): InvoiceView | null {
  if (!vendorId) return null;
  const i = db.prepare(`SELECT * FROM invoices WHERE vendor_id = ? AND status IN ('paid','approved')
                        ORDER BY invoice_date DESC, id DESC LIMIT 1`).get(vendorId) as any;
  if (!i) return null;
  const lines = db.prepare("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no").all(i.id) as any[];
  return {
    invoiceNumber: i.invoice_number, invoiceDate: i.invoice_date, poNumber: i.po_number, amount: i.amount,
    bankName: i.bank_name, routingLast4: last4(i.routing), accountLast4: last4(i.account), remitAddress: i.remit_address,
    lines: lines.map((l) => ({ lineNo: l.line_no, description: l.description, qty: l.qty, unitPrice: l.unit_price, amount: l.amount })),
    pdfUrl: pdfUrlFor(paths, `${i.invoice_number}.pdf`),
  };
}

/** Any stored invoice by id, as an InvoiceView (for the dashboard's invoice list). */
export function invoiceById(db: DB, paths: Paths, id: string): (InvoiceView & { id: string; vendorId: string; status: string }) | null {
  const i = db.prepare("SELECT * FROM invoices WHERE id = ?").get(id) as any;
  if (!i) return null;
  const lines = db.prepare("SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_no").all(i.id) as any[];
  return {
    id: i.id, vendorId: i.vendor_id, status: i.status,
    invoiceNumber: i.invoice_number, invoiceDate: i.invoice_date, poNumber: i.po_number, amount: i.amount,
    bankName: i.bank_name, routingLast4: last4(i.routing), accountLast4: last4(i.account), remitAddress: i.remit_address,
    lines: lines.map((l) => ({ lineNo: l.line_no, description: l.description, qty: l.qty, unitPrice: l.unit_price, amount: l.amount })),
    pdfUrl: pdfUrlFor(paths, `${i.invoice_number}.pdf`),
  };
}

/** Every invoice the dashboard lists: open/closed cases first (newest first), then stored invoices (newest first). */
export async function invoiceListViews(db: DB, cache: CaseCache) {
  const caseRows = (await listCaseViews(db, cache)).map((c: any) => ({
    id: c.id, kind: "case" as const, caseId: c.id, vendorName: c.vendorName, invoiceNumber: c.invoiceNumber ?? null,
    date: c.createdAt, amount: c.amount ?? null,
    risk: c.state === "APPROVED" ? "cleared" : c.outcome === "HOLD_FRAUD_RISK" ? "fraud" : c.outcome === "HOLD_CONFIRM" ? "confirm" : "cleared",
    state: c.state,
  }));
  const stored = (db.prepare(`SELECT i.id, i.invoice_number, i.invoice_date, i.amount, i.status, v.name AS vendor_name
                              FROM invoices i JOIN vendors v ON v.id = i.vendor_id
                              WHERE i.status IN ('paid','approved') ORDER BY i.invoice_date DESC, i.id DESC`).all() as any[])
    .map((r) => ({ id: r.id, kind: "invoice" as const, caseId: null, vendorName: r.vendor_name, invoiceNumber: r.invoice_number,
                   date: r.invoice_date, amount: r.amount, risk: "cleared" as const, state: r.status === "paid" ? "PAID" : "APPROVED" }));
  return [...caseRows, ...stored];
}

/** Per-case derived data, cached: the PDF parse is the only slow part. Clear on demo reset. */
export class CaseCache {
  private invoices = new Map<string, Promise<InvoiceView | null>>();
  constructor(private paths: Paths) {}
  invoice(db: DB, hold: any) {
    let p = this.invoices.get(hold.id);
    if (!p) {
      p = currentInvoice(db, this.paths, hold).catch(() => null);
      this.invoices.set(hold.id, p);
    }
    return p;
  }
  clear() { this.invoices.clear(); }
}

function findingsOf(hold: any): Finding[] {
  try { return JSON.parse(hold.findings) as Finding[]; } catch { return []; }
}

/** Re-run the deterministic decide() on the stored findings for its plain reasons and top checks. */
function decisionExtras(hold: any, hasInvoice: boolean) {
  const d = decide(findingsOf(hold), { hasInvoice });
  return { reasons: d.reasons, topChecks: d.top.map((f) => f.check) };
}

async function summary(db: DB, cache: CaseCache, hold: any) {
  const inv = await cache.invoice(db, hold);
  const vendorName = hold.vendor_id ? ((db.prepare("SELECT name FROM vendors WHERE id = ?").get(hold.vendor_id) as any)?.name ?? null) : null;
  return {
    id: hold.id as string,
    vendorId: hold.vendor_id ?? null,
    vendorName,
    invoiceNumber: hold.invoice_id ?? inv?.invoiceNumber ?? null,
    amount: inv?.amount ?? null,
    outcome: hold.outcome,
    nextStep: hold.next_step,
    state: hold.state,
    status: hold.status,
    severity: hold.severity,
    score: hold.score,
    reason: hold.reason,
    createdAt: hold.created_at,
    topChecks: decisionExtras(hold, !!inv).topChecks,
  };
}

export async function listCaseViews(db: DB, cache: CaseCache) {
  const holds = db.prepare("SELECT * FROM holds ORDER BY created_at DESC, id DESC").all() as any[];
  return maskDeep(await Promise.all(holds.map((h) => summary(db, cache, h))));
}

export async function caseDetail(db: DB, cache: CaseCache, paths: Paths, hold: any) {
  const base = await summary(db, cache, hold);
  const current = await cache.invoice(db, hold);
  const v = hold.vendor_id ? (db.prepare("SELECT * FROM vendors WHERE id = ?").get(hold.vendor_id) as any) : null;
  const contacts = v ? (db.prepare("SELECT name, email, role FROM vendor_contacts WHERE vendor_id = ? ORDER BY rowid").all(v.id) as any[]) : [];
  const bank = v ? (db.prepare("SELECT * FROM vendor_banks WHERE vendor_id = ? AND active = 1 ORDER BY rowid DESC LIMIT 1").get(v.id) as any) : null;

  const emailId = emailIdOf(hold.source_file);
  let email: any = null;
  const e = emailId ? (db.prepare("SELECT * FROM emails WHERE id = ?").get(emailId) as any) : null;
  if (e) {
    email = { from: e.from_addr, fromName: e.from_name, replyTo: e.reply_to, to: e.to_addr, subject: e.subject, date: e.date, body: e.body ?? "" };
  } else if (hold.source_file && existsSync(join(paths.inboxDir, basename(hold.source_file)))) {
    const { msg } = await parseEml(join(paths.inboxDir, basename(hold.source_file)));
    email = { from: msg.from, fromName: msg.fromName ?? null, replyTo: msg.replyTo ?? null, to: null, subject: msg.subject, date: msg.date, body: msg.body };
  }
  if (email) {
    const { body, ...rest } = email;
    email = { ...rest, bodyExcerpt: body.length > 1200 ? `${body.slice(0, 1200)}…` : body };
  }

  const callbacks = (db.prepare("SELECT * FROM callbacks WHERE hold_id = ? ORDER BY created_at").all(hold.id) as any[]).map((c) => ({
    id: c.id, phone: c.phone, script: c.script, status: c.status, outcome: c.outcome, createdAt: c.created_at, completedAt: c.completed_at,
  }));
  const requesterChecks = (db.prepare("SELECT * FROM requester_checks WHERE hold_id = ? ORDER BY created_at").all(hold.id) as any[]).map((r) => ({
    id: r.id, recipientName: r.recipient_name, recipientContact: r.recipient_contact, recipientDepartment: r.recipient_department,
    text: r.text, source: r.source, status: r.status, reply: r.reply, createdAt: r.created_at,
  }));
  const events = caseEvents(db, hold.id).map((x) => {
    let detail: unknown = x.detail_json;
    try { detail = JSON.parse(x.detail_json); } catch { /* keep raw */ }
    return { id: x.id, ts: x.ts, actor: x.actor, action: x.action, detail };
  });
  const { reasons } = decisionExtras(hold, !!current);

  return maskDeep({
    case: { ...base, resolvedAt: hold.resolved_at ?? null, resolvedBy: hold.resolved_by ?? null },
    vendor: v ? { id: v.id, name: v.name, domain: v.domain, phoneOnFile: v.phone_on_file, address: v.address, contacts } : null,
    bankOnFile: bank ? { bankName: bank.bank_name, routingLast4: last4(bank.routing), accountLast4: last4(bank.account),
                         remitAddress: bank.remit_address, verifiedAt: bank.verified_at } : null,
    invoice: { current, lastReal: lastRealInvoice(db, paths, hold.vendor_id) },
    email,
    findings: findingsOf(hold),
    decision: { outcome: hold.outcome, nextStep: hold.next_step, score: hold.score, severity: hold.severity, reasons },
    callbacks,
    requesterChecks,
    audit: { events, chainOk: verifyAuditChain(db).ok, count: events.length },
  });
}

export function alertViews(db: DB, limit = 200) {
  return maskDeep(listAlerts(db, limit).map((a) => ({
    id: a.id,
    ts: a.created_at,
    caseId: a.case_id,
    text: scrub(`${a.headline}. ${a.vendor_name ?? "Unknown vendor"}. Why: ${a.reason}.`),
    channel: a.slack_sent ? "slack" : "in-app",
    sent: !!a.slack_sent,
    vendorName: a.vendor_name ?? null,
    outcome: a.outcome,
    state: a.state ?? null,
    headline: a.headline,
    reason: a.reason,
  })));
}

export function vendorViews(db: DB) {
  return db.prepare(`SELECT v.id, v.name, v.domain, v.phone_on_file AS phoneOnFile,
      (SELECT COUNT(*) FROM invoices i WHERE i.vendor_id = v.id) AS invoices,
      (SELECT MAX(paid_on) FROM payments p WHERE p.vendor_id = v.id) AS lastPaid
    FROM vendors v ORDER BY v.id`).all() as any[];
}

const localDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Dashboard counters. "held" = open (non-terminal) cases; awaiting* split them by who must answer. */
export async function statusCounts(db: DB, cache: CaseCache) {
  const open = db.prepare("SELECT * FROM holds WHERE state NOT IN ('APPROVED','REJECTED')").all() as any[];
  let heldAmount = 0;
  for (const h of open) heldAmount += (await cache.invoice(db, h))?.amount ?? 0;
  const processed = db.prepare("SELECT processed_at FROM processed_messages").all() as any[];
  const today = localDay(new Date());
  const checkedToday = processed.filter((p) => localDay(new Date(p.processed_at)) === today).length;
  const passed = (db.prepare("SELECT COUNT(*) AS n FROM processed_messages WHERE outcome = 'PASS'").get() as any).n as number;
  const approved = (db.prepare("SELECT COUNT(*) AS n FROM holds WHERE state = 'APPROVED'").get() as any).n as number;
  return {
    heldAmount: Math.round(heldAmount * 100) / 100,
    held: open.length,
    checkedToday,
    cleared: passed + approved,
    awaitingVendor: open.filter((h) => h.next_step === "phone_callback").length,
    awaitingRequester: open.filter((h) => h.next_step === "requester_confirmation").length,
  };
}
