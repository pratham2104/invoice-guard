# GB10 event-day setup checklist

Read 2026-10-24 about 10:02Z. Event: 2026-10-25, sprint 10:00-18:00 PT, submit by 18:00 PT (public Luma listing quoted in `docs/HACKATHON_COMPLIANCE.md`).

**Nothing on this page has been executed on a GB10.** Every command below was found by grepping `docs/GB10_RUNBOOK.md` or the pinned NemoClaw docs at `/home/923873155/Dell X NVIDIA Hack/refs/NemoClaw/docs` (written `refs/NemoClaw/docs` below; `$$nemoclaw` in those docs is a placeholder for `nemoclaw`). A command with a citation was found there; a command marked **NOT FOUND** was not and must be checked on site (`nemoclaw --help`, https://docs.nvidia.com/nemoclaw/latest/). Syntax is version dependent (`docs/GB10_RUNBOOK.md`).

Whether a "Dell Pro Max GB10" is treated as a DGX Spark by NemoClaw is **unverified**: the pinned docs list "DGX OS (Spark)" as Tested (`refs/NemoClaw/docs/reference/platform-support.mdx` line 81, `get-started/prerequisites.mdx` line 105) and never mention "Dell". One profile ID contains `dgx-spark-gb10` (`inference/set-up-llama-cpp.mdx` line 210). `nemoclaw host probe` and `nemoclaw profiles list` are the on-site checks.

## 1. Cross-architecture warnings (x86_64 prep host versus arm64 GB10)

| Item | Warning | Source |
|---|---|---|
| Prep host | x86_64, 2x RTX 3090, 125.5 GiB RAM, driver 535.288.01 (`artifacts/preflight/host.json`, observed). The GB10 is arm64 with unified memory (the NemoClaw docs describe DGX Spark unified-memory behaviour, `refs/NemoClaw/docs/inference/set-up-vllm.mdx`) | observed |
| Binaries do not transfer | `~/.local/bin/openshell` on the prep host is an x86-64 static executable (`file` output). Do not copy it, `node_modules`, wheels, CUDA builds or images to the GB10 | observed; `offline-kit/README.md` says the same |
| Images | Pull or save with the arm64 platform. The pinned sandbox image index lists arm64 manifest `sha256:f0975cb4...`; amd64 is `sha256:c28dcf5e...` (`docs/GB10_RUNBOOK.md`) | runbook |
| Stdlib-only core | PHANTOMSHIFT core is Python 3.10+ standard library only (`README.md`, `DECISIONS.md` item 1), so the core has no wheel risk. Tests were run on Python 3.13.12 here (`host.json`); the GB10's Python version is unverified | README |
| Python version | GB10 Python version unknown. Check before relying on `from __future__ import annotations` style typing | unverified |
| Rootless Docker here | Prep host Docker is rootless and was started with `DOCKER_IGNORE_BR_NETFILTER_ERROR=1` because `br_netfilter` is missing (`DECISIONS.md` item 9). The GB10 is a different setup; the NemoClaw installer can install Docker and add you to the `docker` group (`refs/NemoClaw/docs/get-started/prerequisites.mdx`) | decisions |
| Model memory | On DGX Spark an operator-managed vLLM with a large checkpoint or long context can exhaust unified memory and freeze the host (`NVRM NV_ERR_NO_MEMORY`). Prefer the managed profile or lower `--gpu-memory-utilization`, `--max-model-len`, `--max-num-seqs`, `--max-num-batched-tokens` (`refs/NemoClaw/docs/inference/set-up-vllm.mdx`, warning at lines 89-91; `reference/troubleshooting.mdx` section "DGX Spark") | docs |
| Local NIM on arm64 | Some NIM images may not publish a `linux/arm64` manifest (`reference/platform-support.mdx` line 108) | docs |
| Offline install | NemoClaw docs list **air-gapped / offline installs as Unsupported**; onboarding assumes network for package fetches, container pulls and provider validation (`reference/platform-support.mdx` line 175). The GB10 needs network at install time, or you must be willing to stage and test an undocumented path | docs |
| Telemetry | The installer and CLI attempt anonymous operation telemetry to an NVIDIA receiver unless `NEMOCLAW_DISABLE_TELEMETRY=1` (`get-started/quickstart.mdx` line 39). Decide before the demo and disclose either way | docs |
| `lkg` moves | The installer follows the maintained last-known-good release by default (`get-started/quickstart.mdx`, installer section). Our docs are commit `f00fb1d` (docs "v0.0.137"). The prep host's `nemoclaw --version` printed `nemoclaw v0.0.137` and `openshell --version` printed `openshell 0.0.116` when I ran them at 09:54Z. Compare after installing on the GB10 | runbook, observed |

## 2. Offline stage contents

Directory `/home/923873155/Dell X NVIDIA Hack/offline-stage/` as read at about 10:02Z. A downloader (`fetch_gb10_assets.sh`) was running at that time, so this table is a snapshot.

| Path | What it is | Size / checksum | State |
|---|---|---|---|
| `NemoClaw-f00fb1d-src.tar.gz` | NVIDIA/NemoClaw `lkg` at `f00fb1d`, `.git` stripped (docs, installer, blueprint) | 58,223,922 bytes; no `.sha256` file for it in the stage (the runbook says it was archived with a checksum, I did not find one); sha256 begins `9f6be2f6` when I computed it | present |
| `nemoclaw-bootstrap.sh` | Official `https://www.nvidia.com/nemoclaw.sh` as downloaded | 16,741 bytes; sha256 `539c25cf06c9adce2b7f5756d1acd253f8eddde6e59f60b5eace92c4a123a116` (computed; matches the prefix in `offline-kit/README.md`) | present |
| `images/openclaw-sandbox-arm64.tar` | Pinned sandbox image, linux/arm64, OCI layout | 1,460,778,496 bytes; `images/openclaw-sandbox-arm64.tar.sha256` says `15cd4714...`, and `sha256sum -c` printed `OK` | present, **load not tested** |
| `pull.log` | Log of the image pull and save | 60 lines | last line is an error from the save step: `unable to create manifests file: NotFound: content digest sha256:c28dcf5e...` (the amd64 manifest, which was not pulled). The tar still exists and its OCI `index.json` lists the arm64 manifest `f0975cb4...`. Whether `docker load` accepts it is **unverified** |
| `fetch_gb10_assets.sh`, `fetch.log` | Downloader for the model and a vLLM image. Script text: pinned to NemoClaw `f00fb1d` recipes; downloads `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` at revision `0dcd680e5585c791728c83342b311d0a0026dbeb`, pulls `vllm/vllm-openai@sha256:3af90144...` for arm64, saves `images/vllm-openai-arm64.tar` plus a checksum | in progress at 10:01Z (log showed only step 1 started) | **incomplete** |
| `models/nemotron-3.5-lightning-30b-a3b-nvfp4/` | Partial model download: metadata files plus 5 of 52 safetensors shards present at 10:01Z | not checksummed | **incomplete**; licence not checked (`offline-kit/README.md` requires it); that this model suits the GB10 profile is unverified |

Not staged (per `offline-kit/README.md`): OpenShell 0.0.116 arm64 binary, `@nvidia/openshell-sdk` npm packages, the OpenClaw npm tarball. The installer fetches these at install time. `offline-kit/manifest.sha256` holds one line (its own README) and does not cover the stage.

Pinned versions (`docs/GB10_RUNBOOK.md`): OpenShell `0.0.116`, OpenClaw `>= 2026.3.11`, Node `>= 22.19`, npm `>= 10`, Docker Engine. Prep host has Node v22.22.2 (`host.json`).

## 3. Ordered checklist

Status column: **FOUND** = command text located at the cited path; **NOT FOUND** = not in the two allowed sources.

### Phase A. Before touching the GB10 (on the USB or laptop)

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| A1 | Verify the staged image checksum | `sha256sum -c images/openclaw-sandbox-arm64.tar.sha256` | `offline-kit/README.md` step 4 (`sha256sum -c`), not the runbook and not the NemoClaw docs | **NOT FOUND** in allowed sources (standard coreutils) |
| A2 | Verify the bootstrap script checksum against the value in section 2 | `sha256sum nemoclaw-bootstrap.sh` | not in allowed sources | **NOT FOUND** |
| A3 | Confirm no secret is on the drive | none | `offline-kit/README.md` step 5 | rule, no command |
| A4 | Ask organizers: prebuilt-code rules, submission format, offline allowance, whether the GB10 has internet | n/a | `docs/HACKATHON_COMPLIANCE.md` "Questions for organizers" | unknown, do not guess |

### Phase B. Identify the machine and install (08:30 to 10:00 PT)

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| B1 | Record the host facts | `python3 scripts/verify_hackathon.py --mode prep` (project script; H02 passes only on aarch64 plus a "GB10" GPU string) | `README.md`, `scripts/verify_hackathon.py` | project command |
| B2 | Optionally suppress NemoClaw telemetry in every shell used | `export NEMOCLAW_DISABLE_TELEMETRY=1` | `refs/NemoClaw/docs/get-started/quickstart.mdx` line 39 | FOUND |
| B3 | Install (follows `lkg`) | `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash` | `get-started/quickstart.mdx` line 46; `docs/GB10_RUNBOOK.md` | FOUND |
| B3b | Or pin a release | `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| NEMOCLAW_INSTALL_REF= NEMOCLAW_INSTALL_TAG=vX.Y.Z bash` (replace `vX.Y.Z`; the tag matching `f00fb1d` is unverified) | `get-started/quickstart.mdx` line 162 | FOUND (placeholder tag) |
| B4 | If the installer prints `newgrp docker`, run it and retry | `newgrp docker` | `get-started/prerequisites.mdx` line 43; `quickstart.mdx` | FOUND |
| B5 | Confirm CLI | `nemoclaw --version` | `reference/commands.mdx` line 206 | FOUND |
| B6 | Read-only readiness report (exit 0 supported, 2 incompatible, 3 inconclusive) | `nemoclaw host probe` | `reference/commands.mdx` line 376 | FOUND |
| B7 | List serving profiles for this host | `nemoclaw profiles list` | `reference/commands.mdx` line 407; `docs/GB10_RUNBOOK.md` | FOUND |
| B8 | If the installer offers express install on a supported DGX host, press Enter at `Run express install with these settings? [Y/n]` | n/a | `docs/GB10_RUNBOOK.md`; `get-started/quickstart.mdx` | FOUND (prompt) |

### Phase C. Local inference (target: runtime up by 10:00 to 11:15 PT, `PROGRESS.md`)

Never pick a hosted provider (`build`, `openrouter`, `openai`, `anthropic`, `gemini`): that breaks "all inference local" (`docs/GB10_RUNBOOK.md`).

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| C1 | Select a managed profile | `nemoclaw onboard --profile <profile-id>` | `refs/NemoClaw/docs/inference/set-up-vllm.mdx` line 141; runbook | FOUND |
| C2 | Or reuse a running vLLM on `localhost:${NEMOCLAW_VLLM_PORT:-8000}`, then run onboarding and choose Local vLLM | `nemoclaw onboard` | `inference/set-up-vllm.mdx`, "Use an Existing Server" | FOUND |
| C3 | Example server with structured tool calls (flags depend on the model family) | `vllm serve /models/Hermes-3-Llama-3.1-8B --served-model-name hermes-3-llama-3.1-8b --enable-auto-tool-choice --tool-call-parser hermes --host 0.0.0.0 --port 8000` | `inference/set-up-vllm.mdx` (near line 106) | FOUND as an example only; `--host 0.0.0.0` conflicts with the same page's warning not to expose the port beyond loopback and the OpenShell bridge. Another page shows `--host 127.0.0.1 --port 8000` (`inference/set-up-openai-compatible-endpoint.mdx` line 42). Which bind address works with the sandbox route is **unverified** |
| C4 | Managed vLLM on generic Linux (not expected on a GB10) | `NEMOCLAW_PROVIDER=install-vllm nemoclaw onboard --non-interactive` | `inference/set-up-vllm.mdx` line 78 | FOUND |
| C5 | Confirm route, then sandbox health | `nemoclaw inference get` then `nemoclaw my-assistant status` | `inference/verify-inference-route.mdx` lines 20 and following | FOUND |
| C6 | Diagnose | `nemoclaw my-assistant doctor` | `inference/choose-local-inference-server.mdx` line 150; `reference/commands.mdx` | FOUND |
| C7 | Resume an interrupted onboarding | `nemoclaw onboard --resume` | `get-started/quickstart.mdx` line 86 | FOUND |
| C8 | Prove local inference for H03 | write `artifacts/runtime-verification/local-inference.json` from real command output, do not hand-write | `docs/GB10_RUNBOOK.md` | rule |
| C9 | Check the static inference gate against the real config | `phantomshift/inference_gate.py` `check_inference_config(config, "competition", env)` (library call, no CLI) | module docstring | project code; may flag `host.openshell.internal` (unverified) |

### Phase D. Sandbox and agent

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| D1 | Status | `nemoclaw my-assistant status` | `get-started/quickstart.mdx` line 89 | FOUND |
| D2 | Sandbox shell, then TUI | `nemoclaw my-assistant connect` then `openclaw tui` | `get-started/quickstart.mdx` lines 113-114 | FOUND |
| D3 | Or one command | `nemoclaw launch my-assistant` | `get-started/quickstart.mdx` line 103 | FOUND |
| D4 | Dashboard URL | `nemoclaw my-assistant dashboard-url --quiet` | `get-started/quickstart.mdx` line 97 | FOUND |
| D5 | One agent turn from the host | `nemoclaw my-assistant exec -- openclaw agent --agent main -m "What is 2+2?"` | `reference/commands.mdx` line 1384 | FOUND |
| D6 | Follow logs | `nemoclaw my-assistant logs --follow` | `manage-sandboxes/lifecycle.mdx` line 75 | FOUND |
| D7 | Watch and approve blocked egress | `openshell term` | `network-policy/approve-network-requests.mdx` line 33; `reference/commands.mdx` | FOUND |
| D8 | Optional periodic agent turns (a candidate mechanism for H01, **unverified** as sufficient for the gate) | `export NEMOCLAW_AGENT_HEARTBEAT_EVERY=2h` then `nemoclaw onboard` | `configure-agents/configure-agent-heartbeats.mdx` line 23 | FOUND |

### Phase E. Channel (target: real round trip by 11:15 PT; this path alone counts for the channel gate)

Run on the host, not in the sandbox. Token by silent prompt, never in argv, chat or git (`docs/GB10_RUNBOOK.md`; details in `docs/DISCORD_OPERATOR_GUIDE.md`).

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| E1 | Read the token silently | `read -rsp "Discord bot token: " DISCORD_BOT_TOKEN; echo; export DISCORD_BOT_TOKEN` | `docs/GB10_RUNBOOK.md` | FOUND (runbook) |
| E2 | Set server, user restriction and mention mode (`DISCORD_USER_ID` restricts to one user; without it any server member can command the bot) | `export DISCORD_SERVER_ID=<server id> DISCORD_USER_ID=<your user id> DISCORD_REQUIRE_MENTION=1` | `docs/GB10_RUNBOOK.md`; `refs/NemoClaw/docs/manage-sandboxes/set-up-discord.mdx` lines 17-26 | FOUND |
| E3 | List channels | `nemoclaw my-assistant channels list` | `manage-sandboxes/add-channels-after-onboarding.mdx` line 20 | FOUND |
| E4 | Add Discord (applies the preset, offers a rebuild) | `nemoclaw my-assistant channels add discord` | same file, line 34 | FOUND |
| E5 | Rebuild if deferred | `nemoclaw my-assistant rebuild` | same file, line 104 | FOUND |
| E6 | Channel status | `nemoclaw my-assistant channels status` | `reference/commands.mdx` line 2684 | FOUND |
| E7 | Send a real message as the operator, watch egress and logs | `openshell term`; `nemoclaw my-assistant logs --follow` | troubleshooting "Discord bot logs in, but the channel still does not work" (`reference/troubleshooting.mdx` line 2382) | FOUND |
| E8 | Save a sanitized round trip as `artifacts/runtime-verification/channel.json` with `is_live`, `openclaw_managed`, `type`, `round_trip` | from real output | `scripts/verify_hackathon.py`; runbook | rule |

Intents: the pinned NemoClaw docs and source never mention Discord intents (grep found nothing). The runbook's statement that the bot needs the Message Content intent is **unverified** against NVIDIA docs. Current intent status is in `docs/DISCORD_OPERATOR_GUIDE.md`.

### Phase F. Register the guarded tool (unknown; do not guess)

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| F1 | Install a local skill directory containing `SKILL.md` into the sandbox | `nemoclaw my-assistant skill install ./my-skill/` | `reference/commands.mdx` line 2876 | FOUND; whether a skill is a suitable vehicle for the guarded payment tool is **unverified** (`docs/GB10_RUNBOOK.md` "still unknown") |
| F2 | Copy files into the sandbox | `nemoclaw my-assistant upload ./local-file /sandbox/` | `reference/commands.mdx` line 3239 | FOUND; whether the gateway should run in the sandbox or on the host is undecided (`docs/ARCHITECTURE.md` section 9) |
| F3 | Network policy so the sandbox can reach a host-side gateway | `nemoclaw my-assistant policy add <preset>` appears in docs with specific presets only (`configure-agents/configure-memory-search.mdx` line 37 uses `local-inference`) | docs | the right preset for PHANTOMSHIFT is **NOT FOUND** |

### Phase G. Prove the gates and freeze

| # | Step | Command | Source | Status |
|---|---|---|---|---|
| G1 | Run the competition-mode check | `python3 scripts/verify_hackathon.py --competition` (exits 1 unless H01-H06 are PASS) | `README.md` | project command |
| G2 | Evidence files from real output | `artifacts/runtime-verification/{local-inference,nemoclaw,openshell,channel}.json` | `docs/GB10_RUNBOOK.md` | rule |
| G3 | Capture a debug bundle if something is odd | `nemoclaw debug --sandbox my-assistant --output nemoclaw-debug.tar.gz` | `manage-sandboxes/lifecycle.mdx` line 91 | FOUND; review the bundle for secrets before sharing |
| G4 | Re-measure latency on the GB10 | `python3 -m phantomshift eval` | `README.md` | project command; rewrites `artifacts/benchmarks/results.json` |
| G5 | Warning: the unit tests rewrite `verify.json` and `host.json` in competition mode | `python3 -m unittest discover -s tests -v` | `README.md`; observed | project command |
| G6 | Real-model sampling, only once a local model is serving | `python3 -m phantomshift model-replay --scenario invoice_redirect --model <name> --base-url http://127.0.0.1:8000/v1` | `README.md` (`probe`), `phantomshift/__main__.py` | project command; **never run against any model** |

## 4. Commands I could not find in the allowed sources

| Command | Where it does appear | What to do |
|---|---|---|
| `docker load -i images/openclaw-sandbox-arm64.tar` | nowhere in the runbook or NemoClaw docs (grep for `docker load` found nothing) | Check on site. The installer pulls the managed image by digest itself, so loading may be unnecessary; whether the installer would use a pre-loaded image is unverified |
| `docker pull --platform linux/arm64 ...` | `offline-kit/README.md` and `offline-stage/fetch_gb10_assets.sh` only (the NemoClaw docs only show `docker pull` for other purposes) | Repo command, not NVIDIA documented |
| `sha256sum -c ...` | `offline-kit/README.md` only | Standard coreutils |
| `tar xzf NemoClaw-f00fb1d-src.tar.gz` and an install from the unpacked source | not documented; the docs state offline installs are unsupported | Prefer the documented `curl ... \| bash` with network |
| `nvidia-smi` queries | appear only in troubleshooting prose and a proof script (`reference/troubleshooting.mdx`), not as a setup step | Use `nemoclaw host probe` first |
| A command to register a PHANTOMSHIFT tool with OpenClaw | not found; only `skill install` and `mcp add` exist for other purposes | on-site decision |
| A command to approve via Discord reaction through OpenClaw | the docs never mention reactions | on-site test |
| The exact NemoClaw install tag for `f00fb1d` | only the placeholder `vX.Y.Z` is documented | read `nemoclaw --version` after install |

## 5. State of the prep host's NemoClaw install (read time, not part of the event checklist)

At about 09:54Z `artifacts/preflight/host.json` listed `nemoclaw` as `nemoclaw v0.0.137` and `openshell` as `openshell 0.0.116` under `~/.local/bin`, with `openclaw` null. This is an x86_64 install on the prep host, by the lead, in progress. See `docs/HOST_PREFLIGHT.md` for the table. It proves nothing about the GB10.
