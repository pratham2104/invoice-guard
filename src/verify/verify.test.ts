import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  checkChat, checkEgress, checkGpu, checkModels, checkNemoclaw, checkPort, checkToolCall, checkWeights,
  isLoopbackAddr, parseListeners, parseNemoclawStatus, type Ctx, type Runner,
} from "./checks.js";
import { banner, checkInjection, runAll, writeArtifact } from "./index.js";

const missing: Runner = async () => ({ ok: false, stdout: "", stderr: "", missing: true });
function runner(map: Record<string, string | { stdout?: string; stderr?: string; ok?: boolean }>): Runner {
  return async (cmd, args) => {
    const key = Object.keys(map).find((k) => `${cmd} ${args.join(" ")}`.includes(k));
    if (!key) return { ok: false, stdout: "", stderr: "", missing: true };
    const v = map[key];
    return typeof v === "string" ? { ok: true, stdout: v, stderr: "", missing: false } : { ok: v.ok ?? true, stdout: v.stdout ?? "", stderr: v.stderr ?? "", missing: false };
  };
}
const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });
const ctx = (over: Partial<Ctx> = {}): Ctx => ({
  baseUrl: "http://127.0.0.1:8000/v1", model: "nvidia/Qwen3.6-35B-A3B-NVFP4", run: missing,
  fetchImpl: (async () => { throw new Error("fetch failed"); }) as typeof fetch, env: {}, home: mkdtempSync(join(tmpdir(), "vh-")), platform: "linux", ...over,
});

describe("GPU", () => {
  test("GB10 reports [N/A] memory: sums per-process memory instead", async () => {
    const r = await checkGpu(ctx({ run: runner({
      "--query-gpu": "NVIDIA GB10, [N/A], [N/A]\n",
      "--query-compute-apps": "211542, VLLM::EngineCore, 53456\n",
    }) }));
    assert.equal(r.status, "pass");
    assert.match(r.detail, /NVIDIA GB10 · 52\.2 GiB in use/);
    assert.match(r.detail, /VLLM::EngineCore/);
  });
  test("no nvidia-smi → skip", async () => {
    assert.equal((await checkGpu(ctx())).status, "skip");
  });
});

describe("port", () => {
  test("parses ss and lsof", () => {
    assert.deepEqual(parseListeners("LISTEN 0      4096   127.0.0.1:8000 0.0.0.0:*\n", "ss"), ["127.0.0.1:8000"]);
    assert.deepEqual(parseListeners("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\nssh 1 p 5u IPv6 0x1 0t0 TCP [::1]:18000 (LISTEN)\n", "lsof"), ["[::1]:18000"]);
    assert.ok(isLoopbackAddr("127.0.0.1:8000") && isLoopbackAddr("[::1]:8000"));
    assert.ok(!isLoopbackAddr("0.0.0.0:8000") && !isLoopbackAddr("*:8000") && !isLoopbackAddr("[::]:8000"));
  });
  test("loopback-only passes, names the container", async () => {
    const r = await checkPort(ctx({ run: runner({ "ss -ltnH": "LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:*\n", "docker ps": "ig-vllm (vllm/vllm-openai:v0.32.0)\n" }) }));
    assert.equal(r.status, "pass");
    assert.match(r.detail, /ig-vllm/);
  });
  test("bound to 0.0.0.0 fails", async () => {
    const r = await checkPort(ctx({ run: runner({ "ss -ltnH": "LISTEN 0 4096 0.0.0.0:8000 0.0.0.0:*\n" }) }));
    assert.equal(r.status, "fail");
  });
  test("an off-box LLM_BASE_URL fails before looking at ports", async () => {
    assert.equal((await checkPort(ctx({ baseUrl: "https://api.openai.com/v1" }))).status, "fail");
  });
});

describe("weights", () => {
  test("counts real files once (snapshot symlinks into blobs are skipped)", async () => {
    const home = mkdtempSync(join(tmpdir(), "vh-"));
    const dir = join(home, ".cache", "huggingface", "hub", "models--nvidia--Qwen3.6-35B-A3B-NVFP4");
    mkdirSync(join(dir, "blobs"), { recursive: true });
    mkdirSync(join(dir, "snapshots", "abc"), { recursive: true });
    writeFileSync(join(dir, "blobs", "x"), Buffer.alloc(2048));
    symlinkSync(join(dir, "blobs", "x"), join(dir, "snapshots", "abc", "model-00001-of-00001.safetensors"));
    const r = await checkWeights(ctx({ home }));
    assert.equal(r.data!.bytes, 2048);
    assert.deepEqual(r.data!.shards, ["model-00001-of-00001.safetensors"]);
    assert.equal(r.status, "warn"); // tiny: not a real model
  });
  test("missing → skip", async () => {
    assert.equal((await checkWeights(ctx())).status, "skip");
  });
});

