import { test } from "node:test";
import assert from "node:assert/strict";
import { openDb, loadFixtures } from "./index.js";

test("fixtures load into a fresh database", () => {
  const db = openDb(":memory:");
  const counts = loadFixtures(db);
  assert.equal(counts.vendors, 5);
  assert.ok(counts.emails >= 26);
  const acme = db.prepare("SELECT phone_on_file FROM vendors WHERE id = 'V001'").get() as { phone_on_file: string };
  assert.equal(acme.phone_on_file, "(559) 555-0142");
  const bank = db.prepare("SELECT routing FROM vendor_banks WHERE vendor_id = 'V001' AND active = 1").get() as { routing: string };
  assert.equal(bank.routing, "999000111");
  const po = db.prepare("SELECT requester_name, requester_contact FROM purchase_orders WHERE number = 'PO-2026-0117'").get() as any;
  assert.equal(po.requester_name, "Linda Park");
  assert.match(po.requester_contact, /@valleyusd\.example\.org$/);
  db.close();
});

test("loading twice is idempotent", () => {
  const db = openDb(":memory:");
  loadFixtures(db);
  loadFixtures(db);
  const n = db.prepare("SELECT COUNT(*) AS n FROM vendors").get() as { n: number };
  assert.equal(n.n, 5);
  db.close();
});
