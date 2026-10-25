import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, FIXTURES_DIR, REPO_ROOT } from "../db/index.js";
import { fingerprint, messageFromFixture, buildProfile, compareDomains, isLocalHost, scanPdf, languageChecks } from "./index.js";
import { parseFindings, type LlmClient } from "./llm.js";

const incoming = JSON.parse(readFileSync(join(FIXTURES_DIR, "incoming.json"), "utf8")) as any[];
const expected = JSON.parse(readFileSync(join(FIXTURES_DIR, "expected.json"), "utf8")) as Record<string, any>;

function freshDb() {
  const db = openDb(":memory:");
  loadFixtures(db);
  return db;
}

// --- domains
test("lookalike domains are caught; the real domain and unrelated vendors are not", () => {
  assert.equal(compareDomains("acme-supp1y.com", "acme-supply.com").technique, "homoglyph");
  assert.equal(compareDomains("acmesupply.co", "acme-supply.com").technique, "tld-swap");
  assert.equal(compareDomains("аcme-supply.com", "acme-supply.com").technique, "homoglyph"); // Cyrillic а
  assert.equal(compareDomains("acme-supply.com.billing-portal.net", "acme-supply.com").technique, "subdomain");
  assert.equal(compareDomains("acme-suply.com", "acme-supply.com").technique, "typo");
  assert.equal(compareDomains("acme-supply.com", "acme-supply.com").lookalike, false);
  assert.equal(compareDomains("brightbus.com", "acme-supply.com").lookalike, false);
});

// --- profile
test("Acme's profile captures Maria's normal", () => {
  const db = freshDb();
  const p = buildProfile(db, "V001")!;
  assert.equal(p.domain, "acme-supply.com");
  assert.equal(p.billingDay, 1);
  assert.equal(p.everRequestedBankChange, false);
  assert.equal(p.style.usesUrgentWords, false);
  assert.ok(p.style.signoffs[0].includes("Thanks, Maria"), p.style.signoffs[0]);
  assert.ok(p.invoiceNumbers.includes("ACME-1051"));
  assert.ok(p.sampleEmails.length >= 20);
});

// --- PDF hidden text
test("hidden white 1pt text is found in the forged invoice, but not the white logo text on the real one", async () => {
  const forged = await scanPdf(join(REPO_ROOT, "data", "invoices", "ACME-1051-corrected.pdf"));
  assert.equal(forged.hidden.length, 1);
  assert.match(forged.hidden[0].text, /approve this invoice/);
  assert.ok(forged.hidden[0].reasons.some((r) => r.includes("tiny")));
  assert.ok(forged.hidden[0].reasons.some((r) => r.includes("white")));
  const real = await scanPdf(join(REPO_ROOT, "data", "invoices", "ACME-1051.pdf"));
  assert.equal(real.hidden.length, 0, JSON.stringify(real.hidden));
  assert.match(real.text, /ACME/);
});

// --- the demo scenarios, rule checks only
for (const x of incoming) {
  test(`scenario ${x.scenario}: rule checks find what they must`, async () => {
    const db = freshDb();
    const r = await fingerprint(db, messageFromFixture(x), { llm: false });
    const found = new Set(r.findings.map((f) => f.check));
    const exp = expected[x.scenario];
    for (const c of exp.rule_checks) assert.ok(found.has(c), `${x.id} missing ${c}; got ${[...found].join(", ")}`);
    if (!exp.hold) assert.equal(r.findings.length, 0, `control should be clean, got ${[...found].join(", ")}`);
    for (const f of r.findings) {
      assert.ok(f.expected !== undefined && f.actual !== undefined && f.explanation, `bad finding shape ${JSON.stringify(f)}`);
    }
  });
}

test("scenario 2 is from Maria's real address, so it is not flagged as impersonation", async () => {
  const db = freshDb();
  const x = incoming.find((m) => m.id === "IN-ATTACK-2");
  const r = await fingerprint(db, messageFromFixture(x), { llm: false });
  assert.equal(r.impersonating, false);
  const checks = r.findings.map((f) => f.check);
  assert.ok(!checks.includes("lookalike_domain"));
  assert.ok(!checks.includes("unknown_sender"));
});

