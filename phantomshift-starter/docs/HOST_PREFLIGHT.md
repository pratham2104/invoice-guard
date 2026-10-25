# Host preflight and hackathon gap table

**Status as of my read at 2026-10-24 10:04Z.** This is the preparation host, not the Dell GB10. A NemoClaw install attempt by the lead was in progress while I read; this page states only what the artifacts and files I could read showed at that time and will go stale. Regenerate with `python3 scripts/verify_hackathon.py` (prep mode).

Sources: `artifacts/preflight/host.json` (collected 10:03:06Z), `artifacts/runtime-verification/verify.json` (10:03Z), `artifacts/preflight/gb10.json` (10:01:43Z, written by someone else), `scripts/verify_hackathon.py`, plus a few read-only listings I ran (marked "listing").

## 1. Host facts (`artifacts/preflight/host.json`, observed)

| Field | Value |
|---|---|
| Collected | 2026-10-24T10:03:06Z |
| Mode field | `competition` (see the warning in section 4: the last writer determines this) |
| Architecture | x86_64 |
| OS | Linux 6.8.0-147-generic, glibc 2.39 (`gb10.json`: Ubuntu 24.04.5 LTS) |
| GPUs | 2x NVIDIA GeForce RTX 3090, driver 535.288.01, 24576 MiB each |
| GPU memory in use | about 2.9 and 3.1 GiB at 10:04Z (listing, `nvidia-smi`); shared server |
| RAM | 125.5 GiB |
| Free disk | 633.7 GiB (668.1 GiB at the earlier 09:52Z read; the offline-stage downloads are running) |
| Python | 3.13.12 |
| Looks like a GB10 | no (`gb10.json`: `looks_like_gb10: no`) |

| Tool | `host.json` result at 10:03Z |
|---|---|
| docker | `/usr/bin/docker`, Docker 29.8.1 |
| nemoclaw | `~/.local/bin/nemoclaw`, `nemoclaw v0.0.137` (null in the 09:52Z and earlier reads; installed since) |
| openshell | `~/.local/bin/openshell`, `openshell 0.0.116` (x86-64 executable per `file`) |
| openclaw | **null** (not found) |
| node | v22.22.2 (docs require 22.19 or later) |
| git | 2.43.0 |
| ollama, vllm | null |

Extra observations (listings, not in `host.json`):

| Item | Observation |
|---|---|
| Docker daemon | The default socket `~/.docker/run/docker.sock` does not exist, so plain `docker ps` fails in my shell and `gb10.json` says `docker_daemon_reachable: no`. With `DOCKER_HOST=unix:///home/923873155/.docker/xdg/docker.sock` (the path the offline-stage script uses) the daemon answered: no containers running, one image `ghcr.io/nvidia/openshell-community/sandboxes/openclaw` (5.37 GB). `DECISIONS.md` item 9 says Docker here is rootless with `DOCKER_IGNORE_BR_NETFILTER_ERROR=1` |
| NemoClaw state | `~/.nemoclaw/source` present; `~/.nemoclaw/state` had only empty `mcp-lifecycle-locks` and `tunnel` directories; no `~/.nemoclaw/sandboxes.json`. I read this as: no sandbox created yet (I did not run `nemoclaw list`). This is an inference |
| Model server | none on 127.0.0.1:8000 or 11434 (`verify.json` H03 detail); `PROGRESS.md` says the HF cache holds empty stubs and there is no vLLM |
| Offline-stage downloads | in progress at 10:01Z (model shards and a vLLM arm64 image); see `docs/GB10_SETUP.md` section 2 |
| Discord | token valid, bot in server, operator is a member, intents OFF (`artifacts/runtime-verification/discord-preflight.json`, 09:38Z); see `docs/DISCORD_OPERATOR_GUIDE.md` |

Local-first caveat for this host: nothing here proves anything about the GB10. An x86_64 NemoClaw install would only rehearse commands.

## 2. Gate status (`artifacts/runtime-verification/verify.json`, 10:03Z)

The file was last written in competition mode, so the GB10-only gates show FAIL. In prep mode the same probes show NOT TESTED (`scripts/verify_hackathon.py`: `gb10_only_status` is `NOT TESTED` in prep and `FAIL` in competition). I re-ran prep mode at about 09:57Z and got NOT TESTED for H01-H06, H07 PASS; another run since then flipped it back.

| ID | Gate | Status now (competition-mode file) | Status in prep mode | Detail from the script |
|---|---|---|---|---|
| H01 | Autonomous always-on trigger | NOT TESTED | NOT TESTED | no live OpenClaw agent trace |
| H02 | Runs on Dell Pro Max GB10 | FAIL | NOT TESTED | arch x86_64, two RTX 3090 |
| H03 | Local inference, no remote LLM | NOT TESTED | NOT TESTED | no model server on 127.0.0.1:8000/11434 |
| H04 | NemoClaw + OpenClaw + OpenShell present | FAIL | NOT TESTED | not found: `openclaw` (nemoclaw and openshell found since the install) |
| H05 | Discord/Slack/Telegram via OpenClaw | NOT TESTED | NOT TESTED | no `channel.json` proof file |
| H06 | Final demo on the GB10 | FAIL | NOT TESTED | event-time check |
| H07 | Evidence plus claims audit present | PASS | PASS | `docs/CLAIMS_AUDIT.md` exists (non-mandatory) |

