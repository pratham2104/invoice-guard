// Slack bot (T18): case cards via chat.postMessage + Socket Mode buttons wired to src/cases.
// Idea from Chetas's branch (Socket Mode, Block Kit); written fresh. Cards carry vendor, decision, top reason,
// case id and state only: never invoice data or bank numbers. Every button goes through src/cases, so Slack
// can't bypass a control: unknown users, the agent, non-managers approving and self-approval are all refused.
import { existsSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { DB } from "../db/index.js";
import type { Finding } from "../fingerprint/types.js";
import * as cases from "../cases/index.js";
import { PHRASES, scrub } from "./index.js";

// ------------------------------------------------------------------ config (secrets never logged)
export interface SlackConfig { botToken?: string; appToken?: string; channelId?: string; webhookUrl?: string }

export const DEFAULT_SLACK_ENV = join(homedir(), ".invoice-guard-slack.env");

/** Load tokens from a chmod-600 env file (default ~/.invoice-guard-slack.env). Returns warnings, never values. */
export function loadSlackEnv(path = process.env.SLACK_ENV_FILE ?? DEFAULT_SLACK_ENV): string[] {
  if (!existsSync(path)) return [];
  const warnings: string[] = [];
  const mode = statSync(path).mode & 0o777;
  if (mode & 0o077) warnings.push(`${path} is readable by others (mode ${mode.toString(8)}); run: chmod 600 ${path}`);
  process.loadEnvFile(path);
  return warnings;
}

export function slackConfig(env: NodeJS.ProcessEnv = process.env): SlackConfig {
  const cfg: SlackConfig = {
    botToken: env.SLACK_BOT_TOKEN || undefined, appToken: env.SLACK_APP_TOKEN || undefined,
    channelId: env.SLACK_CHANNEL_ID || undefined, webhookUrl: env.SLACK_WEBHOOK_URL || undefined,
  };
  if (cfg.botToken?.startsWith("xoxp-")) throw new Error("SLACK_BOT_TOKEN is a user token (xoxp-). Use the bot token (xoxb-); user tokens are not allowed.");
  if (cfg.botToken && !cfg.botToken.startsWith("xoxb-")) throw new Error("SLACK_BOT_TOKEN must be a bot token (xoxb-...).");
  if (cfg.appToken && !cfg.appToken.startsWith("xapp-")) throw new Error("SLACK_APP_TOKEN must be an app-level token (xapp-...).");
  return cfg;
}

/** For logs: which pieces are configured, without any token text. */
export function describeConfig(c: SlackConfig): string {
  return `bot ${c.botToken ? "set" : "unset"} · app (Socket Mode) ${c.appToken ? "set" : "unset"} · channel ${c.channelId ?? "unset"} · webhook ${c.webhookUrl ? "set" : "unset"}`;
}

/** Slack user ID → Invoice Guard user (roles come from IG_USERS / src/cases users()). */
export function slackUserMap(env: NodeJS.ProcessEnv = process.env): Record<string, string> {
  return env.SLACK_USERS ? JSON.parse(env.SLACK_USERS) : {};
}

// ------------------------------------------------------------------ case card
export const ACTIONS = { start: "ig_start_verification", yes: "ig_confirmed_legit", no: "ig_confirmed_fraud", approve: "ig_approve_release" } as const;

const OUTCOME_TEXT: Record<string, string> = {
  HOLD_FRAUD_RISK: "HELD: fraud risk, phone callback to the number on file",
  HOLD_CONFIRM: "HELD: waiting for the requester to confirm the order",
};
const EMOJI: Record<string, string> = { HOLD_FRAUD_RISK: ":rotating_light:", HOLD_CONFIRM: ":large_yellow_circle:" };

export function caseCard(db: DB, caseId: string): { text: string; blocks: any[] } {
  const c = cases.getCase(db, caseId);
  const vendor = scrub(c.vendor_id ? ((db.prepare("SELECT name FROM vendors WHERE id = ?").get(c.vendor_id) as any)?.name ?? "unknown vendor") : "unknown vendor");
  const findings = JSON.parse(c.findings) as Finding[];
  const rank: Record<string, number> = { high: 3, medium: 2, low: 1, info: 0, unknown: 0 };
  const top = [...findings].sort((a, b) => rank[b.severity] - rank[a.severity]).slice(0, 3);
  const why = [...new Set(top.map((f) => PHRASES[f.check] ?? f.check.replace(/_/g, " ")))].join("; ") || "no specific reason";
  const confirmWho = c.next_step === "requester_confirmation" ? "Requester" : "Vendor";
  const buttons: any[] = [];
  const btn = (text: string, action_id: string, style?: "primary" | "danger") =>
    ({ type: "button", text: { type: "plain_text", text }, action_id, value: caseId, ...(style ? { style } : {}) });
  if (c.state === "OPEN") buttons.push(btn("Start verification", ACTIONS.start, "primary"));
  if (c.state === "AWAITING_VENDOR" || c.state === "AWAITING_REQUESTER") {
    buttons.push(btn(`${confirmWho} confirmed legit`, ACTIONS.yes, "primary"), btn("Confirmed fraud", ACTIONS.no, "danger"));
  }
  if (c.state === "READY_FOR_APPROVAL") buttons.push(btn("Approve release", ACTIONS.approve, "primary"));
  const outcome = OUTCOME_TEXT[c.outcome] ?? c.outcome;
  const next = c.state === "OPEN" ? (c.next_step === "requester_confirmation" ? "Ask the PO requester whether they ordered this." : "Call the vendor on the number on file. Never use contact details from the email.")
    : c.state === "AWAITING_VENDOR" ? "Waiting for the callback result." : c.state === "AWAITING_REQUESTER" ? "Waiting for the requester's yes or no."
    : c.state === "READY_FOR_APPROVAL" ? "Verified. A manager who didn't run verification can release it." : `Closed: ${c.state}.`;
  const blocks: any[] = [
    { type: "header", text: { type: "plain_text", text: scrub(`${caseId} · payment ${outcome}`).slice(0, 150) } },
    { type: "section", text: { type: "mrkdwn", text: scrub(`${EMOJI[c.outcome] ?? ""} *Vendor:* ${vendor}\n*State:* \`${c.state}\`\n*Why:* ${why}\n*Next:* ${next}`) } },
    { type: "context", elements: [{ type: "mrkdwn", text: "_Alerts are a heads-up; the data stays on the box._" }] },
  ];
  if (buttons.length) blocks.push({ type: "actions", block_id: `ig_case_${caseId}`, elements: buttons });
  return { text: scrub(`${caseId}: ${vendor} — ${outcome}. Why: ${why}.`), blocks };
}

// ------------------------------------------------------------------ posting
export interface ChatClient {
  chat: {
    postMessage(args: { channel: string; text: string; blocks: any[] }): Promise<{ ok?: boolean; ts?: string; channel?: string; error?: string }>;
    update(args: { channel: string; ts: string; text: string; blocks: any[] }): Promise<{ ok?: boolean }>;
  };
}

export async function postCaseCard(client: ChatClient, channel: string, db: DB, caseId: string) {
  const card = caseCard(db, caseId);
  const res = await client.chat.postMessage({ channel, ...card });
  return { sent: !!res.ok, ts: res.ts, channel: res.channel ?? channel, error: res.error };
}

/** A Web API client if the bot token + channel are configured, else null (callers fall back to the webhook). */
export async function botFromEnv(env: NodeJS.ProcessEnv = process.env): Promise<{ client: ChatClient; channel: string } | null> {
  const cfg = slackConfig(env);
  if (!cfg.botToken || !cfg.channelId) return null;
  const { WebClient } = await import("@slack/web-api");
  return { client: new WebClient(cfg.botToken) as unknown as ChatClient, channel: cfg.channelId };
}

// ------------------------------------------------------------------ buttons → case transitions
export interface ActionInput { actionId: string; caseId: string; slackUserId: string }
export interface ActionResult { ok: boolean; message: string; state?: string }

/** Pure: apply one button press through src/cases. Every control lives there, not here. */
export function handleAction(db: DB, a: ActionInput, userMap: Record<string, string>): ActionResult {
  const user = userMap[a.slackUserId];
  if (!user) return { ok: false, message: `Blocked: your Slack account (${a.slackUserId}) isn't mapped to an Invoice Guard user.` };
  try {
    switch (a.actionId) {
      case ACTIONS.start: cases.startVerification(db, a.caseId, user); break;
      case ACTIONS.yes: cases.recordConfirmation(db, a.caseId, user, true, "via Slack"); break;
      case ACTIONS.no: cases.recordConfirmation(db, a.caseId, user, false, "via Slack: confirmed fraud"); break;
      case ACTIONS.approve: cases.approve(db, a.caseId, user); break;
      default: return { ok: false, message: `Unknown action ${a.actionId}.` };
    }
    const state = cases.getCase(db, a.caseId).state;
    return { ok: true, message: `${a.caseId} is now ${state} (by ${user}).`, state };
  } catch (e) {
    if (e instanceof cases.ControlError) return { ok: false, message: `Blocked: ${e.message}` };
    throw e;
  }
}

/** Minimal shape of a Bolt App we use, so tests can pass a fake. */
export interface BoltLike {
  action(id: RegExp | string, fn: (args: any) => Promise<void>): unknown;
}

export function registerHandlers(app: BoltLike, db: DB, userMap: () => Record<string, string> = () => slackUserMap()) {
  app.action(/^ig_/, async ({ ack, body, client, respond, action }: any) => {
    await ack();
    const caseId = String(action?.value ?? body?.actions?.[0]?.value ?? "");
    const res = handleAction(db, { actionId: String(action?.action_id ?? body?.actions?.[0]?.action_id), caseId, slackUserId: String(body?.user?.id) }, userMap());
    if (!res.ok) {
      await respond({ text: `:no_entry: ${res.message}`, response_type: "ephemeral", replace_original: false });
      return;
    }
    const card = caseCard(db, caseId);
    if (body?.channel?.id && body?.message?.ts) await client.chat.update({ channel: body.channel.id, ts: body.message.ts, ...card });
  });
}
