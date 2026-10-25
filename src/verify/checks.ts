// Local-inference proof (T17). Each check gathers evidence that the AI runs on this box and nowhere else.
// Idea from Chetas's verify_qwen_route.py; written fresh. Every check degrades to "skip" when the
// thing it inspects isn't on this machine (e.g. no GPU on a dev Mac).
import { execFile } from "node:child_process";
import { existsSync, lstatSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { isLocalHost } from "../fingerprint/llm.js";

export type Status = "pass" | "fail" | "warn" | "skip";
export interface CheckResult { id: string; name: string; status: Status; detail: string; data?: Record<string, unknown> }

/** Run a command; never throws. Injected in tests. */
export type Runner = (cmd: string, args: string[], timeoutMs?: number) => Promise<{ ok: boolean; stdout: string; stderr: string; missing: boolean }>;

export const realRunner: Runner = (cmd, args, timeoutMs = 20_000) => new Promise((resolve) => {
  execFile(cmd, args, { timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024 }, (err, stdout, stderr) => {
    const missing = (err as NodeJS.ErrnoException | null)?.code === "ENOENT";
    resolve({ ok: !err, stdout: String(stdout ?? ""), stderr: String(stderr ?? ""), missing });
  });
});

export interface Ctx {
  baseUrl: string;            // e.g. http://127.0.0.1:8000/v1
  model: string;
  run: Runner;
  fetchImpl: typeof fetch;
  env: NodeJS.ProcessEnv;
  home: string;
  platform: NodeJS.Platform;
}

export function defaultCtx(): Ctx {
  return {
    baseUrl: process.env.LLM_BASE_URL ?? "http://127.0.0.1:8000/v1",
    model: process.env.LLM_MODEL ?? "nvidia/Qwen3.6-35B-A3B-NVFP4",
    run: realRunner, fetchImpl: fetch, env: process.env, home: homedir(), platform: process.platform,
  };
}

const r = (id: string, name: string, status: Status, detail: string, data?: Record<string, unknown>): CheckResult => ({ id, name, status, detail, data });

// 1 ---------------------------------------------------------------- GPU
export async function checkGpu(ctx: Ctx): Promise<CheckResult> {
  const name = "GPU";
  const q = await ctx.run("nvidia-smi", ["--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"]);
  if (q.missing) return r("gpu", name, "skip", "nvidia-smi not found (not the GB10)");
  if (!q.ok) return r("gpu", name, "fail", `nvidia-smi failed: ${q.stderr.trim().slice(0, 120)}`);
  const [gpu, used, total] = q.stdout.trim().split("\n")[0].split(",").map((s) => s.trim());
  // GB10 shares memory with the CPU and reports [N/A]; sum per-process GPU memory instead.
  const apps = await ctx.run("nvidia-smi", ["--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"]);
  const procs = apps.ok ? apps.stdout.trim().split("\n").filter(Boolean).map((l) => {
    const [pid, proc, mem] = l.split(",").map((s) => s.trim());
    return { pid: Number(pid), process: proc, usedMiB: Number(mem) || 0 };
  }) : [];
  const appMiB = procs.reduce((n, p) => n + p.usedMiB, 0);
  const usedMiB = /^\d+$/.test(used ?? "") ? Number(used) : appMiB;
  const vllm = procs.some((p) => /vllm|python/i.test(p.process));
  const detail = `${gpu} · ${(usedMiB / 1024).toFixed(1)} GiB in use${total && /^\d+$/.test(total) ? ` of ${(Number(total) / 1024).toFixed(0)} GiB` : ""}` +
    (procs.length ? ` · ${procs.map((p) => `${p.process} ${(p.usedMiB / 1024).toFixed(1)} GiB`).join(", ")}` : "");
  return r("gpu", name, vllm ? "pass" : "warn", vllm ? detail : `${detail} · no vLLM process on the GPU`, { gpu, usedMiB, processes: procs });
}

// 2 ---------------------------------------------------------------- port is loopback-only
export function parseListeners(stdout: string, tool: "ss" | "lsof"): string[] {
  const lines = stdout.trim().split("\n").filter(Boolean);
  if (tool === "ss") return lines.map((l) => l.trim().split(/\s+/)[3]).filter(Boolean);            // Local Address:Port
  return lines.filter((l) => !/^COMMAND/.test(l)).map((l) => (l.match(/TCP\s+(\S+)\s+\(LISTEN\)/) ?? [])[1]).filter(Boolean) as string[];
}

export function isLoopbackAddr(addr: string): boolean {
  const host = addr.replace(/:\d+$/, "").replace(/^\[|\]$/g, "");
  return host === "127.0.0.1" || host === "::1" || host === "localhost" || host.startsWith("127.");
}

export async function checkPort(ctx: Ctx): Promise<CheckResult> {
  const name = "LLM port is loopback-only";
  const url = new URL(ctx.baseUrl);
  const port = url.port || (url.protocol === "https:" ? "443" : "80");
  if (!isLocalHost(url.hostname)) return r("port", name, "fail", `LLM_BASE_URL points off-box: ${url.hostname}`);
  let addrs: string[] = [];
  const ss = ctx.platform === "linux" ? await ctx.run("ss", ["-ltnH", `sport = :${port}`]) : { ok: false, missing: true, stdout: "", stderr: "" };
  if (ss.ok) addrs = parseListeners(ss.stdout, "ss");
  else {
    const lsof = await ctx.run("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"]);
    if (lsof.missing && ss.missing) return r("port", name, "skip", "neither ss nor lsof available");
    addrs = parseListeners(lsof.stdout, "lsof");
  }
  if (!addrs.length) return r("port", name, "skip", `nothing listening on port ${port} here`);
  let container = "";
  const d = await ctx.run("docker", ["ps", "--filter", `publish=${port}`, "--format", "{{.Names}} ({{.Image}})"]);
  if (d.ok) container = d.stdout.trim().split("\n")[0] ?? "";
  const open = addrs.filter((a) => !isLoopbackAddr(a));
  const detail = `port ${port} listens on ${[...new Set(addrs)].join(", ")}${container ? ` · container ${container}` : ""}`;
  return r("port", name, open.length ? "fail" : "pass", open.length ? `${detail} · reachable from the network` : detail, { port, listeners: addrs, container });
}

