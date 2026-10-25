// npm run slack [-- --demo] [-- --post-open]
// Socket Mode listener for the case-card buttons. Tokens come from ~/.invoice-guard-slack.env (chmod 600) or the
// environment; they are never printed.
//   --demo       fresh demo DB, process data/emails/incoming, post a card for every hold
//   --post-open  post a card for every OPEN case already in the DB
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { openDb, loadFixtures, REPO_ROOT } from "../db/index.js";
import { listCases } from "../cases/index.js";
import { processDir } from "../pipeline/index.js";
import { describeConfig, loadSlackEnv, postCaseCard, registerHandlers, slackConfig, slackUserMap } from "./slack.js";

const envFile = join(REPO_ROOT, ".env");
if (existsSync(envFile)) process.loadEnvFile(envFile);
for (const w of loadSlackEnv()) console.warn(`warning: ${w}`);

const cfg = slackConfig();
console.log(`Slack: ${describeConfig(cfg)}`);
if (!cfg.botToken || !cfg.appToken) {
  console.error("Need SLACK_BOT_TOKEN (xoxb-) and SLACK_APP_TOKEN (xapp-, Socket Mode) in ~/.invoice-guard-slack.env or the environment.");
  process.exit(2);
}
const users = slackUserMap();
if (!Object.keys(users).length) console.warn("warning: SLACK_USERS is empty, so every button press will be refused. Map Slack user IDs to IG users, e.g. SLACK_USERS='{\"U012ABC\":\"omar.reyes\"}'.");

const args = new Set(process.argv.slice(2));
const dbPath = process.env.DB_PATH ?? join(REPO_ROOT, "data", "demo.db");
if (args.has("--demo") && existsSync(dbPath)) rmSync(dbPath);
const db = openDb(dbPath);

const { App, LogLevel } = await import("@slack/bolt");
const app = new App({ token: cfg.botToken, appToken: cfg.appToken, socketMode: true, logLevel: LogLevel.WARN });
registerHandlers(app, db);
await app.start();
console.log("Socket Mode listener running. Buttons on case cards now drive src/cases (roles enforced). Ctrl+C to stop.");

const bot = cfg.channelId ? { client: app.client as any, channel: cfg.channelId } : null;
if ((args.has("--demo") || args.has("--post-open")) && !bot) console.warn("warning: SLACK_CHANNEL_ID is not set, so no cards can be posted.");
if (args.has("--demo") && bot) {
  loadFixtures(db);
  // raiseAlert() picks up the bot from SLACK_BOT_TOKEN + SLACK_CHANNEL_ID and posts a card per hold
  const res = await processDir(db, join(REPO_ROOT, "data", "emails", "incoming"), { llm: process.env.LLM_BASE_URL ? undefined : false });
  console.log(`processed ${res.length} emails, posted ${res.filter((r) => r.caseId).length} case cards`);
} else if (args.has("--post-open") && bot) {
  for (const c of listCases(db).filter((x) => x.state === "OPEN")) {
    const r = await postCaseCard(bot.client, bot.channel, db, c.id);
    console.log(`${c.id}: ${r.sent ? "posted" : `failed (${r.error})`}`);
  }
}
