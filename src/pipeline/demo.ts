// npm run demo: fresh demo DB, process every email in data/emails/incoming, print what happened.
// Uses the local model only if LLM_BASE_URL is set (in .env or the environment); otherwise rules only.
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, REPO_ROOT } from "../db/index.js";
import { processDir } from "./index.js";
import { verifyAuditChain, listCases } from "../cases/index.js";
import { listAlerts } from "../alerts/index.js";

const envFile = join(REPO_ROOT, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

const dbPath = process.env.DEMO_DB_PATH ?? join(REPO_ROOT, "data", "demo.db");
if (dbPath !== ":memory:" && existsSync(dbPath)) rmSync(dbPath);
const db = openDb(dbPath);
loadFixtures(db);

const useLlm = !!process.env.LLM_BASE_URL;
console.log(`Invoice Guard demo · model: ${useLlm ? process.env.LLM_BASE_URL : "off (rules only; set LLM_BASE_URL to use the GB10)"}` +
            ` · Slack: ${process.env.SLACK_WEBHOOK_URL ? "on" : "off"}\n`);

const results = await processDir(db, join(REPO_ROOT, "data", "emails", "incoming"), { llm: useLlm ? undefined : false });

const rows = results.map((r) => ({
  message: r.file.replace(/\.eml$/, ""),
  vendor: r.vendorName ?? "(unknown)",
  decision: r.skipped ? "skipped" : r.decision!.outcome,
  "top findings": r.skipped ? "" : r.decision!.top.map((f) => f.check).join(", ") || "-",
  case: r.caseId ?? "-",
}));
const cols = Object.keys(rows[0]) as (keyof (typeof rows)[0])[];
const width = (c: (typeof cols)[number]) => Math.max(c.length, ...rows.map((r) => String(r[c]).length));
const line = (r: Record<string, string>) => cols.map((c) => String(r[c]).padEnd(width(c))).join("  ");
console.log(line(Object.fromEntries(cols.map((c) => [c, c]))));
console.log(cols.map((c) => "-".repeat(width(c))).join("  "));
for (const r of rows) console.log(line(r as any));

const audit = verifyAuditChain(db);
console.log(`\ncases opened: ${listCases(db).length} · alerts in feed: ${listAlerts(db).length} · audit chain: ${audit.ok ? "OK" : `BROKEN at event ${audit.firstBadId}`} (${audit.events} events)`);
const rq = db.prepare("SELECT hold_id, recipient_name, text FROM requester_checks").all() as any[];
for (const q of rq) console.log(`\n${q.hold_id} → ask ${q.recipient_name}: "${q.text}"`);
const cb = db.prepare("SELECT hold_id, phone FROM callbacks").all() as any[];
for (const c of cb) console.log(`${c.hold_id} → phone callback to ${c.phone} (number on file)`);
console.log(`\nDB: ${dbPath}`);
db.close();
