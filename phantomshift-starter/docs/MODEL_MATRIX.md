# Model matrix and local-inference gates (LM-01..LM-08)

Sources: NemoClaw `lkg` @ `f00fb1d` under `../refs/NemoClaw/managed-inference/{models,recipes,presets}/` and `../refs/NemoClaw/docs/`,
the staging listing in `../offline-stage/`, and the repo's own notes (`PROGRESS.md`, `local-inference/README.md`).
Nothing here was executed against a GB10. "Staged" means bytes are on disk on this dev host; sizes below come from a
directory listing, hashes were **not** recomputed in this pass (`../offline-stage/manifest.sha256`, 199 entries, was written
2026-10-24 10:37). Read `docs/CLAIMS_AUDIT.md` before quoting anything.

## 1. Models and recipes

| | Nemotron 3.5 Lightning 30B-A3B NVFP4 (primary) | Nemotron-3 Nano 4B FP8 (fast tier) | Nemotron-3 Nano 30B-A3B GGUF via llama.cpp (documented fallback) |
|---|---|---|---|
| Model id | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` | `unsloth/Nemotron-3-Nano-30B-A3B-GGUF`, file `Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf` |
| Pinned revision | `0dcd680e5585c791728c83342b311d0a0026dbeb` | `3fe6dab75665a93884214ad4b1b95cf02717d081` | model `9ad8b366c308f931b2a96b9306f0b41aef9cd405`; llama.cpp `8e7f22b67ef4667b4ddd50230771287f328cfb3f` |
| Served name (readiness `expectedModel`) | `nvidia-nemotron-3.5-lightning-30b-a3b-nvfp4` | `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` | `nvidia-nemotron-3-nano-30b-a3b` |
| Size (recipe) | `downloadSizeBytes` 21,561,882,284 | 5,280,000,000 | 22,833,947,424 (sha256 `627f5b04...1887890` in the recipe) |
| Capabilities flags | chat, streaming, toolCalls, reasoning = true; structuredOutputs = false; multimodal = false | same flags as Lightning | toolCalls true, **structuredOutputs true**, parallelToolCalls false, responsesApi false, protocol `openai-completions` |
| Support state of the GB10 preset | `experimental`, validation level `schema` (evidence `managed-inference-catalog-compiler-v1`), `selection: explicit-only`, `interactive: false` | **`supported`**, validation level `hardware` (evidence `preexisting-supported-profile-v0.0.109`), `explicit-only`, `interactive: true` | `experimental`, level `schema`, **`selection: automatic`**, priority 450 |

### GB10 (DGX Spark preset) versus x86 recipes

| | Lightning GB10 `vllm.dgx-spark-gb10.single.nemotron-3.5-lightning-30b-a3b-nvfp4` -> `...spark-single.v1` | Lightning x86 `...linux-amd64-single.v1` | Nano GB10 `vllm.dgx-spark-gb10.single.nemotron-3-nano-4b-fp8` -> `...optimized-arm64-single.v1` | Nano arm64 / amd64 (generic) |
|---|---|---|---|---|
| Image (pinned digest) | `vllm/vllm-openai@sha256:3af90144a0926e5c5fe46ee16e5201e763dd854538b9d7ce433755f11dadaf78` | `vllm/vllm-openai@sha256:c2f3b1b964e47809b722b5e75b61b1e7b39a50f70388cf2bf2418f16a9f31da2` | `nvcr.io/nvidia/vllm@sha256:9204569b17ee4c0eff75194b8e6e458479c8aee18953b5ab9cf359fcdac659e2` | arm64 `nvcr.io/nvidia/vllm@sha256:447995cbb57e...`; amd64 `...@sha256:7be6c2f676c3...` |
| `architecture` | arm64 | amd64 | arm64 | arm64 / amd64 |
| Image download size | 12,691,539,532 B | 9,110,652,559 B | 9,603,085,145 B (unpacked 27,658,526,720 B) | 9,278,081,698 B / 8,928,665,752 B |
| `minimumComputeCapability` | **121** | **90** (comment: NVIDIA's recipe matrix starts at H100) | 89 | 89 |
| `minimumGpuMemoryBytes` | 21,561,882,284 | **96,000,000,000** | 5,280,000,000 | 5,280,000,000 |
| Environment | `VLLM_USE_RUST_FRONTEND: "0"` (comment: `step3p5` parsers are not in the Rust frontend) | none | none | none |

Consequences on this dev host (RTX 3090, compute capability 8.6 per `artifacts/preflight/gb10.json`): the Lightning x86
recipe needs CC 9.0 and 96 GB, so it cannot run here (PROGRESS says the same). The Nano FP8 recipes declare CC 8.9, above
8.6; whether FP8 weights would load on a 3090 was never tested and is not expected to work. The staged images are arm64 and
cannot start on this x86 host at all.

### Key serve arguments and parsers (quoted from the recipes)

Lightning, GB10 (`spark-single.v1`, `executable: /usr/local/bin/vllm`):

```
--max-model-len 65536            --max-num-seqs 1                 --gpu-memory-utilization 0.65
--kv-cache-dtype fp8             --moe-backend marlin             --max-num-batched-tokens 4096
--speculative-config '{"method":"mtp","num_speculative_tokens":1,"moe_backend":"flashinfer_cutlass"}'
--mamba-backend flashinfer       --mamba-ssm-cache-dtype float16  --enable-mamba-cache-stochastic-rounding
--mamba-cache-philox-rounds 5    --enable-prefix-caching          --mamba-cache-mode align
--compilation-config '{"cudagraph_capture_sizes":[1,2,4,8,16,24,32,...,256,1024,2048,4096]}'
--enable-auto-tool-choice        --tool-call-parser step3p5       --reasoning-parser step3p5
```

Lightning, x86: `--max-model-len 65536 --max-num-seqs 1 --gpu-memory-utilization 0.75 --max-num-batched-tokens 4096
--mamba-backend flashinfer --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser nemotron_v3`.
**The GB10 and x86 Lightning recipes use different tool-call and reasoning parsers** (`step3p5` versus `qwen3_coder` /
`nemotron_v3`). Gate LM-03 must therefore be run against the exact recipe that serves the model on the GB10, not assumed from
any other run.

Nano 4B FP8 (all three recipes): `--max-model-len 262144 --gpu-memory-utilization 0.7 --reasoning-parser nemotron_v3
--load-format fastsafetensors --enable-auto-tool-choice --tool-call-parser qwen3_coder`; `sharedMemoryBytes` 68,719,476,736;
all three `directInstall.authentication: none`, `fixedArguments: false`.

Nano-30B llama.cpp (`llama-cpp.nemotron-3-nano-30b-a3b.spark-single.v1`): runtime image
`ghcr.io/nvidia/nemoclaw/llama-cpp-server@sha256:93efd0bec1ed2a7166660edfef9bb743fdfeb3c125d915b43801e69c0befca67`
(1,862,644,330 B; `linux/amd64` and `linux/arm64`), `minimumDriverVersion: 580.65.06`, `gpu.offload: full`,
`cpuFallback: reject`, `memoryBytes: 51539607552`, `port: 8081`, `chatTemplate: nemotron-v3-embedded`,
`contextSize: 262144`, `slots: 1`, `flashAttention: enabled`, KV cache `f16`/`f16`, `speculativeDecoding: disabled`,
`policy.egress: disabled`, `modelDownloads: disabled`.

Memory arithmetic worth knowing for LM-07: the two vLLM recipes ask for `--gpu-memory-utilization` 0.65 (Lightning, GB10) and
0.7 (Nano), which sum to 1.35 of the same memory pool, so they cannot be co-served as written; one must be re-tuned. The
NemoClaw docs also state the managed single-host vLLM runtime is host-global (`docs/inference/set-up-vllm.mdx`, "Handle a
Running vLLM Server"), so a second model means an operator-run server on another port. None of this has been tried.

## 2. What is staged here and what has actually been run

| Asset | Staged here? (listing, `../offline-stage/`) | Run anywhere? |
|---|---|---|
| Lightning NVFP4 checkpoint at rev `0dcd680e...` | `models/nemotron-3.5-lightning-30b-a3b-nvfp4/`: 69 files excluding `.cache`, 21,583,776,248 B (52 safetensors shards; recipe size 21,561,882,284 B, the directory also holds README-type files and images). Listed in the manifest (141 lines mention it). | **No. Never served anywhere.** |
| Lightning arm64 image `vllm/vllm-openai@sha256:3af90144...` | `images/vllm-openai-arm64.tar`, 12,691,571,200 B, `.sha256` beside it; `fetch.log` shows `Digest: sha256:3af90144...` and `SAVE_OK` | **No.** arm64 image on an x86 host; never started. |
| Nano 4B FP8 checkpoint at rev `3fe6dab7...` | `models/nemotron-3-nano-4b-fp8/`: 22 files excluding `.cache`, 5,284,569,483 B. Note `LICENSE` is a 0-byte file in this copy. In the manifest (47 lines). | **No. The FP8 weights never ran.** |
| Nano arm64 image `nvcr.io/nvidia/vllm@sha256:9204569b...` | `images/nvcr-vllm-arm64.tar`, 9,603,180,032 B (`fetch_fallback.log`: `FB_SAVE_OK`) | **No.** |
| OpenClaw sandbox image (arm64 manifest) | `images/openclaw-sandbox-arm64.tar`, 1,460,778,496 B. `pull.log` ends in a `docker save` error naming the amd64 digest; the tar exists, `docker load` acceptance is **unverified** (GB10_SETUP). | **No** (no sandbox was ever created). |
| NemoClaw source `f00fb1d`, bootstrap, PHANTOMSHIFT tarball | present | n/a |
| Nano 4B **Q4_K_M GGUF** (`NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf`, 2,837,072,864 B) | In `../local-inference/models/`, **outside** `offline-stage` and not in its manifest | **Yes: the only model ever run.** llama.cpp CPU build (`3642238`), 3 threads, loaded dev box, 6.4-6.8 tok/s generation, native tool call parsed, model-replay at temperature 0. Not GB10, not FP8, not vLLM. |
| Nano 30B-A3B GGUF (22,833,947,424 B, sha256 pinned in `../local-inference/models/30b.sha256`) | On disk in `../local-inference/models/`, outside `offline-stage` | **No. Downloaded only, never served** (shared-server guardrails). |
| Not staged at all | OpenShell 0.0.116 arm64 binary, `@nvidia/openshell-sdk`, OpenClaw npm tarball (the installer fetches them; offline install is unsupported by NemoClaw per GB10_RUNBOOK). | n/a |

Honest summary: **Lightning and the FP8 Nano have never run; no model has run on a GB10.** The only run is the 4B Q4 GGUF
on CPU, and its numbers carry the caveats in `docs/CLAIMS_AUDIT.md`.

## 3. Routing policy (design, not built into NemoClaw)

| Situation | Route |
|---|---|
| Sensitive task (moves money, sends PII or secrets, or any untrusted content with instruction-like text) or ambiguous | **Lightning** |
| Low-risk task | **Nano** |
| Lightning unavailable and the task is sensitive | **Hold for a human.** Never fall back to Nano for a sensitive task. |
| Any route | The context-bound guard and the authority record still judge every proposed action; a model never approves its own action. |

`scripts/evaluate.py` implements this rule for the mixed baseline (`classify_risk`, `route_for`; held trials are counted
separately). With the three fixture scenarios every task is sensitive, so (f) routes everything to Lightning; the rule only
differs from Lightning-only once low-risk tasks exist. How to express two models inside one NemoClaw/OpenClaw sandbox
(single recorded route versus an OpenClaw `agents.list` sub-agent, `docs/inference/set-up-sub-agent.mdx`) is **UNKNOWN** and
untried; the harness routes outside NemoClaw.

**Do not use NemoClaw's built-in Model Router example.** Verified in the pinned docs:

- `refs/NemoClaw/docs/inference/set-up-model-router.mdx`: the diagram is `Sandbox agent -> OpenShell -> Model Router on port 4000 -> NVIDIA API`; the default pool
  (`nemoclaw-blueprint/router/pool-config.yaml`) lists `gpt-oss-20b-high` and `nemotron-3-super`, both with
  `api_base: "https://integrate.api.nvidia.com/v1"`; non-interactive onboarding needs `NVIDIA_INFERENCE_API_KEY`; the router
  downloads and loads a routing model (`Qwen/Qwen3.5-0.8B` encoder) at start.
- It routes by cost versus predicted accuracy (`tolerance`), not by data sensitivity, and it breaks the "no remote LLM"
  requirement (R01). The doc says the pool file can be edited, so a local-only pool is conceivable, but that is unverified and
  the shipped path is hosted.
- Cross-check: `docs/inference/how-inference-routing-works.mdx` lists Model Router among routes that "retain the shared route".

## 4. Gates LM-01..LM-08 (all NOT_TESTED)

`EV=artifacts/runtime-verification/raw` as in `openclaw-integration/ONSITE_CHECKLIST.md`. "Source" says where the command was
found; **FLAG** means no such command exists in the NemoClaw docs or the checklist and the command is our own proposal.

| Gate | Passes when | Command and evidence file | Source / verification | Status |
|---|---|---|---|---|
| LM-01 | `/v1/models` returns the expected model | `curl -s http://127.0.0.1:8000/v1/models` -> `$EV/h03-host-models.json`; expected id `nvidia-nemotron-3.5-lightning-30b-a3b-nvfp4` (recipe `readiness.expectedModel`). Port is `${NEMOCLAW_VLLM_PORT:-8000}`; the llama.cpp fallback serves on 8081. | ONSITE_CHECKLIST H03 #1; `docs/inference/set-up-vllm.mdx` (NemoClaw queries `/v1/models`). Found. | NOT_TESTED |
| LM-02 | A real chat completion from the GB10 | `curl -s http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"<served name>","messages":[{"role":"user","content":"Reply PONG"}],"max_tokens":16}'` -> `$EV/lm02-chat.json`, saved together with `uname -m` and `nvidia-smi --query-gpu=name --format=csv,noheader` | **FLAG: no direct host chat-completion command in the checklist or docs** (docs only describe `/v1/chat/completions` as what validation calls; `nemoclaw <sb> status` sends one through the route, `docs/inference/verify-inference-route.mdx`). Command is ours; bearer auth may be required for fixed profiles (recipes say `authentication: bearer`). | NOT_TESTED |
| LM-03 | Named and auto tool calls parse with exact arguments | Two requests to `/v1/chat/completions` with `tools:[pay_invoice...]`, one with `"tool_choice":"auto"` and one with `{"type":"function","function":{"name":"pay_invoice"}}`; assert `choices[0].message.tool_calls[0].function.arguments` is JSON equal to the expected args -> `$EV/lm03-toolcalls.json`. Also checklist H04 #13 (`POST http://127.0.0.1:18789/tools/invoke` through OpenClaw) and #10 (agent turn). | **FLAG: the named/auto request pair is ours.** Parser requirement is in `docs/inference/set-up-vllm.mdx` ("Configure Structured Tool Calls": without `--enable-auto-tool-choice` plus a matching parser, calls arrive as text) and `docs/reference/troubleshooting.mdx` "Tool calls appear as assistant text". Precedent: `local-inference/tooltest.json` (llama.cpp, CPU). Parsers differ between recipes (section 1). H04 #13 is marked INFERRED in the checklist. | NOT_TESTED |
| LM-04 | An OpenClaw call passes through `inference.local` and the OpenShell gateway | `nemoclaw inference get --json` -> `$EV/h03-inference-get.json`; `openshell inference get` -> `$EV/h03-openshell-inference.txt`; `nemoclaw <sb> status` -> `$EV/h03-status.txt`; `nemoclaw <sb> agent --agent main --json -m 'Reply with the single word PONG'` -> `$EV/h03-agent-turn.json`; `nemoclaw <sb> logs --since 10m` and `openshell logs <sb> --since 10m` -> `$EV/h03-logs.txt` | ONSITE_CHECKLIST H03 #2, #4, #5, #7, #8. Verified: `inference get --json` and `<name> logs [--since]` are in `docs/reference/commands.mdx`; `<name> agent --agent main -m` at commands.mdx ~1447. `openshell inference get` is **not in the NemoClaw docs** (zero hits) but exists in `openshell inference --help` (0.0.116, run read-only here) and is referenced in NemoClaw source comments; `openshell logs --since` likewise exists in `openshell logs --help` but not in the docs. Caveat: docs say new OpenClaw standalone vLLM/llama.cpp selections use a sandbox-attached provider (`how-inference-routing-works.mdx`), so whether the route is literally `inference.local` is UNKNOWN until `inference get` is read on site. | NOT_TESTED |
| LM-05 | A Discord event yields a locally inferred OpenClaw reply | `nemoclaw <sb> channels add discord` -> `$EV/h05-channels-add.txt`; `nemoclaw <sb> channels status --json` -> `$EV/h05-channels-status.json`; `nemoclaw <sb> logs --follow` while the allowed operator mentions the bot -> `$EV/h05-gateway.log`; `nemoclaw <sb> sessions list` / `sessions export <key>` -> `$EV/h05-session.jsonl`; plus LM-04's route evidence taken in the same window | ONSITE_CHECKLIST H05 #3, #4, #7, #9 and `docs/manage-sandboxes/set-up-discord.mdx`; all found (`channels add discord` 4 doc hits, `channels status` 16, `sessions` 25). **FLAG:** nothing in the docs correlates the Discord turn with a local model request; correlate timestamps with the model server's request log (ours). | NOT_TESTED |
| LM-06 | Nano returns a response with explicit model identity | `curl -s <nano-endpoint>/v1/models` plus a chat completion whose response JSON `model` field equals `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8`; or `python3 scripts/evaluate.py --base-url-nano http://127.0.0.1:<port>/v1` (it refuses to run unless `/models` lists the expected id) -> `artifacts/benchmarks/baselines.json` `served_model_ids` | **FLAG: ours.** Switching the active model is documented (`docs/inference/switch-models.mdx`, `nemoclaw inference set --provider ... --model ...`), but the managed vLLM runtime is host-global, so a second concurrent Nano is an operator-run server. | NOT_TESTED |
| LM-07 | Concurrent run with peak memory, throttling and latency captured | Run `scripts/evaluate.py` with both `--base-url-*` at once while sampling `free -h`, `nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,power.draw,clocks_throttle_reasons.active --format=csv -l 1` and afterwards `journalctl -k --since "1 hour ago" --no-pager \| grep -Ei 'NVRM\|OOM\|out of memory\|lockup\|watchdog'` -> `$EV/lm07-*.csv`, `baselines.json` p50/p95 | `free -h`, `docker ps`, and the `journalctl -k ... grep` line are verbatim from `docs/reference/troubleshooting.mdx` ("Host freezes or logs NVRM NV_ERR_NO_MEMORY", ~2767-2778). **FLAG: the concurrent driver, the `nvidia-smi` sampler and its throttle field names are ours**; `nvidia-smi` may report N/A for memory on a unified-memory GB10. See the 0.65 + 0.70 memory note in section 1. | NOT_TESTED |
| LM-08 | Remote LLM hosts blocked (DNS and network evidence) while Discord egress stays allowed | `nemoclaw <sb> logs --since 10m` and `openshell logs <sb> --since 10m` during LM-04 and LM-05 -> `$EV/h03-logs.txt`; `openshell term` while sending a Discord message (allowed: `discord.com`, `gateway.discord.gg`, nothing new) -> `$EV/h05-term.png`; `nemoclaw <sb> policy list` -> `$EV/h03-policy.txt`, `$EV/h05-policy.txt`; `nemoclaw credentials list` -> `$EV/h03-credentials.txt`; optional DNS probes `openshell sandbox exec --name <sb> -- getent hosts host.openshell.internal` and `... getent hosts example.com` | ONSITE_CHECKLIST H03 #6, #8, #9 and H05 #5, #10; the two `getent hosts` lines are verbatim from `docs/reference/troubleshooting.mdx` (~337-338). Caveats found: the docs say in-sandbox direct DNS is **not** a supported health check and a failed lookup is not evidence about policy-covered traffic; the baseline policy still allows `integrate.api.nvidia.com` for the openclaw binary (`nemoclaw-blueprint/policies/openclaw-sandbox.yaml`, `nvidia` entry), so R01 needs `policy list` plus `policy exclude nvidia --dry-run` output, not only a log grep. **FLAG: no documented command that actively attempts a hosted LLM call and shows the deny**; that negative test is ours and its outcome is UNKNOWN. | NOT_TESTED |

Nothing above has been executed; every gate stays NOT_TESTED until its evidence file exists, was produced on the GB10, and
was reviewed. `scripts/verify_hackathon.py` remains the only place a gate can turn PASS.
