// T03b: the dashboard API over the real pipeline + case workflow, on an ephemeral port, rules only, no network.
import { describe, test, before, after } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import type { Server } from "node:http";
import { createApi } from "./app.js";

const FULL_NUMBERS = ["4410023378", "8820017745", "6604418392", "7720045519", "999000111", "999000222", "999000555"];

async function start(extra: Parameters<typeof createApi>[0] extends infer O ? Partial<O> : never = {}) {
  const api = createApi({ dbPath: ":memory:", llmBaseUrl: null, slackWebhookUrl: "", ...extra });
  const server: Server = await new Promise((ok) => { const s = api.app.listen(0, "127.0.0.1", () => ok(s)); });
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const call = async (method: string, path: string, body?: unknown, headers: Record<string, string> = {}) => {
    const res = await fetch(base + path, { method, headers: { "content-type": "application/json", ...headers }, body: body ? JSON.stringify(body) : undefined });
    const text = await res.text();
    let json: any = null;
    try { json = JSON.parse(text); } catch { /* not json */ }
    return { status: res.status, json, text, headers: res.headers };
  };
  return { api, base, call, close: () => new Promise<void>((ok) => { api.close(); server.closeAllConnections(); server.close(() => ok()); }) };
}

describe("dashboard API", () => {
  let s: Awaited<ReturnType<typeof start>>;
  const caseFor: Record<string, string> = {};

  before(async () => {
    s = await start();
    for (let i = 0; i < 5; i++) {
      const r = await s.call("POST", "/api/demo/ingest", {});
      assert.equal(r.status, 200, r.text);
      if (r.json.caseId) caseFor[r.json.processed.replace(".eml", "")] = r.json.caseId;
    }
  });
  after(() => s.close());

  test("status: rules-only, no cloud, counts from the real cases", async () => {
    const r = await s.call("GET", "/api/status");
    assert.equal(r.json.product, "Halberd");
    assert.equal(r.json.mode, "rules-only");
    assert.equal(r.json.model.up, false);
    assert.equal(r.json.model.id, "nvidia/Qwen3.6-35B-A3B-NVFP4");
    assert.equal(r.json.cloudCalls, 0);
    assert.deepEqual(r.json.counts, { heldAmount: 8940 + 6420 + 4200, held: 4, checkedToday: 5, cleared: 1, awaitingVendor: 3, awaitingRequester: 1 });
  });

  test("ingest ran every demo email through the pipeline; nothing left", async () => {
    assert.deepEqual(Object.keys(caseFor).sort(), ["IN-ATTACK-1", "IN-ATTACK-2", "IN-ATTACK-3", "IN-SURPRISE-1"]);
    const files = await s.call("GET", "/api/demo/files");
    assert.equal(files.json.length, 5);
    assert.ok(files.json.every((f: any) => f.processed));
    assert.equal(files.json.find((f: any) => f.file === "IN-NORMAL-1.eml").outcome, "PASS");
    const more = await s.call("POST", "/api/demo/ingest", {});
    assert.equal(more.status, 409);
    assert.ok(more.json.error);
  });

  test("cases list: newest first, with amount and top checks", async () => {
    const r = await s.call("GET", "/api/cases");
    assert.equal(r.json.length, 4);
    assert.deepEqual(r.json.map((c: any) => c.id), [...r.json.map((c: any) => c.id)].sort().reverse());
    const a3 = r.json.find((c: any) => c.id === caseFor["IN-ATTACK-3"]);
    assert.equal(a3.outcome, "HOLD_FRAUD_RISK");
    assert.equal(a3.vendorName, "Acme School Supply");
    assert.equal(a3.amount, 6420);
    assert.equal(a3.invoiceNumber, "ACME-1051");
    assert.ok(a3.topChecks.length > 0 && a3.topChecks.length <= 3);
  });

  test("case detail: forged invoice vs the last real one, masked, audit chain intact", async () => {
    const r = await s.call("GET", `/api/cases/${caseFor["IN-ATTACK-3"]}`);
    assert.equal(r.status, 200);
    const d = r.json;
    assert.equal(d.vendor.phoneOnFile, "(559) 555-0142");
    assert.equal(d.bankOnFile.accountLast4, "3378");
    assert.equal(d.invoice.current.accountLast4, "7745");
    assert.equal(d.invoice.current.pdfUrl, "/files/invoices/ACME-1051-corrected.pdf");
    assert.equal(d.invoice.lastReal.invoiceNumber, "ACME-1051");
    assert.equal(d.invoice.lastReal.pdfUrl, "/files/invoices/ACME-1051.pdf");
    assert.ok(d.invoice.current.lines.length > 0);
    assert.ok(d.findings.some((f: any) => f.check === "hidden_pdf_text"));
    assert.equal(d.decision.nextStep, "phone_callback");
    assert.equal(d.callbacks[0].phone, "(559) 555-0142");
    assert.equal(d.audit.chainOk, true);
    assert.ok(d.audit.count >= 2);
    assert.equal(d.email.from, "accounts@acmesupply.co");
  });

  test("no full bank or routing number appears in any response", async () => {
    const paths = ["/api/status", "/api/cases", "/api/alerts", "/api/vendors", ...Object.values(caseFor).map((id) => `/api/cases/${id}`)];
    for (const p of paths) {
      const { text } = await s.call("GET", p);
      for (const n of FULL_NUMBERS) assert.ok(!text.includes(n), `${p} leaks ${n}`);
    }
  });

  test("alerts and vendors", async () => {
    const a = await s.call("GET", "/api/alerts");
    assert.equal(a.json.length, 4);
    assert.ok(a.json.every((x: any) => x.caseId && x.text && x.channel === "in-app" && x.sent === false));
    const v = await s.call("GET", "/api/vendors");
    const acme = v.json.find((x: any) => x.id === "V001");
    assert.equal(acme.invoices, 12);
    assert.ok(acme.lastPaid);
  });

  test("approval controls: manager only, after verification, never the verifier", async () => {
    const id = caseFor["IN-SURPRISE-1"];
    let r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "janet.kim", role: "clerk" });
    assert.equal(r.status, 403);
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "omar.reyes", role: "manager" });
    assert.equal(r.status, 409, "not verified yet");
    r = await s.call("POST", `/api/cases/${id}/callback`, { result: "confirmed_legit", actor: "omar.reyes" });
    assert.equal(r.status, 200, r.text);
    assert.equal(r.json.case.state, "READY_FOR_APPROVAL");
    assert.equal(r.json.requesterChecks[0].status, "confirmed");
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "omar.reyes", role: "manager" });
    assert.equal(r.status, 403, "segregation of duties");
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "janet.kim", role: "manager" });
    assert.equal(r.status, 403, "role claim is checked against the user list");
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "pat.lee", role: "manager" });
    assert.equal(r.status, 200, r.text);
    assert.equal(r.json.case.state, "APPROVED");
    assert.equal(r.json.case.resolvedBy, "pat.lee");
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "pat.lee", role: "manager" });
    assert.equal(r.status, 409);
    r = await s.call("POST", `/api/cases/${id}/approve`, { actor: "agent", role: "manager" });
    assert.equal(r.status, 403);
  });

  test("callback: no answer keeps it held, confirmed fraud rejects it; reject is manager only", async () => {
    const id = caseFor["IN-ATTACK-1"];
    let r = await s.call("POST", `/api/cases/${id}/callback`, { result: "no_answer", actor: "janet.kim" });
    assert.equal(r.status, 200, r.text);
    assert.equal(r.json.case.state, "AWAITING_VENDOR");
    assert.equal(r.json.callbacks[0].status, "no_answer");
    r = await s.call("POST", `/api/cases/${id}/callback`, { result: "confirmed_fraud", actor: "janet.kim" });
    assert.equal(r.json.case.state, "REJECTED");
    assert.equal(r.json.callbacks[0].status, "confirmed_fraud");
    assert.ok(r.json.audit.events.some((e: any) => e.action === "rejected"));
    r = await s.call("POST", `/api/cases/${caseFor["IN-ATTACK-2"]}/reject`, { actor: "janet.kim", role: "manager" });
    assert.equal(r.status, 403);
    r = await s.call("POST", `/api/cases/${caseFor["IN-ATTACK-2"]}/reject`, { actor: "omar.reyes", role: "manager" });
    assert.equal(r.status, 200);
    assert.equal(r.json.case.state, "REJECTED");
    r = await s.call("POST", `/api/cases/${caseFor["IN-ATTACK-2"]}/callback`, { result: "maybe", actor: "omar.reyes" });
    assert.equal(r.status, 400);
    r = await s.call("GET", "/api/cases/HOLD-9999");
    assert.equal(r.status, 404);
  });

  test("CORS for the dashboard origin and invoice PDFs are served", async () => {
    const r = await s.call("GET", "/api/vendors", undefined, { origin: "http://localhost:5180" });
    assert.equal(r.headers.get("access-control-allow-origin"), "http://localhost:5180");
    const other = await s.call("GET", "/api/vendors", undefined, { origin: "https://evil.example" });
    assert.equal(other.headers.get("access-control-allow-origin"), null);
    const pdf = await fetch(`${s.base}/files/invoices/ACME-1051.pdf`);
    assert.equal(pdf.status, 200);
    assert.match(pdf.headers.get("content-type") ?? "", /pdf/);
    const bad = await fetch(`${s.base}/files/invoices/..%2F..%2Fpackage.json`);
    assert.equal(bad.status, 404);
  });
});

