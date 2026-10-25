// Ported from prototype/ap-guard/tests/test_apguard.py (prerna-1): scenarios via the pipeline,
// idempotency, batch totals, case controls, callback target, audit tamper detection, agent limits.
import { describe, test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { openDb, loadFixtures, REPO_ROOT, type DB } from "../db/index.js";
import { processEml, processDir, parseEml } from "./index.js";
import * as cases from "../cases/index.js";

const INBOX = join(REPO_ROOT, "data", "emails", "incoming");
const eml = (name: string) => join(INBOX, `${name}.eml`);
const opts = { llm: false as const, slackWebhookUrl: "" };

function freshDb(): DB {
  const db = openDb(":memory:");
  loadFixtures(db);
  return db;
}

describe("pipeline scenarios", () => {
  test("parseEml reads sender, reply-to and the PDF attachment", async () => {
    const p = await parseEml(eml("IN-ATTACK-3"));
    assert.equal(p.msg.from, "accounts@acmesupply.co");
    assert.equal(p.msg.replyTo, "accounts@acmesupply.co");
    assert.equal(p.msg.pdfPaths!.length, 1);
    assert.match(p.messageId, /in-attack-3/);
  });

  test("each demo email gets the right outcome", async () => {
    const db = freshDb();
    const res = await processDir(db, INBOX, opts);
    const by = Object.fromEntries(res.map((r) => [r.file.replace(".eml", ""), r]));
    assert.equal(by["IN-NORMAL-1"].decision!.outcome, "PASS");
    assert.equal(by["IN-NORMAL-1"].caseId, null);
    for (const id of ["IN-ATTACK-1", "IN-ATTACK-2", "IN-ATTACK-3"]) assert.equal(by[id].decision!.outcome, "HOLD_FRAUD_RISK", id);
    assert.equal(by["IN-SURPRISE-1"].decision!.outcome, "HOLD_CONFIRM");
    assert.ok(by["IN-ATTACK-3"].decision!.findings.some((f) => f.check === "hidden_pdf_text"));
    // batch totals
    assert.equal(res.filter((r) => r.caseId).length, 4);
    assert.equal(res.filter((r) => r.decision?.outcome === "PASS").length, 1);
  });

  test("reprocessing is idempotent", async () => {
    const db = freshDb();
    await processEml(db, eml("IN-ATTACK-1"), opts);
    const again = await processEml(db, eml("IN-ATTACK-1"), opts);
    assert.equal(again.skipped, true);
    assert.equal((db.prepare("SELECT COUNT(*) AS n FROM holds").get() as any).n, 1);
  });

  test("full bank numbers are never stored in cases or the audit log", async () => {
    const db = freshDb();
    await processDir(db, INBOX, opts);
    const blob = JSON.stringify(db.prepare("SELECT findings, reason FROM holds").all()) +
                 JSON.stringify(db.prepare("SELECT detail_json FROM audit_events").all()) +
                 JSON.stringify(db.prepare("SELECT * FROM alerts").all());
    for (const n of ["8820017745", "6604418392", "999000222", "999000555"]) assert.ok(!blob.includes(n), n);
    assert.ok(blob.includes("••••7745"));
  });

  test("surprise invoice drafts a question to the internal requester, not the sender", async () => {
    const db = freshDb();
    const r = await processEml(db, eml("IN-SURPRISE-1"), opts);
    const q = db.prepare("SELECT * FROM requester_checks WHERE hold_id = ?").get(r.caseId) as any;
    assert.equal(q.recipient_name, "Linda Park");
    assert.match(q.recipient_contact, /@valleyusd\.example\.org$/);
    assert.match(q.text, /\$4,200\.00/);
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM callbacks").get()!.n, 0);
  });
});

describe("case controls (ported)", () => {
  let db: DB;
  let cid: string;
  beforeEach(async () => {
    db = freshDb();
    cid = (await processEml(db, eml("IN-ATTACK-2"), opts)).caseId!;
  });

  test("cannot approve without verification", () => {
    assert.throws(() => cases.approve(db, cid, "omar.reyes"), cases.ControlError);
  });
  test("clerk cannot approve", () => {
    cases.startVerification(db, cid, "janet.kim");
    cases.recordConfirmation(db, cid, "janet.kim", true);
    assert.throws(() => cases.approve(db, cid, "janet.kim"), /not allowed to approve/);
  });
  test("segregation of duties: the verifier can't approve", () => {
    cases.startVerification(db, cid, "omar.reyes");
    cases.recordConfirmation(db, cid, "omar.reyes", true);
    assert.throws(() => cases.approve(db, cid, "omar.reyes"), /Segregation of duties/);
  });
  test("full happy path, audit chain intact", () => {
    cases.startVerification(db, cid, "janet.kim");
    cases.recordConfirmation(db, cid, "janet.kim", true, "called Maria on the number on file, confirmed");
    cases.approve(db, cid, "pat.lee");
    const c = cases.getCase(db, cid);
    assert.equal(c.state, "APPROVED");
    assert.equal(c.status, "released");
    assert.equal(c.resolved_by, "pat.lee");
    assert.equal(cases.verifyAuditChain(db).ok, true);
  });
  test("vendor denial rejects, and a rejected case can't be approved", () => {
    cases.startVerification(db, cid, "janet.kim");
    cases.recordConfirmation(db, cid, "janet.kim", false, "Maria says they never changed banks");
    assert.equal(cases.getCase(db, cid).state, "REJECTED");
    assert.throws(() => cases.approve(db, cid, "omar.reyes"), cases.ControlError);
  });
  test("callback uses the vendor master's phone, not the email", () => {
    const cb = db.prepare("SELECT * FROM callbacks WHERE hold_id = ?").get(cid) as any;
    assert.equal(cb.phone, "(559) 555-0142");
    assert.match(cb.script, /Call ONLY \(559\) 555-0142/);
    assert.ok(!cb.script.includes("6604418392"));
    const started = cases.startVerification(db, cid, "janet.kim") as any;
    assert.equal(started.phone, "(559) 555-0142");
  });
  test("audit tampering is detected", () => {
    cases.startVerification(db, cid, "janet.kim");
    assert.equal(cases.verifyAuditChain(db).ok, true);
    db.exec("UPDATE audit_events SET actor = 'mallory' WHERE action = 'verification_started'");
    const v = cases.verifyAuditChain(db);
    assert.equal(v.ok, false);
    assert.ok(v.firstBadId);
  });
  test("deleting an audit row is detected", () => {
    cases.startVerification(db, cid, "janet.kim");
    cases.recordConfirmation(db, cid, "janet.kim", true);
    db.exec("DELETE FROM audit_events WHERE action = 'verification_started'");
    assert.equal(cases.verifyAuditChain(db).ok, false);
  });
  test("the agent can't do human actions", () => {
    for (const fn of [() => cases.startVerification(db, cid, cases.AGENT), () => cases.approve(db, cid, cases.AGENT),
                      () => cases.reject(db, cid, cases.AGENT), () => cases.recordConfirmation(db, cid, cases.AGENT, true)]) {
      assert.throws(fn, /human-only/);
    }
  });
  test("unknown users and illegal transitions are refused", () => {
    assert.throws(() => cases.startVerification(db, cid, "mallory"), /Unknown user/);
    assert.throws(() => cases.recordConfirmation(db, cid, "janet.kim", true), /Cannot record confirmation from state OPEN/);
    cases.reject(db, cid, "janet.kim", "obvious fraud");
    assert.throws(() => cases.reject(db, cid, "janet.kim"), /already REJECTED/);
  });
});

describe("requester confirmation flow", () => {
  test("HOLD_CONFIRM → requester says yes → manager approves", async () => {
    const db = freshDb();
    const cid = (await processEml(db, eml("IN-SURPRISE-1"), opts)).caseId!;
    const s = cases.startVerification(db, cid, "janet.kim") as any;
    assert.equal(s.state, "AWAITING_REQUESTER");
    assert.match(s.recipient, /linda\.park@/);
    cases.recordConfirmation(db, cid, "janet.kim", true, "Linda: yes, science dept order");
    cases.approve(db, cid, "omar.reyes");
    assert.equal(cases.getCase(db, cid).state, "APPROVED");
    assert.equal((db.prepare("SELECT status FROM requester_checks WHERE hold_id = ?").get(cid) as any).status, "confirmed");
    assert.equal(cases.verifyAuditChain(db).ok, true);
  });
  test("requester says no → rejected", async () => {
    const db = freshDb();
    const cid = (await processEml(db, eml("IN-SURPRISE-1"), opts)).caseId!;
    cases.startVerification(db, cid, "janet.kim");
    cases.recordConfirmation(db, cid, "janet.kim", false, "Linda: never ordered microscopes");
    assert.equal(cases.getCase(db, cid).state, "REJECTED");
  });
});

describe("alerts from the pipeline", () => {
  test("a hold posts one Slack summary when a webhook is set (fake fetch, no network)", async () => {
    const db = freshDb();
    const sent: any[] = [];
    const fake = (async (_u: any, init: any) => { sent.push(JSON.parse(init.body)); return new Response("ok"); }) as typeof fetch;
    await processDir(db, INBOX, { llm: false, slackWebhookUrl: "https://hooks.slack.com/services/TEST/TEST/TEST", fetchImpl: fake });
    assert.equal(sent.length, 4);
    for (const s of sent) assert.ok(!/\d{6,}/.test(JSON.stringify(s)), JSON.stringify(s));
  });
});
