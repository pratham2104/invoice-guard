// Pipeline (T15): .eml → fingerprint → rules → case + audit + alert. Each email is processed once.
// Port of prerna-1's prototype pipeline.py / parser.py onto the TypeScript modules.
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { simpleParser } from "mailparser";
import type { DB } from "../db/index.js";
import type { IncomingMessage } from "../fingerprint/types.js";
import type { LlmClient } from "../fingerprint/llm.js";
import { fingerprint, scanPdf } from "../fingerprint/index.js";
import { parseInvoiceText } from "../fingerprint/text.js";
import { decide, messageChecks, type Decision } from "../rules/index.js";
import { openCase } from "../cases/index.js";
import { raiseAlert, type Alert, type SlackResult } from "../alerts/index.js";

export interface ParsedEml { messageId: string; msg: IncomingMessage; authResults?: string }

/** Parse an .eml file. PDF attachments are written to a private temp dir so the PDF checks can read them. */
export async function parseEml(path: string): Promise<ParsedEml> {
  const m = await simpleParser(readFileSync(path));
  const from = m.from?.value?.[0];
  const replyTo = m.replyTo?.value?.[0]?.address ?? null;
  const pdfs = (m.attachments ?? []).filter((a) => a.contentType === "application/pdf" || /\.pdf$/i.test(a.filename ?? ""));
  let pdfPaths: string[] = [];
  if (pdfs.length) {
    const dir = mkdtempSync(join(tmpdir(), "ig-att-"));
    pdfPaths = pdfs.map((a, i) => {
      const p = join(dir, `${i}-${basename(a.filename ?? "attachment.pdf").replace(/[^\w.-]/g, "_")}`);
      writeFileSync(p, a.content);
      return p;
    });
  }
  const auth = m.headers.get("authentication-results");
  const messageId = m.messageId ?? `<${basename(path)}>`;
  return {
    messageId,
    authResults: auth ? String(auth) : undefined,
    msg: {
      id: messageId,
      from: (from?.address ?? "").toLowerCase(),
      fromName: from?.name ?? "",
      replyTo: replyTo ? replyTo.toLowerCase() : null,
      date: (m.date ?? new Date()).toISOString(),
      subject: m.subject ?? "",
      body: m.text ?? "",
      pdfPaths,
    },
  };
}

export interface ProcessResult {
  file: string;
  messageId: string;
  skipped: boolean;
  decision: Decision | null;
  vendorId: string | null;
  vendorName: string | null;
  caseId: string | null;
  alert?: { alert: Alert; slack: SlackResult };
}

export interface ProcessOptions { llm?: LlmClient | false; slackWebhookUrl?: string; fetchImpl?: typeof fetch }

export async function processEml(db: DB, path: string, opts: ProcessOptions = {}): Promise<ProcessResult> {
  const { messageId, msg, authResults } = await parseEml(path);
  const file = basename(path);
  const seen = db.prepare("SELECT outcome, case_id FROM processed_messages WHERE message_id = ?").get(messageId) as any;
  if (seen) return { file, messageId, skipped: true, decision: null, vendorId: null, vendorName: null, caseId: seen.case_id ?? null };

  const fp = await fingerprint(db, msg, { llm: opts.llm });
  const findings = [...fp.findings, ...messageChecks(msg, authResults)];
  const hasInvoice = !!msg.invoice || !!msg.pdfPaths?.length;
  const decision = decide(findings, { hasInvoice });
  const vendorName = fp.vendorId ? ((db.prepare("SELECT name FROM vendors WHERE id = ?").get(fp.vendorId) as any)?.name ?? null) : null;

  // invoice fields for the case record and the requester draft (read off the PDF if the email didn't carry them)
  if (!msg.invoice && msg.pdfPaths?.length) {
    const inv = parseInvoiceText((await scanPdf(msg.pdfPaths[0])).text);
    if (inv.invoice_number && inv.amount !== undefined) {
      msg.invoice = { invoice_number: inv.invoice_number, invoice_date: inv.invoice_date ?? "", po_number: inv.po_number ?? null, amount: inv.amount, bank: inv.bank };
    }
  }

  let caseId: string | null = null;
  let alert: ProcessResult["alert"];
  db.exec("BEGIN");
  try {
    if (decision.outcome !== "PASS") {
      const opened = await openCase(db, { decision, vendorId: fp.vendorId, messageId, invoiceNumber: msg.invoice?.invoice_number ?? null, msg, sourceFile: file }, { llm: opts.llm });
      caseId = opened.caseId;
    }
    db.prepare("INSERT INTO processed_messages (message_id, file, processed_at, outcome, case_id) VALUES (?,?,?,?,?)")
      .run(messageId, file, new Date().toISOString(), decision.outcome, caseId);
    db.exec("COMMIT");
  } catch (err) {
    db.exec("ROLLBACK");
    throw err;
  }
  if (caseId) {
    alert = await raiseAlert(db, { caseId, vendorName, outcome: decision.outcome, state: "OPEN", top: decision.top },
                             { webhookUrl: opts.slackWebhookUrl, fetchImpl: opts.fetchImpl });
  }
  return { file, messageId, skipped: false, decision, vendorId: fp.vendorId, vendorName, caseId, alert };
}

/** Process every .eml in a folder, in filename order. */
export async function processDir(db: DB, dir: string, opts: ProcessOptions = {}): Promise<ProcessResult[]> {
  const files = readdirSync(dir).filter((f) => f.endsWith(".eml") && !f.startsWith("._")).sort();
  const out: ProcessResult[] = [];
  for (const f of files) out.push(await processEml(db, join(dir, f), opts));
  return out;
}
