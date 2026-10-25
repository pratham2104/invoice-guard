// T18: Slack bot cards + buttons, all with fake clients (no network).
import { describe, test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { openDb, loadFixtures, REPO_ROOT, type DB } from "../db/index.js";
import { processEml } from "../pipeline/index.js";
import * as cases from "../cases/index.js";
import { raiseAlert } from "./index.js";
import { ACTIONS, caseCard, describeConfig, handleAction, loadSlackEnv, postCaseCard, registerHandlers, slackConfig, type ChatClient } from "./slack.js";

const eml = (n: string) => join(REPO_ROOT, "data", "emails", "incoming", `${n}.eml`);
const USERS = { U_CLERK: "janet.kim", U_MGR1: "omar.reyes", U_MGR2: "pat.lee" };

function fakeClient() {
  const posted: any[] = [], updated: any[] = [];
  const client: ChatClient = { chat: {
    async postMessage(a) { posted.push(a); return { ok: true, ts: "1.0001", channel: a.channel }; },
    async update(a) { updated.push(a); return { ok: true }; },
  } };
  return { client, posted, updated };
}

async function withCase(name = "IN-ATTACK-2"): Promise<{ db: DB; cid: string }> {
  const db = openDb(":memory:");
  loadFixtures(db);
  const r = await processEml(db, eml(name), { llm: false, slackWebhookUrl: "" });
  return { db, cid: r.caseId! };
}

const flat = (x: unknown) => JSON.stringify(x);
const buttons = (card: { blocks: any[] }) => card.blocks.find((b) => b.type === "actions")?.elements.map((e: any) => e.text.text) ?? [];

describe("config", () => {
  test("user tokens (xoxp-) are refused; wrong token kinds are refused", () => {
    assert.throws(() => slackConfig({ SLACK_BOT_TOKEN: "xoxp-123" }), /user token/);
    assert.throws(() => slackConfig({ SLACK_BOT_TOKEN: "abc" }), /bot token/);
    assert.throws(() => slackConfig({ SLACK_BOT_TOKEN: "xoxb-1", SLACK_APP_TOKEN: "xoxb-2" }), /app-level token/);
  });
  test("describeConfig never contains token text", () => {
    const c = slackConfig({ SLACK_BOT_TOKEN: "xoxb-SECRET1", SLACK_APP_TOKEN: "xapp-SECRET2", SLACK_CHANNEL_ID: "C123" });
    const d = describeConfig(c);
    assert.ok(!d.includes("SECRET"));
    assert.match(d, /bot set · app \(Socket Mode\) set · channel C123/);
  });
  test("env file: loaded, and a world-readable file is flagged", () => {
    const dir = mkdtempSync(join(tmpdir(), "se-"));
    const p = join(dir, "slack.env");
    writeFileSync(p, "IG_TEST_SLACK_VAR=hello\n");
    chmodSync(p, 0o644);
    const w = loadSlackEnv(p);
    assert.equal(process.env.IG_TEST_SLACK_VAR, "hello");
    assert.match(w[0], /chmod 600/);
    chmodSync(p, 0o600);
    assert.deepEqual(loadSlackEnv(p), []);
    delete process.env.IG_TEST_SLACK_VAR;
  });
});

describe("case card", () => {
  test("vendor, decision, reason, case id; no invoice or bank data", async () => {
    for (const n of ["IN-ATTACK-1", "IN-ATTACK-2", "IN-ATTACK-3", "IN-SURPRISE-1"]) {
      const { db, cid } = await withCase(n);
      const card = caseCard(db, cid);
      const s = flat(card);
      assert.match(s, new RegExp(cid));
      assert.match(s, /Acme School Supply/);
      for (const leak of ["999000", "8820017745", "6604418392", "4410023378", "ACME-105", "4,200", "6,420", "@acme", "Coastline", "Harbor"]) {
        assert.ok(!s.includes(leak), `${n} card leaks ${leak}`);
      }
    }
  });
  test("buttons follow the state machine", async () => {
    const { db, cid } = await withCase();
    assert.deepEqual(buttons(caseCard(db, cid)), ["Start verification"]);
    cases.startVerification(db, cid, "janet.kim");
    assert.deepEqual(buttons(caseCard(db, cid)), ["Vendor confirmed legit", "Confirmed fraud"]);
    cases.recordConfirmation(db, cid, "janet.kim", true);
    assert.deepEqual(buttons(caseCard(db, cid)), ["Approve release"]);
    cases.approve(db, cid, "omar.reyes");
    assert.deepEqual(buttons(caseCard(db, cid)), []);
  });
  test("requester cases say 'Requester confirmed legit'", async () => {
    const { db, cid } = await withCase("IN-SURPRISE-1");
    cases.startVerification(db, cid, "janet.kim");
    assert.deepEqual(buttons(caseCard(db, cid)), ["Requester confirmed legit", "Confirmed fraud"]);
  });
});

describe("posting", () => {
  test("postCaseCard uses chat.postMessage with the channel", async () => {
    const { db, cid } = await withCase();
    const f = fakeClient();
    const r = await postCaseCard(f.client, "C0DEMO", db, cid);
    assert.equal(r.sent, true);
    assert.equal(f.posted[0].channel, "C0DEMO");
    assert.ok(f.posted[0].blocks.some((b: any) => b.type === "actions"));
  });
  test("raiseAlert prefers the bot; the webhook path still works without it", async () => {
    const { db, cid } = await withCase();
    const f = fakeClient();
    let webhookCalls = 0;
    const fetchImpl = (async () => { webhookCalls++; return new Response("ok"); }) as typeof fetch;
    const viaBot = await raiseAlert(db, { caseId: cid, vendorName: "Acme School Supply", outcome: "HOLD_FRAUD_RISK", state: "OPEN", top: [] },
      { bot: { client: f.client, channel: "C0DEMO" }, webhookUrl: "https://hooks.slack.com/services/TEST/TEST/TEST", fetchImpl });
    assert.equal(viaBot.slack.sent, true);
    assert.equal(f.posted.length, 1);
    assert.equal(webhookCalls, 0);
    const viaHook = await raiseAlert(db, { caseId: cid, vendorName: "Acme School Supply", outcome: "HOLD_FRAUD_RISK", state: "OPEN", top: [] },
      { bot: null, webhookUrl: "https://hooks.slack.com/services/TEST/TEST/TEST", fetchImpl });
    assert.equal(viaHook.slack.sent, true);
    assert.equal(webhookCalls, 1);
  });
});

describe("buttons → case transitions (roles enforced)", () => {
  let db: DB, cid: string;
  beforeEach(async () => ({ db, cid } = await withCase()));
  const press = (actionId: string, slackUserId: string) => handleAction(db, { actionId, caseId: cid, slackUserId }, USERS);

  test("unmapped Slack user is blocked", () => {
    const r = press(ACTIONS.start, "U_STRANGER");
    assert.equal(r.ok, false);
    assert.match(r.message, /isn't mapped/);
    assert.equal(cases.getCase(db, cid).state, "OPEN");
  });
  test("full flow: clerk verifies, a different manager approves", () => {
    assert.equal(press(ACTIONS.start, "U_CLERK").state, "AWAITING_VENDOR");
    assert.equal(press(ACTIONS.yes, "U_CLERK").state, "READY_FOR_APPROVAL");
    const clerk = press(ACTIONS.approve, "U_CLERK");
    assert.equal(clerk.ok, false);
    assert.match(clerk.message, /not allowed to approve/);
    assert.equal(press(ACTIONS.approve, "U_MGR1").state, "APPROVED");
    assert.equal(cases.verifyAuditChain(db).ok, true);
  });
  test("segregation of duties: the manager who verified can't approve", () => {
    press(ACTIONS.start, "U_MGR1");
    press(ACTIONS.yes, "U_MGR1");
    assert.match(press(ACTIONS.approve, "U_MGR1").message, /Segregation of duties/);
    assert.equal(press(ACTIONS.approve, "U_MGR2").state, "APPROVED");
  });
  test("'Confirmed fraud' rejects; approve is then impossible", () => {
    press(ACTIONS.start, "U_CLERK");
    assert.equal(press(ACTIONS.no, "U_CLERK").state, "REJECTED");
    assert.equal(press(ACTIONS.approve, "U_MGR1").ok, false);
  });
  test("buttons out of order are refused (approve on an OPEN case)", () => {
    assert.match(press(ACTIONS.approve, "U_MGR1").message, /verification is required first/);
  });
  test("a Slack user mapped to 'agent' is still refused", () => {
    const r = handleAction(db, { actionId: ACTIONS.start, caseId: cid, slackUserId: "U_BOT" }, { U_BOT: cases.AGENT });
    assert.equal(r.ok, false);
    assert.match(r.message, /human-only/);
  });
});

describe("Bolt wiring (fake app)", () => {
  test("acks, updates the card on success, answers ephemerally when blocked", async () => {
    const { db, cid } = await withCase();
    let handler: any;
    registerHandlers({ action: (_id: any, fn: any) => { handler = fn; } }, db, () => USERS);
    const f = fakeClient();
    const responses: any[] = [];
    let acks = 0;
    const call = (action_id: string, user: string) => handler({
      ack: async () => { acks++; }, respond: async (m: any) => responses.push(m), client: f.client,
      action: { action_id, value: cid }, body: { user: { id: user }, channel: { id: "C0DEMO" }, message: { ts: "1.0001" } },
    });
    await call(ACTIONS.approve, "U_MGR1");           // blocked: not verified yet
    assert.equal(responses[0].response_type, "ephemeral");
    assert.match(responses[0].text, /Blocked/);
    await call(ACTIONS.start, "U_CLERK");            // ok → card updated in place
    assert.equal(f.updated.length, 1);
    assert.equal(f.updated[0].ts, "1.0001");
    assert.match(flat(f.updated[0].blocks), /AWAITING_VENDOR/);
    assert.equal(acks, 2);
  });
});