describe("dashboard API: reset, live events, model probe", () => {
  test("reset gives a fresh DB; SSE announces the case an ingest opens", async () => {
    const s = await start();
    try {
      await s.call("POST", "/api/demo/ingest", { file: "IN-ATTACK-1.eml" });
      let cases = await s.call("GET", "/api/cases");
      assert.equal(cases.json.length, 1);
      const reset = await s.call("POST", "/api/demo/reset");
      assert.equal(reset.json.ok, true);
      cases = await s.call("GET", "/api/cases");
      assert.equal(cases.json.length, 0);

      const ctrl = new AbortController();
      const res = await fetch(`${s.base}/api/events`, { signal: ctrl.signal });
      const reader = res.body!.getReader();
      const ing = s.call("POST", "/api/demo/ingest", { file: "IN-ATTACK-3.eml" });
      let buf = "";
      while (!buf.includes("event: case")) buf += new TextDecoder().decode((await reader.read()).value);
      const r = await ing;
      assert.match(buf, new RegExp(`data: \\{"id":"${r.json.caseId}"\\}`));
      ctrl.abort();
      const missing = await s.call("POST", "/api/demo/ingest", { file: "NOPE.eml" });
      assert.equal(missing.status, 404);
    } finally { await s.close(); }
  });

  test("model is up only for a reachable local endpoint", async () => {
    const ok = (async () => new Response("{}", { status: 200 })) as unknown as typeof fetch;
    let s = await start({ llmBaseUrl: "http://localhost:8000/v1", fetchImpl: ok });
    try {
      const r = await s.call("GET", "/api/status");
      assert.equal(r.json.model.up, true);
      assert.equal(r.json.mode, "model");
      assert.equal(r.json.model.endpoint, "http://localhost:8000/v1");
    } finally { await s.close(); }
    s = await start({ llmBaseUrl: "https://api.example.com/v1", fetchImpl: ok });
    try {
      const r = await s.call("GET", "/api/status");
      assert.equal(r.json.model.up, false, "non-local endpoints are refused");
      assert.equal(r.json.mode, "rules-only");
    } finally { await s.close(); }
  });
});
