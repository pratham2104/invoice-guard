// Billing rhythm checks + requester confirmation drafts.
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, FIXTURES_DIR } from "../db/index.js";
import { fingerprint, messageFromFixture, buildProfile, learnRhythm, draftRequesterConfirmation } from "./index.js";
import type { IncomingMessage } from "./types.js";
import type { LlmClient } from "./llm.js";

const incoming = JSON.parse(readFileSync(join(FIXTURES_DIR, "incoming.json"), "utf8")) as any[];

function freshDb() {
  const db = openDb(":memory:");
  loadFixtures(db);
  return db;
}

function invoiceMsg(from: string, invoice: IncomingMessage["invoice"], body = "Hello,\n\nInvoice attached.\n\nThanks"): IncomingMessage {
  return { id: "RH", from, date: `${invoice!.invoice_date}T09:30:00-07:00`, subject: `Invoice ${invoice!.invoice_number}`, body, invoice };
}

const checks = async (m: IncomingMessage) => {
  const db = freshDb();
  const r = await fingerprint(db, m, { llm: false });
  db.close();
  return r.findings;
};

describe("rhythm learning", () => {
  test("Acme bills monthly, amount varies", () => {
    const p = buildProfile(freshDb(), "V001")!;
    assert.equal(p.rhythm.cadence, "monthly");
    assert.ok(p.rhythm.intervalDays! >= 28 && p.rhythm.intervalDays! <= 31);
    assert.equal(p.rhythm.lastInvoiceDate, "2026-10-01");
    assert.equal(p.rhythm.fixedAmount, false);
  });
  test("TechNest bills a fixed $2,500 monthly", () => {
    const p = buildProfile(freshDb(), "V004")!;
    assert.equal(p.rhythm.cadence, "monthly");
    assert.equal(p.rhythm.fixedAmount, true);
    assert.equal(p.rhythm.typicalAmount, 2500);
  });
  test("LabWorks is irregular", () => {
    assert.equal(buildProfile(freshDb(), "V005")!.rhythm.cadence, "irregular");
  });
  test("quarterly and empty histories", () => {
    const q = learnRhythm([{ date: "2026-01-10", amount: 900 }, { date: "2026-04-10", amount: 900 }, { date: "2026-07-10", amount: 905 }]);
    assert.equal(q.cadence, "quarterly");
    assert.equal(q.expectedNextDate, "2026-10-09");
    assert.equal(learnRhythm([]).cadence, "none");
  });
});

describe("rhythm checks", () => {
  test("no false findings: Acme's normal November invoice from Maria", async () => {
    const f = await checks(invoiceMsg("maria.lopez@acme-supply.com",
      { invoice_number: "ACME-1052", invoice_date: "2026-11-01", po_number: "PO-2026-0117", amount: 5800, bank: { routing: "999000111", account: "4410023378" } },
      "Hi Janet,\n\nAttached is ACME-1052 for October.\n\nThanks,\nMaria"));
    assert.deepEqual(f.map((x) => x.check), []);
  });

  test("no false findings: TechNest's normal $2,500", async () => {
    const f = await checks(invoiceMsg("kevin@technest-it.com",
      { invoice_number: "TN-2211", invoice_date: "2026-10-01", po_number: "PO-2026-0071", amount: 2500, bank: { routing: "999000111", account: "5590061243" } }));
    assert.deepEqual(f.map((x) => x.check), []);
  });

  test("fixed_amount_changed: TechNest suddenly bills $3,400", async () => {
    const f = await checks(invoiceMsg("kevin@technest-it.com",
      { invoice_number: "TN-2211", invoice_date: "2026-10-01", po_number: "PO-2026-0071", amount: 3400, bank: { routing: "999000111", account: "5590061243" } }));
    const hit = f.find((x) => x.check === "fixed_amount_changed");
    assert.ok(hit, f.map((x) => x.check).join());
    assert.equal(hit!.severity, "medium");
  });

  test("bill_too_soon: second Acme bill 13 days after the monthly one", async () => {
    const f = await checks(invoiceMsg("maria.lopez@acme-supply.com",
      { invoice_number: "ACME-1052", invoice_date: "2026-10-14", po_number: "PO-2026-0117", amount: 4200, bank: { routing: "999000111", account: "4410023378" } }));
    const hit = f.find((x) => x.check === "bill_too_soon");
    assert.ok(hit, f.map((x) => x.check).join());
    assert.equal(hit!.severity, "medium");
    assert.ok(!f.some((x) => x.severity === "high"));
  });

  test("one_time_bill: irregular vendor (LabWorks), suggests requester confirmation", async () => {
    const f = await checks(invoiceMsg("orders@labworks-sci.com",
      { invoice_number: "LW-5504", invoice_date: "2026-10-20", po_number: "PO-2026-0150", amount: 980, bank: { routing: "999000666", account: "2208813377" } }));
    const hit = f.find((x) => x.check === "one_time_bill");
    assert.ok(hit, f.map((x) => x.check).join());
    assert.equal(hit!.severity, "low");
    assert.equal(hit!.action, "confirm_with_requester");
  });

  test("no_billing_history: a vendor on file that has never billed", async () => {
    const db = freshDb();
    db.exec(`INSERT INTO vendors VALUES ('V006','Northside Printing','northsideprint.com','1 Main St','(559) 555-0177',NULL,'Net 30','NP-');
             INSERT INTO vendor_contacts VALUES ('V006','Jo Bell','jo@northsideprint.com','Owner');
             INSERT INTO vendor_banks (vendor_id,bank_name,routing,account,remit_address,active) VALUES ('V006','First Valley Bank','999000111','1112223334','1 Main St',1);
             INSERT INTO purchase_orders VALUES ('PO-2026-0201','V006','Graduation programs',3000,0,3000,'Mia Chen','mia.chen@valleyusd.example.org','Principal''s Office');`);
    const r = await fingerprint(db, invoiceMsg("jo@northsideprint.com",
      { invoice_number: "NP-1", invoice_date: "2026-10-20", po_number: "PO-2026-0201", amount: 1250, bank: { routing: "999000111", account: "1112223334" } }), { llm: false });
    const hit = r.findings.find((x) => x.check === "no_billing_history");
    assert.ok(hit, r.findings.map((x) => x.check).join());
    assert.equal(hit!.severity, "low");
    assert.equal(hit!.action, "confirm_with_requester");
  });

  test("the 3 attacks and the control are unaffected by rhythm checks", async () => {
    const db = freshDb();
    for (const id of ["IN-NORMAL-1", "IN-ATTACK-1", "IN-ATTACK-2"]) {
      const r = await fingerprint(db, messageFromFixture(incoming.find((x) => x.id === id)), { llm: false });
      const rhythm = r.findings.filter((f) => ["bill_too_soon", "fixed_amount_changed", "one_time_bill", "no_billing_history"].includes(f.check));
      assert.deepEqual(rhythm.map((f) => f.check), [], id);
    }
  });
});

