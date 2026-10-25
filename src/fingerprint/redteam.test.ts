// Red-team cases: attacks someone actually tried against the fingerprint (rules only).
// Add every new bypass here before fixing it.
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, FIXTURES_DIR } from "../db/index.js";
import { fingerprint, messageFromFixture, compareDomains } from "./index.js";
import { BANK_CHANGE_RE } from "./text.js";
import type { IncomingMessage } from "./types.js";

const BANK_BODY = "Hi Janet,\n\nWe have moved our accounts to a new bank. Please update our remittance details:\n\nBank: Coastline Credit Union\nRouting: 999000222\nAccount: 8820017745\n\nThanks,\nMaria";

function msg(from: string, fromName: string, body = BANK_BODY, subject = "Banking update"): IncomingMessage {
  return { id: "RT", from, fromName, date: "2026-10-25T09:00:00-07:00", subject, body };
}

async function run(m: IncomingMessage) {
  const db = openDb(":memory:");
  loadFixtures(db);
  const r = await fingerprint(db, m, { llm: false });
  db.close();
  return { ...r, checks: r.findings.map((f) => f.check), high: r.findings.filter((f) => f.severity === "high").map((f) => f.check) };
}

describe("red team (pratham-1, 13:20)", () => {
  test("combosquat maria.lopez@acmeschoolsupply-billing.com", async () => {
    const r = await run(msg("maria.lopez@acmeschoolsupply-billing.com", "Maria Lopez"));
    assert.equal(r.vendorId, "V001");
    assert.equal(r.impersonating, true);
    assert.ok(r.checks.includes("lookalike_domain"), r.checks.join());
    assert.ok(r.high.includes("payment_change_from_unknown_sender"));
  });

  test("plural maria@acme-supplies.com", async () => {
    const r = await run(msg("maria@acme-supplies.com", "Maria"));
    assert.equal(r.vendorId, "V001");
    assert.ok(r.checks.includes("lookalike_domain"), r.checks.join());
    assert.ok(r.high.includes("payment_change_from_unknown_sender"));
  });

  test("freemail maria.lopez.acme@gmail.com, display name 'Maria Lopez'", async () => {
    const r = await run(msg("maria.lopez.acme@gmail.com", "Maria Lopez"));
    assert.equal(r.vendorId, "V001");
    assert.equal(r.impersonating, true);
    assert.ok(r.high.includes("freemail_sender"), r.checks.join());
    assert.ok(r.high.includes("payment_change_from_unknown_sender"));
  });

  test("real address, vague wording: 'remittance info is different now, details in the attached letter'", async () => {
    const r = await run(msg("maria.lopez@acme-supply.com", "Maria Lopez",
      "Hi Janet,\n\nOur remittance info is different now, details in the attached letter.\n\nThanks,\nMaria", "Remittance"));
    assert.equal(r.impersonating, false);
    assert.ok(r.checks.includes("bank_change_request"), r.checks.join());
    assert.ok(r.high.includes("first_bank_change"));
  });

  test("false positive: orders@bestsupply.com with display name 'Supply' is NOT Acme", async () => {
    const r = await run(msg("orders@bestsupply.com", "Supply", "Hello,\n\nAttached is our catalog for spring.\n\nOrders team", "Spring catalog"));
    assert.equal(r.vendorId, null);
    assert.ok(!r.checks.includes("lookalike_domain"));
    assert.deepEqual(r.high, []);
  });

  test("gmail with display name 'Acme School Supply' (was already caught)", async () => {
    const r = await run(msg("acmeschoolsupply.ar@gmail.com", "Acme School Supply"));
    assert.equal(r.vendorId, "V001");
    assert.ok(r.high.includes("payment_change_from_unknown_sender"));
  });

  test("real address 'going forward please remit to: Routing…, Account…' (was already caught)", async () => {
    const r = await run(msg("maria.lopez@acme-supply.com", "Maria Lopez",
      "Hi Janet,\n\nGoing forward please remit to: Routing 999000555, Account 6604418392.\n\nThanks,\nMaria", "Remit"));
    assert.ok(r.checks.includes("bank_change_request"), r.checks.join());
    assert.ok(r.high.includes("first_bank_change"));
  });

  test("control (Bright Bus normal invoice) still has no findings", async () => {
    const incoming = JSON.parse(readFileSync(join(FIXTURES_DIR, "incoming.json"), "utf8")) as any[];
    const r = await run(messageFromFixture(incoming.find((x) => x.id === "IN-NORMAL-1")));
    assert.deepEqual(r.checks, []);
  });
});

describe("red team (pratham-2 extras)", () => {
  test(".co TLD swap with contact name: maria.lopez@acme-supply.co", async () => {
    const r = await run(msg("maria.lopez@acme-supply.co", "Maria Lopez"));
    assert.equal(r.vendorId, "V001");
    assert.ok(r.findings.some((f) => f.check === "lookalike_domain" && f.explanation.includes("tld-swap")));
  });

  test("Cyrillic а in acme: maria.lopez@аcme-supply.com", async () => {
    const r = await run(msg("maria.lopez@аcme-supply.com", "Maria Lopez"));
    assert.equal(r.vendorId, "V001");
    assert.ok(r.findings.some((f) => f.check === "lookalike_domain" && f.explanation.includes("homoglyph")));
  });

  test("total stranger asking for a bank change still gets a high finding with no vendor match", async () => {
    const r = await run(msg("ar@vendor-payments.net", "Accounts Receivable", "Hello,\n\nPlease update our banking details for all future payments.\n\nAR team"));
    assert.equal(r.vendorId, null);
    assert.ok(r.high.includes("payment_change_from_unknown_sender"), r.checks.join());
  });

  test("the vendor's own subdomain is not a lookalike: ar@billing.acme-supply.com", async () => {
    assert.equal(compareDomains("billing.acme-supply.com", "acme-supply.com", "Acme School Supply").lookalike, false);
    const r = await run(msg("ar@billing.acme-supply.com", "Acme AR", "Hi Janet,\n\nStatement attached.\n\nAcme AR", "Statement"));
    assert.equal(r.vendorId, "V001");
    assert.equal(r.impersonating, false);
    assert.ok(!r.checks.includes("lookalike_domain"));
  });

  test("suffix glued on: maria@acmesupplyinc.com", async () => {
    const r = await run(msg("maria@acmesupplyinc.com", "Maria"));
    assert.equal(r.vendorId, "V001");
    assert.ok(r.checks.includes("lookalike_domain"), r.checks.join());
  });

  test("other vendors' real domains never look like Acme", () => {
    for (const d of ["brightbus.com", "greenfieldfoods.com", "technest-it.com", "bestsupply.com", "officesupply.com"]) {
      assert.equal(compareDomains(d, "acme-supply.com", "Acme School Supply").lookalike, false, d);
    }
  });

  test("none of Maria's 22 history emails reads as a bank change", () => {
    const history = JSON.parse(readFileSync(join(FIXTURES_DIR, "emails.json"), "utf8")) as any[];
    const hits = history.filter((e) => BANK_CHANGE_RE.test(e.body) || BANK_CHANGE_RE.test(e.subject));
    assert.deepEqual(hits.map((e) => e.id), []);
  });
});