describe("server checks (fake fetch)", () => {
  const server = (async (url: string, init?: RequestInit) => {
    if (url.endsWith("/models")) return json({ data: [{ id: "nvidia/Qwen3.6-35B-A3B-NVFP4", max_model_len: 65536, owned_by: "vllm" }] });
    const body = JSON.parse(String(init!.body));
    assert.deepEqual(body.chat_template_kwargs, { enable_thinking: false });
    if (body.tools) return json({ choices: [{ message: { tool_calls: [{ function: { name: "lookup_vendor", arguments: '{"name":"Acme School Supply"}' } }] } }] });
    return json({ choices: [{ message: { content: "LOCAL-OK" } }], usage: { completion_tokens: 4 } });
  }) as typeof fetch;
  test("models, chat, tool call pass", async () => {
    const c = ctx({ fetchImpl: server });
    assert.equal((await checkModels(c)).status, "pass");
    const chat = await checkChat(c);
    assert.equal(chat.status, "pass");
    assert.match(chat.detail, /LOCAL-OK/);
    const tools = await checkToolCall(c);
    assert.equal(tools.status, "pass");
    assert.match(tools.detail, /lookup_vendor/);
  });
  test("wrong model listed fails; no server skips", async () => {
    const other = (async () => json({ data: [{ id: "some-other-model" }] })) as typeof fetch;
    assert.equal((await checkModels(ctx({ fetchImpl: other }))).status, "fail");
    assert.equal((await checkModels(ctx())).status, "skip");
    assert.equal((await checkChat(ctx())).status, "skip");
  });
  test("model that answers in text instead of calling the tool fails", async () => {
    const lazy = (async () => json({ choices: [{ message: { content: "Sure, Acme is a vendor." } }] })) as typeof fetch;
    assert.equal((await checkToolCall(ctx({ fetchImpl: lazy }))).status, "fail");
  });
});

describe("egress audit", () => {
  test("clean env passes; key names reported, values never", async () => {
    assert.equal((await checkEgress(ctx())).status, "pass");
    const r = await checkEgress(ctx({ env: { OPENAI_API_KEY: "sk-secret-value", HTTPS_PROXY: "http://p:3128" } }));
    assert.equal(r.status, "fail");
    assert.match(r.detail, /OPENAI_API_KEY/);
    assert.ok(!JSON.stringify(r).includes("sk-secret-value"));
  });
  test("proxy alone is a warning; NVIDIA cloud key is a fail", async () => {
    assert.equal((await checkEgress(ctx({ env: { HTTPS_PROXY: "http://p:3128" } }))).status, "warn");
    assert.equal((await checkEgress(ctx({ env: { NVIDIA_API_KEY: "nvapi-x" } }))).status, "fail");
  });
});

describe("NemoClaw", () => {
  test("detects inference.local → local vLLM and redacts tokens", () => {
    const p = parseNemoclawStatus("Sandbox: my-assistant (running)\nInference: inference.local → http://host.openshell.internal:8000/v1 (vllm)\nDashboard: http://127.0.0.1:18790/#token=abc123\n");
    assert.equal(p.inferenceLocal, true);
    assert.equal(p.localUpstream, true);
    assert.ok(!p.lines.join().includes("abc123"));
  });
  test("busy lock → warn; missing CLI → skip; cloud route → not pass", async () => {
    assert.equal((await checkNemoclaw(ctx({ run: runner({ "my-assistant status": { ok: false, stderr: "Error: Failed to acquire lock on /x" } }) }))).status, "warn");
    assert.equal((await checkNemoclaw(ctx())).status, "skip");
    const cloud = await checkNemoclaw(ctx({ run: runner({ "my-assistant status": "Inference provider: build.nvidia.com (NVIDIA Endpoint API)\n" }) }));
    assert.notEqual(cloud.status, "pass");
  });
});

describe("injection + whole run", () => {
  test("hidden-text invoice is held and the agent can't approve (rules only)", async () => {
    const r = await checkInjection(ctx(), false);
    assert.equal(r.status, "pass", r.detail);
    assert.equal(r.data!.outcome, "HOLD_FRAUD_RISK");
  });
  test("runAll on a machine with nothing: no fails, artifact written, banner only claims what it proved", async () => {
    const report = await runAll(ctx());
    assert.ok(report.results.length === 9);
    assert.ok(!report.results.some((x) => x.status === "fail"), JSON.stringify(report.results.filter((x) => x.status === "fail")));
    const path = join(mkdtempSync(join(tmpdir(), "va-")), "verify-local.json");
    writeArtifact(report, path);
    const b = banner({ LLM_BASE_URL: "http://127.0.0.1:8000/v1" }, path);
    assert.match(b, /no cloud AI keys/);
    assert.ok(!b.includes("agent route"));
    writeArtifact({ ...report, results: [{ id: "nemoclaw", name: "", status: "pass", detail: "" }] }, path);
    assert.match(banner({ LLM_BASE_URL: "http://127.0.0.1:8000/v1" }, path), /agent route: inference\.local → local vLLM/);
    assert.match(banner({ LLM_BASE_URL: "http://127.0.0.1:8000/v1", ANTHROPIC_API_KEY: "x" }, path), /cloud AI keys present: ANTHROPIC_API_KEY/);
  });
});
