import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, FIXTURES_DIR } from "../db/index.js";
import { fingerprint, messageFromFixture } from "../fingerprint/index.js";
import { decide } from "../rules/index.js";
import { buildAlert, postToSlack, raiseAlert, listAlerts, scrub } from "./index.js";

const incoming = JSON.parse(readFileSync(join(FIXTURES_DIR, "incoming.json"), "utf8")) as any[];

async function alertFor(id: string) {
  const db = openDb(":memory:");
  loadFixtures(db);
  const r = await fingerprint(db, messageFromFixture(incoming.find((x) => x.id === id)), { llm: false });
  const d = decide(r.findings, { hasInvoice: true });
  return { db, alert: buildAlert({ caseId: "HOLD-0001", vendorName: "Acme School Supply", outcome: d.outcome, state: "OPEN", top: d.top }) };
}

test("alerts carry vendor, decision, reason and case id, and nothing from the invoice", async () => {
  for (const id of ["IN-ATTACK-1", "IN-ATTACK-2", "IN-ATTACK-3", "IN-SURPRISE-1"]) {
    const { alert } = await alertFor(id);
    const all = JSON.stringify(alert.blocks) + alert.text;
    assert.match(all, /HOLD-0001/);
    assert.match(all, /Acme School Supply/);
    assert.match(alert.headline, /HELD/);
    for (const leak of ["999000", "8820017745", "6604418392", "4410023378", "ACME-105", "4,200", "6,420", "8,940", "@", "Coastline", "Harbor"]) {
      assert.ok(!all.includes(leak), `${id} alert leaks ${leak}: ${all}`);
    }
  }
});

test("scrub strips numbers and addresses that slip in", () => {
  assert.equal(scrub("pay 8820017745 to x@evil.co"), "pay [number] to [address]");
  assert.equal(scrub("HOLD-0003"), "HOLD-0003");
});

test("no webhook configured → nothing sent, no network", async () => {
  const { alert } = await alertFor("IN-ATTACK-1");
  const prev = process.env.SLACK_WEBHOOK_URL;
  delete process.env.SLACK_WEBHOOK_URL;
  let called = false;
  const r = await postToSlack(alert, { fetchImpl: (async () => { called = true; return new Response("ok"); }) as typeof fetch });
  if (prev !== undefined) process.env.SLACK_WEBHOOK_URL = prev;
  assert.equal(r.sent, false);
  assert.equal(called, false);
});

test("posts text + blocks to a Slack webhook; refuses non-Slack URLs", async () => {
  const { alert } = await alertFor("IN-ATTACK-1");
  let body: any;
  const fake = (async (_u: any, init: any) => { body = JSON.parse(init.body); return new Response("ok", { status: 200 }); }) as typeof fetch;
  const ok = await postToSlack(alert, { webhookUrl: "https://hooks.slack.com/services/TEST/TEST/TEST", fetchImpl: fake });
  assert.equal(ok.sent, true);
  assert.ok(Array.isArray(body.blocks) && body.text.includes("HOLD-0001"));
  const bad = await postToSlack(alert, { webhookUrl: "https://evil.example/hook", fetchImpl: fake });
  assert.equal(bad.sent, false);
});

test("in-app feed records every alert, with Slack status", async () => {
  const { db } = await alertFor("IN-ATTACK-1");
  await raiseAlert(db, { caseId: "HOLD-0001", vendorName: "Acme School Supply", outcome: "HOLD_FRAUD_RISK", state: "OPEN", top: [] }, { webhookUrl: "" });
  const feed = listAlerts(db);
  assert.equal(feed.length, 1);
  assert.equal(feed[0].slack_sent, 0);
  assert.equal(feed[0].outcome, "HOLD_FRAUD_RISK");
});