describe("demo case 4: surprise invoice → requester confirmation", () => {
  const surprise = () => messageFromFixture(incoming.find((x) => x.id === "IN-SURPRISE-1"));

  test("flags too-soon + no PO, nothing high, real sender", async () => {
    const db = freshDb();
    const r = await fingerprint(db, surprise(), { llm: false });
    const c = r.findings.map((f) => f.check);
    for (const x of ["bill_too_soon", "one_time_bill", "off_cycle_date"]) assert.ok(c.includes(x), c.join());
    assert.equal(r.impersonating, false);
    assert.ok(!r.findings.some((f) => f.severity === "high"), c.join());
  });

  test("template draft goes to the internal requester, never the sender, with no bank numbers", async () => {
    const db = freshDb();
    const m = surprise();
    const r = await fingerprint(db, m, { llm: false });
    const d = (await draftRequesterConfirmation(db, "V001", m, r.findings, { llm: false }))!;
    assert.equal(d.source, "template");
    assert.equal(d.recipient!.name, "Linda Park");
    assert.match(d.recipient!.contact, /@valleyusd\.example\.org$/);
    assert.notEqual(d.recipient!.contact, m.from);
    assert.match(d.text, /\$4,200\.00/);
    assert.match(d.text, /Acme School Supply/);
    assert.match(d.text, /no PO number/);
    assert.match(d.text, /yes or no/);
    assert.ok(!/\d{6,}/.test(d.text.replace(/\$[\d,]+(?:\.\d+)?/g, "")), d.text);
    assert.deepEqual(d.triggeredBy.sort(), ["one_time_bill"]);
  });

  test("uses the local model's wording when it's safe", async () => {
    const db = freshDb();
    const m = surprise();
    const r = await fingerprint(db, m, { llm: false });
    const good: LlmClient = { async complete() {
      return '{"message":"Hi Linda, Acme School Supply sent invoice ACME-1052 for $4,200.00 of lab equipment with no PO. It\'s on hold. Did you order it? Reply yes or no."}';
    } };
    const d = (await draftRequesterConfirmation(db, "V001", m, r.findings, { llm: good }))!;
    assert.equal(d.source, "llm");
    assert.match(d.text, /Hi Linda/);
  });

  test("falls back to the template if the model leaks a bank number, omits facts, or is offline", async () => {
    const db = freshDb();
    const m = surprise();
    const r = await fingerprint(db, m, { llm: false });
    const leaky: LlmClient = { async complete() { return '{"message":"Acme School Supply billed $4,200 to account 4410023378. Reply yes or no."}'; } };
    const vague: LlmClient = { async complete() { return '{"message":"Did you order something? Reply yes or no."}'; } };
    const dead: LlmClient = { async complete() { throw new Error("ECONNREFUSED"); } };
    for (const c of [leaky, vague, dead]) {
      const d = (await draftRequesterConfirmation(db, "V001", m, r.findings, { llm: c }))!;
      assert.equal(d.source, "template");
      assert.ok(!d.text.includes("4410023378"));
    }
  });

  test("no draft when nothing asks for confirmation (e.g. Maria's normal invoice)", async () => {
    const db = freshDb();
    const m = invoiceMsg("maria.lopez@acme-supply.com",
      { invoice_number: "ACME-1052", invoice_date: "2026-11-01", po_number: "PO-2026-0117", amount: 5800, bank: { routing: "999000111", account: "4410023378" } });
    const r = await fingerprint(db, m, { llm: false });
    assert.equal(await draftRequesterConfirmation(db, "V001", m, r.findings, { llm: false }), null);
  });
});
