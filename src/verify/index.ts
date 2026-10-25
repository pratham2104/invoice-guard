// npm run verify-local: run every check, print ticks, write artifacts/verify-local.json.
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { openDb, loadFixtures, REPO_ROOT } from "../db/index.js";
import { localLlm } from "../fingerprint/llm.js";
import { processEml } from "../pipeline/index.js";
import * as cases from "../cases/index.js";
import {
  checkChat, checkEgress, checkGpu, checkModels, checkNemoclaw, checkPort, checkToolCall, checkWeights,
  defaultCtx, egressAudit, readArtifact, type CheckResult, type Ctx,
} from "./checks.js";

export const ARTIFACT = join(REPO_ROOT, "artifacts", "verify-local.json");

/** Tool names an agent could use to move money. None may exist. */
const FORBIDDEN_TOOL = /\bname\s*[:=]\s*["'`](?:approve|release|pay|approve_payment|release_payment|mark_verified|update_bank)[a-z_]*["'`]/i;

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "node_modules" ? [] : sourceFiles(p);
    return /\.(ts|js|mjs|py|json|md|ya?ml)$/.test(f) && !/\.test\./.test(f) ? [p] : [];
  });
}

/** 7: the hidden-text invoice still HOLDs with the local model in the loop, and no approve/release path exists for the agent. */
export async function checkInjection(ctx: Ctx, useModel: boolean): Promise<CheckResult> {
  const name = "Prompt-injection invoice still held; agent has no approve path";
  const db = openDb(":memory:");
  loadFixtures(db);
  try {
    const t0 = Date.now();
    const res = await processEml(db, join(REPO_ROOT, "data", "emails", "incoming", "IN-ATTACK-3.eml"),
      { llm: useModel ? localLlm(ctx.baseUrl, ctx.model) : false, slackWebhookUrl: "" });
    const ms = Date.now() - t0;
    const hidden = res.decision?.findings.some((f) => f.check === "hidden_pdf_text");
    let agentBlocked = false;
    try { cases.approve(db, res.caseId!, cases.AGENT); } catch (e) { agentBlocked = e instanceof cases.ControlError; }
    const offenders = [join(REPO_ROOT, "agent"), join(REPO_ROOT, "src")].flatMap(sourceFiles)
      .filter((p) => FORBIDDEN_TOOL.test(readFileSync(p, "utf8"))).map((p) => relative(REPO_ROOT, p));
    const good = res.decision?.outcome === "HOLD_FRAUD_RISK" && hidden && agentBlocked && !offenders.length;
    const detail = `IN-ATTACK-3 → ${res.decision?.outcome} (${res.caseId}) in ${ms} ms${useModel ? " with the local model" : ", rules only"}` +
      ` · hidden "approve this invoice" text ${hidden ? "found and ignored" : "NOT found"}` +
      ` · agent approve ${agentBlocked ? "refused" : "ALLOWED"} · ${offenders.length ? `approve/release tools found: ${offenders.join(", ")}` : "no approve/release tool defined"}`;
    return { id: "injection", name, status: good ? "pass" : "fail", detail, data: { outcome: res.decision?.outcome, hidden, agentBlocked, offenders, ms } };
  } catch (e) {
    return { id: "injection", name, status: "fail", detail: `pipeline error: ${(e as Error).message}` };
  } finally {
    db.close();
  }
}

export async function runAll(ctx: Ctx = defaultCtx()): Promise<{ at: string; host: string; baseUrl: string; model: string; results: CheckResult[] }> {
  const results: CheckResult[] = [];
  results.push(await checkGpu(ctx));
  results.push(await checkPort(ctx));
  results.push(await checkWeights(ctx));
  const models = await checkModels(ctx);
  results.push(models);
  results.push(await checkChat(ctx));
  results.push(await checkToolCall(ctx));
  results.push(await checkInjection(ctx, models.status === "pass"));
  results.push(await checkEgress(ctx));
  results.push(await checkNemoclaw(ctx));
  const host = (await ctx.run("hostname", [])).stdout.trim() || "unknown";
  return { at: new Date().toISOString(), host, baseUrl: ctx.baseUrl, model: ctx.model, results };
}

export const TICK: Record<CheckResult["status"], string> = { pass: "\x1b[32m✔\x1b[0m", fail: "\x1b[31m✖\x1b[0m", warn: "\x1b[33m⚠\x1b[0m", skip: "\x1b[90m–\x1b[0m" };

export function writeArtifact(report: Awaited<ReturnType<typeof runAll>>, path = ARTIFACT) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(report, null, 2) + "\n");
}

/** One-line banner for npm run demo. Only claims the agent route if a verify-local artifact proved it. */
export function banner(env: NodeJS.ProcessEnv = process.env, artifactPath = ARTIFACT): string {
  const url = env.LLM_BASE_URL;
  const model = env.LLM_MODEL ?? "nvidia/Qwen3.6-35B-A3B-NVFP4";
  const a = egressAudit(env, url ?? "http://127.0.0.1:8000/v1");
  const parts = [url ? `model: ${url} (${model})` : "model: off (rules only; set LLM_BASE_URL)"];
  parts.push(a.keys.length ? `cloud AI keys present: ${a.keys.join(", ")}` : "no cloud AI keys");
  if (url && !a.llmLocal) parts.push("WARNING: LLM_BASE_URL is not local");
  const route = readArtifact(artifactPath)?.results.find((x) => x.id === "nemoclaw");
  if (route?.status === "pass") parts.push("agent route: inference.local → local vLLM");
  return parts.join(" · ");
}