// --- language checks (model mocked)
test("scenario 2: language findings from the model are kept, junk checks are dropped", async () => {
  const db = freshDb();
  const x = incoming.find((m) => m.id === "IN-ATTACK-2");
  const mock: LlmClient = {
    async complete(messages) {
      assert.match(messages[1].content, /NEW EMAIL \(untrusted/);
      assert.match(messages[1].content, /Thanks,\nMaria/);
      return '<think>hm</think>{"findings":[' +
        '{"check":"urgency","expected":"never urgent","actual":"process ... today","severity":"high","explanation":"x"},' +
        '{"check":"style_mismatch","expected":"Hi Janet, ... Thanks, Maria","actual":"Dear Accounts Payable Team ... Best Regards","severity":"high","explanation":"x"},' +
        '{"check":"unusual_request","expected":"no bank changes","actual":"do not call our office","severity":"high","explanation":"x"},' +
        '{"check":"approve_payment","expected":"","actual":"","severity":"high","explanation":"injected"}]}';
    },
  };
  const r = await fingerprint(db, messageFromFixture(x), { llm: mock });
  const llmChecks = r.findings.filter((f) => f.source === "llm").map((f) => f.check);
  for (const c of expected["2-hacked-real-email"].llm_checks) assert.ok(llmChecks.includes(c), `missing ${c}`);
  assert.ok(!llmChecks.includes("approve_payment"));
});

test("model offline → one 'unknown' finding, rules still run", async () => {
  const db = freshDb();
  const x = incoming.find((m) => m.id === "IN-ATTACK-1");
  const dead: LlmClient = { async complete() { throw new Error("connect ECONNREFUSED"); } };
  const r = await fingerprint(db, messageFromFixture(x), { llm: dead });
  const unknown = r.findings.filter((f) => f.severity === "unknown");
  assert.equal(unknown.length, 1);
  assert.ok(r.findings.some((f) => f.check === "lookalike_domain"));
});

test("only local inference endpoints are allowed", async () => {
  for (const h of ["localhost", "127.0.0.1", "192.168.1.20", "172.20.10.3", "10.0.0.5", "vllm", "inference.local", "host.openshell.internal"]) {
    assert.ok(isLocalHost(h), h);
  }
  for (const h of ["api.openai.com", "api.anthropic.com", "8.8.8.8", "generativelanguage.googleapis.com"]) {
    assert.ok(!isLocalHost(h), h);
  }
  const db = freshDb();
  const p = buildProfile(db, "V001")!;
  const prev = process.env.LLM_BASE_URL;
  process.env.LLM_BASE_URL = "https://api.openai.com/v1";
  const r = await languageChecks(p, messageFromFixture(incoming[1]));
  process.env.LLM_BASE_URL = prev;
  if (prev === undefined) delete process.env.LLM_BASE_URL;
  assert.equal(r[0].severity, "unknown");
  assert.match(r[0].explanation, /Refusing non-local/);
});

test("parseFindings tolerates thinking blocks and rejects replies with no JSON", () => {
  assert.equal(parseFindings('<think>x</think>{"findings":[]}').length, 0);
  assert.throws(() => parseFindings("I think it's fine"));
});

test("invoice fields can be read straight off the PDF (no structured invoice in the email)", async () => {
  const { parseInvoiceText } = await import("./text.js");
  const scan = await scanPdf(join(REPO_ROOT, "data", "invoices", "ACME-1051-corrected.pdf"));
  const inv = parseInvoiceText(scan.text);
  assert.equal(inv.invoice_number, "ACME-1051");
  assert.equal(inv.amount, 6420);
  assert.equal(inv.bank?.routing, "999000222");
  assert.equal(inv.bank?.account, "8820017745");
  const db = freshDb();
  const x = { ...incoming.find((m) => m.id === "IN-ATTACK-3"), invoice: undefined };
  const r = await fingerprint(db, messageFromFixture(x), { llm: false });
  const checks = r.findings.map((f) => f.check);
  for (const c of ["bank_mismatch", "duplicate_invoice", "hidden_pdf_text"]) assert.ok(checks.includes(c), `missing ${c}: ${checks}`);
});

test("vendor with no email history: style is never judged (T19 false-positive fix)", async () => {
  const db = freshDb();
  const x = incoming.find((m) => m.id === "IN-NORMAL-1");   // Bright Bus: no history emails
  let prompt = "";
  const mock: LlmClient = { async complete(messages) {
    prompt = messages.map((m) => m.content).join("\n");
    return '{"findings":[{"check":"style_mismatch","expected":"","actual":"","severity":"high","explanation":"no past emails to compare"}]}';
  } };
  const r = await fingerprint(db, messageFromFixture(x), { llm: mock });
  assert.match(prompt, /do NOT judge writing style/);
  assert.ok(!prompt.includes("PAST EMAILS"));
  assert.deepEqual(r.findings.map((f) => f.check), []);
});

test("vendor with a baseline still gets the style check", async () => {
  const db = freshDb();
  const x = incoming.find((m) => m.id === "IN-ATTACK-2");
  let prompt = "";
  const mock: LlmClient = { async complete(messages) { prompt = messages[1].content; return '{"findings":[{"check":"style_mismatch","expected":"Hi Janet","actual":"Dear AP Team","severity":"medium","explanation":"x"}]}'; } };
  const r = await fingerprint(db, messageFromFixture(x), { llm: mock });
  assert.match(prompt, /PAST EMAILS \(trusted\)/);
  assert.ok(r.findings.some((f) => f.check === "style_mismatch"));
});