// 3 ---------------------------------------------------------------- weights on disk
function dirBytes(dir: string): number {
  let n = 0;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    const st = lstatSync(p);
    if (st.isSymbolicLink()) continue;         // HF snapshots symlink into blobs: count each file once
    n += st.isDirectory() ? dirBytes(p) : st.size;
  }
  return n;
}

export async function checkWeights(ctx: Ctx): Promise<CheckResult> {
  const name = "Model weights on this disk";
  const hub = join(ctx.env.HF_HOME ?? join(ctx.home, ".cache", "huggingface"), "hub");
  const dir = join(hub, `models--${ctx.model.replace("/", "--")}`);
  if (!existsSync(dir)) return r("weights", name, "skip", `${dir} not found (weights not on this machine)`);
  const bytes = dirBytes(dir);
  const shards = existsSync(join(dir, "snapshots")) ? readdirSync(join(dir, "snapshots")).flatMap((s) => {
    try { return readdirSync(join(dir, "snapshots", s)).filter((f) => f.endsWith(".safetensors")); } catch { return []; }
  }) : [];
  const gb = bytes / 1e9;
  return r("weights", name, gb > 1 ? "pass" : "warn", `${dir.replace(ctx.home, "~")} · ${gb.toFixed(1)} GB · ${new Set(shards).size} safetensors shards`, { dir, bytes, shards: [...new Set(shards)] });
}