ID mapping: `docs/HACKATHON_COMPLIANCE.md` uses R01-R12, the script uses H01-H07. My mapping is inferred, not stated anywhere: H03 about R01, H04 about R02, H05 about R03, H01 about R04, H02 and H06 about R06, H07 about R07.

## 3. Prioritized gap table (red / yellow / green)

Colour rule: **red** = gate not met and no usable groundwork that moves it; **yellow** = groundwork exists but the gate cannot pass on this host or needs on-site proof; **green** = met. Priority 1 is the critical path in `PROGRESS.md` ("local inference plus a real channel by about 11:15 PT").

| Pri | Gate | Colour | Why | What closes it | Closable on this host? |
|---|---|---|---|---|---|
| 1 | H03 local inference | **red** | No model server, no cached instruct weights here, nothing served on 8000/11434. `inference_gate.py` is only a static config check. Model download to the offline stage is in progress but incomplete | A local model served on the GB10, routed through NemoClaw, with `local-inference.json` from real output | Partly (rehearse a server on the 3090s; shared box, load noted in `PROGRESS.md`); the gate itself no |
| 1 | H04 runtime present | **yellow** | `nemoclaw` v0.0.137 and `openshell` 0.0.116 are installed on this x86_64 host; `openclaw` is not found; no sandbox visible; Docker daemon only reachable through a non-default socket. The script can never output PASS for H04 (see section 4) | OpenClaw sandbox created and healthy on the GB10, `nemoclaw <sandbox> status` saved | Rehearsal only |
| 1 | H05 channel | **yellow** | Bot token valid, operator is a member, rehearsal channel code exists and is stub-tested. Not OpenClaw-managed, no `channel.json`, intents OFF (need unverified), pasted token not shown to be reset | `nemoclaw <sandbox> channels add discord` on the GB10 and a saved real round trip | No |
| 2 | H01 autonomous trigger | **yellow** | `trigger.py` plus `eventstore.py` implement a local-inbox polling stand-in with retries (28 tests passed when I ran them); both say it is not the OpenClaw agent. The script hardcodes NOT TESTED for H01 (see section 4) | A live OpenClaw agent trace in `artifacts/runs/`, and the script taught to accept it | No |
| 2 | H02 / H06 on the GB10 | **red** (by definition off-GB10) | x86_64, RTX 3090 | Run everything on the Dell Pro Max GB10 at the event | No |
| 3 | Tool registration, approval over the real channel | **red** | Both listed as unknown in `docs/GB10_RUNBOOK.md`; not started | On-site decisions; see `docs/GB10_SETUP.md` phases E and F | No |
| 3 | Real model measurements | **red** | `model-replay` exists, tested with a stub only; no model has been run, no `model-*.json` | Run against the local model on the GB10 | Partly |
| 4 | H07 evidence | **green** | `docs/CLAIMS_AUDIT.md` present. This only certifies that the audit exists, not that claims are true | keep the audit current | yes |
| 4 | Application layer | **green (fixture)** | Gateway, approval gate, forks, eval, adapter, event store, trace; unit tests pass (54 at 09:54Z in my full run; later files add more). All fixtures | n/a | yes |
| 4 | Node, disk, RAM prerequisites for the installer | **green** | Node 22.22.2 (needs 22.19+), 633.7 GiB disk, 125.5 GiB RAM, docker CLI present | n/a | yes |
| 4 | Offline kit | **yellow** | Image tar present with a passing checksum but load untested and its save step logged an error; model and vLLM image downloads incomplete; OpenShell, npm packages and OpenClaw tarball not staged; NemoClaw docs list offline installs as Unsupported | Complete, checksum and test-load what can be; plan for network on the GB10 | Partly |
| 5 | R05 buyer interest, R08-R12 administrative | **red / unverified** | No interviews; registration items not tested (`docs/HACKATHON_COMPLIANCE.md`) | People tasks | n/a |

## 4. Findings about the verification script itself (observed by reading `scripts/verify_hackathon.py`)

| Finding | Consequence |
|---|---|
| H01 is hardcoded `NOT TESTED` and never reads a proof file | `--competition` cannot exit 0 as written, even on a GB10, because H01 is mandatory |
| H04 is `NOT TESTED` even when all three binaries are found (comment: "still need proof files"); it never reads `nemoclaw.json` or `openshell.json` | same: H04 cannot reach PASS as written |
| H03 PASS requires `on_gb10` and a live model on 8000/11434, and does not read `local-inference.json` | The runbook tells us to produce `local-inference.json`, `nemoclaw.json`, `openshell.json`, but only `channel.json` is consumed |
| H02 requires `arch` in (`aarch64`, `arm64`) and a GPU string containing "GB10" | If the GB10's `nvidia-smi` name does not contain "GB10", H02 fails even on the right machine; unverified what it prints |
| Every run, including each unit-test run, overwrites `host.json`, `machine.json` and `verify.json`; `tests/test_guardian.py::VerifyScriptTests` runs competition mode | The file you read may be prep or competition mode; check the `mode` field in `host.json`. I clobbered it once with my own test run and restored it with a prep-mode run |
| `python3 -m phantomshift discord-setup` runs the test suite as a subprocess | same clobbering, after it has already posted the status card |

These are script gaps for the lead to fix; I did not edit any code.

## 5. Unverified in this document

* Whether the install attempt in progress completes, and anything about a sandbox created by it.
* That the Docker daemon at the xdg socket is the one NemoClaw will use.
* The GB10's `nvidia-smi` GPU name and whether NemoClaw treats a Dell Pro Max GB10 as a DGX Spark.
* The inferred mapping between R and H identifiers.
