// SQLite access for Invoice Guard. Uses Node's built-in node:sqlite (no native build on the GB10).
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = join(here, "..", "..");
export const FIXTURES_DIR = join(REPO_ROOT, "data", "fixtures");

export type DB = DatabaseSync;

/** Open (or create) the database and apply the schema. Use ":memory:" in tests. */
export function openDb(path = process.env.DB_PATH ?? join(REPO_ROOT, "data", "invoice-guard.db")): DB {
  const db = new DatabaseSync(path);
  db.exec("PRAGMA foreign_keys = ON;");
  db.exec(readFileSync(join(here, "schema.sql"), "utf8"));
  return db;
}

function fixture<T>(name: string, dir = FIXTURES_DIR): T {
  return JSON.parse(readFileSync(join(dir, name), "utf8")) as T;
}

interface Bank { bank_name: string; routing: string; account: string; remit_address?: string }
interface VendorFx {
  id: string; name: string; domain: string; address: string; phone_on_file: string;
  billing_day: number; terms: string; invoice_prefix: string; bank: Bank;
  contacts: { name: string; email: string; role: string }[];
  po: { number: string; description: string; annual_limit: number; monthly_min: number; monthly_max: number;
        requester_name?: string; requester_contact?: string; requester_department?: string };
}
interface InvoiceFx {
  id: string; vendor_id: string; invoice_number: string; invoice_date: string; po_number: string;
  amount: number; bank: Bank; status: string; source_email_id: string | null;
  lines: { description: string; qty: number; unit_price: number; amount: number }[];
}
interface PaymentFx { id: string; invoice_id: string; vendor_id: string; amount: number; paid_on: string; routing: string; account: string; method: string }
interface EmailFx {
  id: string; vendor_id: string | null; from: string; from_name: string; reply_to: string | null; to: string;
  date: string; subject: string; body: string; attachments: string[]; kind: string; scenario: string | null;
}

/** Wipe and load data/fixtures into the database. Returns row counts. */
export function loadFixtures(db: DB, dir = FIXTURES_DIR): Record<string, number> {
  const vendors = fixture<VendorFx[]>("vendors.json", dir);
  const invoices = fixture<InvoiceFx[]>("invoices.json", dir);
  const payments = fixture<PaymentFx[]>("payments.json", dir);
  const emails = [...fixture<EmailFx[]>("emails.json", dir), ...fixture<EmailFx[]>("incoming.json", dir)];

  db.exec("BEGIN");
  try {
    for (const t of ["callbacks", "holds", "emails", "payments", "invoice_lines", "invoices",
                     "purchase_orders", "vendor_banks", "vendor_contacts", "vendors"]) {
      db.exec(`DELETE FROM ${t}`);
    }
    const v = db.prepare("INSERT INTO vendors VALUES (?,?,?,?,?,?,?,?)");
    const c = db.prepare("INSERT INTO vendor_contacts VALUES (?,?,?,?)");
    const b = db.prepare("INSERT INTO vendor_banks (vendor_id,bank_name,routing,account,remit_address,active,verified_at,verified_by) VALUES (?,?,?,?,?,1,?,?)");
    const po = db.prepare(`INSERT INTO purchase_orders (number, vendor_id, description, annual_limit, monthly_min, monthly_max,
      requester_name, requester_contact, requester_department) VALUES (?,?,?,?,?,?,?,?,?)`);
    for (const x of vendors) {
      v.run(x.id, x.name, x.domain, x.address, x.phone_on_file, x.billing_day, x.terms, x.invoice_prefix);
      for (const k of x.contacts) c.run(x.id, k.name, k.email, k.role);
      b.run(x.id, x.bank.bank_name, x.bank.routing, x.bank.account, x.bank.remit_address ?? null, "2025-01-15", "onboarding");
      po.run(x.po.number, x.id, x.po.description, x.po.annual_limit, x.po.monthly_min, x.po.monthly_max,
             x.po.requester_name ?? null, x.po.requester_contact ?? null, x.po.requester_department ?? null);
    }
    const i = db.prepare("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?)");
    const l = db.prepare("INSERT INTO invoice_lines VALUES (?,?,?,?,?,?)");
    for (const x of invoices) {
      i.run(x.id, x.vendor_id, x.invoice_number, x.invoice_date, x.po_number, x.amount,
            x.bank.bank_name, x.bank.routing, x.bank.account, x.bank.remit_address ?? null, x.status, x.source_email_id);
      x.lines.forEach((ln, n) => l.run(x.id, n + 1, ln.description, ln.qty, ln.unit_price, ln.amount));
    }
    const p = db.prepare("INSERT INTO payments VALUES (?,?,?,?,?,?,?,?)");
    for (const x of payments) p.run(x.id, x.invoice_id, x.vendor_id, x.amount, x.paid_on, x.routing, x.account, x.method);
    const e = db.prepare("INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?,?,?)");
    for (const x of emails) {
      e.run(x.id, x.vendor_id, x.from, x.from_name, x.reply_to, x.to, x.date, x.subject, x.body,
            JSON.stringify(x.attachments ?? []), x.kind, x.scenario);
    }
    db.exec("COMMIT");
  } catch (err) {
    db.exec("ROLLBACK");
    throw err;
  }
  return { vendors: vendors.length, invoices: invoices.length, payments: payments.length, emails: emails.length };
}