// 4–6 ---------------------------------------------------------------- the local server answers
async function post(ctx: Ctx, path: string, body: unknown, timeoutMs = 120_000) {
  const t0 = Date.now();
  const res = await ctx.fetchImpl(`${ctx.baseUrl.replace(/\/$/, "")}${path}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs),
  });
  const json = (await res.json()) as any;
  return { ok: res.ok, status: res.status, json, ms: Date.now() - t0 };
}

export async function checkModels(ctx: Ctx): Promise<CheckResult> {
  const name = "GET /v1/models lists the model";
  try {
    const res = await ctx.fetchImpl(`${ctx.baseUrl.replace(/\/$/, "")}/models`, { signal: AbortSignal.timeout(10_000) });
    const j = (await res.json()) as any;
    const ids: string[] = (j.data ?? []).map((m: any) => m.id);
    const m = (j.data ?? []).find((x: any) => x.id === ctx.model);
    return r("models", name, m ? "pass" : "fail", m ? `${ctx.model}${m.max_model_len ? ` · context ${m.max_model_len}` : ""}${m.owned_by ? ` · served by ${m.owned_by}` : ""}` : `model not listed; got ${ids.join(", ") || "nothing"}`, { ids });
  } catch (e) {
    return r("models", name, "skip", `no server at ${ctx.baseUrl} (${(e as Error).message})`);
  }
}

export async function checkChat(ctx: Ctx): Promise<CheckResult> {
  const name = "Chat completion (local)";
  try {
    const { ok, json, ms } = await post(ctx, "/chat/completions", {
      model: ctx.model, temperature: 0, max_tokens: 16, chat_template_kwargs: { enable_thinking: false },
      messages: [{ role: "user", content: "Reply with exactly: LOCAL-OK" }],
    });
    const text = String(json.choices?.[0]?.message?.content ?? "").trim();
    const toks = json.usage?.completion_tokens;
    const good = ok && /LOCAL-OK/.test(text);
    return r("chat", name, good ? "pass" : "fail", `${good ? "answered" : "unexpected reply"} "${text.slice(0, 40)}" in ${ms} ms${toks ? ` (${toks} tokens)` : ""}`, { ms, text, usage: json.usage });
  } catch (e) {
    return r("chat", name, "skip", `no server (${(e as Error).message})`);
  }
}

export async function checkToolCall(ctx: Ctx): Promise<CheckResult> {
  const name = "Tool call (local)";
  try {
    const { ok, json, ms } = await post(ctx, "/chat/completions", {
      model: ctx.model, temperature: 0, max_tokens: 200, chat_template_kwargs: { enable_thinking: false },
      tools: [{ type: "function", function: { name: "lookup_vendor", description: "Look up a vendor in the AP vendor master",
        parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } } }],
      tool_choice: "auto",
      messages: [{ role: "user", content: "Look up the vendor Acme School Supply." }],
    });
    const call = json.choices?.[0]?.message?.tool_calls?.[0];
    let args: any = null;
    try { args = JSON.parse(call?.function?.arguments ?? "null"); } catch { /* bad args */ }
    const good = ok && call?.function?.name === "lookup_vendor" && /acme/i.test(String(args?.name ?? ""));
    return r("tools", name, good ? "pass" : "fail", good ? `lookup_vendor(${JSON.stringify(args)}) in ${ms} ms` : `no valid tool call (${JSON.stringify(call ?? json.choices?.[0]?.message ?? {}).slice(0, 120)})`, { ms, call });
  } catch (e) {
    return r("tools", name, "skip", `no server (${(e as Error).message})`);
  }
}

// 8 ---------------------------------------------------------------- egress audit
export const CLOUD_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY",
  "MISTRAL_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY",
  "DEEPSEEK_API_KEY", "XAI_API_KEY", "FIREWORKS_API_KEY", "NVIDIA_API_KEY", "NGC_API_KEY", "PERPLEXITY_API_KEY", "REPLICATE_API_TOKEN"];
export const PROXY_VARS = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "OPENAI_BASE_URL", "OPENAI_API_BASE", "ANTHROPIC_BASE_URL"];

/** Names only, never values. */
export function egressAudit(env: NodeJS.ProcessEnv, baseUrl: string) {
  const keys = CLOUD_KEYS.filter((k) => !!env[k]);
  const proxies = PROXY_VARS.filter((k) => !!env[k]);
  let local = false;
  try { local = isLocalHost(new URL(baseUrl).hostname); } catch { /* bad url */ }
  return { keys, proxies, llmLocal: local };
}

export async function checkEgress(ctx: Ctx): Promise<CheckResult> {
  const name = "No cloud AI keys / proxies; LLM_BASE_URL is local";
  const a = egressAudit(ctx.env, ctx.baseUrl);
  const parts = [`LLM_BASE_URL ${a.llmLocal ? "is local" : "is NOT local"} (${new URL(ctx.baseUrl).host})`,
    a.keys.length ? `cloud AI keys set: ${a.keys.join(", ")}` : "no cloud AI keys in env",
    a.proxies.length ? `proxy/base-url vars set: ${a.proxies.join(", ")}` : "no proxy vars"];
  const status: Status = !a.llmLocal || a.keys.length ? "fail" : a.proxies.length ? "warn" : "pass";
  return r("egress", name, status, parts.join(" · "), a);
}

// 9 ---------------------------------------------------------------- NemoClaw agent route
export function parseNemoclawStatus(out: string): { lines: string[]; inferenceLocal: boolean; localUpstream: boolean } {
  const clean = out.replace(/(token=)[^\s&]+/gi, "$1REDACTED").replace(/\x1b\[[0-9;]*m/g, "");
  const lines = clean.split("\n").map((l) => l.trim()).filter((l) => /inference|route|provider|endpoint|model|upstream|vllm|openai-compatible/i.test(l)).slice(0, 8);
  const inferenceLocal = /inference\.local/i.test(clean);
  const localUpstream = /(127\.0\.0\.1|localhost|host\.openshell\.internal|host\.docker\.internal|\[::1\])(:\d+)?/i.test(clean) || /\bvllm\b/i.test(clean);
  return { lines, inferenceLocal, localUpstream };
}

export async function checkNemoclaw(ctx: Ctx): Promise<CheckResult> {
  const name = "NemoClaw agent inference route";
  const candidates = ["nemoclaw", join(ctx.home, ".local", "bin", "nemoclaw")];
  for (const bin of candidates) {
    const res = await ctx.run(bin, [ctx.env.NEMOCLAW_SANDBOX ?? "my-assistant", "status"], 40_000);
    if (res.missing) continue;
    const out = `${res.stdout}\n${res.stderr}`;
    if (/Failed to acquire lock/i.test(out)) return r("nemoclaw", name, "warn", "nemoclaw is busy (another command holds its lock); rerun later");
    const p = parseNemoclawStatus(out);
    const route = p.inferenceLocal && p.localUpstream;
    return r("nemoclaw", name, route ? "pass" : res.ok ? "warn" : "fail",
      route ? `agent route: inference.local → local vLLM · ${p.lines.slice(0, 3).join(" | ")}` : `${res.ok ? "status ran" : "status failed"}; no inference.local → local route found · ${p.lines.slice(0, 3).join(" | ") || out.trim().slice(0, 120)}`,
      { route, lines: p.lines });
  }
  return r("nemoclaw", name, "skip", "nemoclaw CLI not installed here");
}

/** Last artifact, if any, for cheap reuse (e.g. the demo banner). */
export function readArtifact(path: string): { results: CheckResult[]; at: string } | null {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}
