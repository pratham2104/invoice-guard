# GB10 runbook (from the pinned NemoClaw docs, NOT yet executed anywhere)

Source: NVIDIA/NemoClaw `lkg` at commit `f00fb1d` (2026-10-20, docs "v0.0.137"). Archived in the offline stage with a checksum.
Every command below is copied from those docs. None has been run by us. Run `nemoclaw --help` and check
https://docs.nvidia.com/nemoclaw/latest/ first; syntax is version dependent.

## Pinned versions (from the repo)
- OpenShell / `@nvidia/openshell-sdk`: **0.0.116** (`nemoclaw-blueprint/blueprint.yaml`)
- OpenClaw: >= 2026.3.11
- Sandbox image (multi-arch index, public): `ghcr.io/nvidia/openshell-community/sandboxes/openclaw@sha256:b3d832b596ab6b7184a9dcb4ae93337ca32851a4f93b00765cc12de26baa3a9a`
  - arm64 manifest `sha256:f0975cb409beb3dd87915ca48c4935fa540dbeb55e222e108493980c1573bc8d`, amd64 `sha256:c28dcf5e...`
- Node >= 22.19, npm >= 10, Docker Engine (default runtime). Platform: DGX OS (Spark) = **Tested**. Generic Linux x86 Docker = Tested.

## Install (official bootstrap; we read it, it clones NVIDIA/NemoClaw at `lkg` and runs scripts/install.sh)
```
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```
On a supported DGX host press Enter at "Run express install with these settings? [Y/n]". Onboarding picks the agent (OpenClaw default) and inference provider.
The installer may install Docker and add you to the `docker` group (needs sudo). Pin with `NEMOCLAW_INSTALL_TAG=vX.Y.Z` for reproducibility.

## Local inference (must be local for R01)
- List profiles: `nemoclaw profiles list`; select: `nemoclaw onboard --profile <profile-id>`.
- Or reuse a running vLLM on `localhost:${NEMOCLAW_VLLM_PORT:-8000}`; onboarding detects it via `/v1/models`.
- Managed vLLM on generic Linux needs `NEMOCLAW_EXPERIMENTAL=1` or `NEMOCLAW_PROVIDER=install-vllm`.
- Structured tool calls need the right vLLM parser flags (docs/inference/set-up-vllm.mdx, "Configure Structured Tool Calls").
- Never choose a hosted provider (build, openrouter, openai, anthropic, gemini...) for the demo: that violates R01.

## Discord (R03). Docs: manage-sandboxes/set-up-discord, add-channels-after-onboarding
Run on the HOST, not in the sandbox. Token via a silent prompt, never in argv or git:
```
read -rsp "Discord bot token: " DISCORD_BOT_TOKEN; echo; export DISCORD_BOT_TOKEN
export DISCORD_SERVER_ID=<server id> DISCORD_USER_ID=<your user id> DISCORD_REQUIRE_MENTION=1
nemoclaw <sandbox> channels list
nemoclaw <sandbox> channels add discord      # applies the discord network preset, then offers a rebuild
nemoclaw <sandbox> status
```
- `DISCORD_USER_ID` restricts the bot to one user; without it any server member can command it.
- Bot needs Message Content intent (currently OFF in our bot), plus Server Members per our own setup notes.
- Troubleshooting: docs/reference/troubleshooting "Discord bot logs in, but the channel still does not work"; `openshell term` shows blocked egress.
- Only this path counts for R03. `phantomshift/discord_channel.py` is a rehearsal channel and does not.

## Prove R01-R03 for `scripts/verify_hackathon.py`
Produce `artifacts/runtime-verification/{local-inference,nemoclaw,openshell,channel}.json` from real command output (versions, `nemoclaw <sandbox> status`, a denied egress seen in `openshell term`, a sanitized Discord round trip). Do not hand-write them.

## Still unknown (read on site, do not guess)
- How to register the PHANTOMSHIFT guarded payment tool as an OpenClaw tool/skill (see `docs/configure-agents`, `skills/`, `agents/` in the archive).
- Whether Discord approval can be driven by reactions through OpenClaw, or needs a message reply handled by the agent.
- Whether our nonce/approval gate should be called from the OpenClaw channel handler or a tool.

## Corrections and caveats added after review (2026-10-24)
- **Offline install is unsupported by NemoClaw.** `refs/NemoClaw/docs/reference/platform-support.mdx` (line ~175) lists offline installs as Unsupported. The GB10 needs network at install time (installer, OpenShell 0.0.116, OpenClaw npm tarball, GitHub npm registry for `@nvidia/openshell-sdk`). The offline stage (weights, arm64 images, source) saves the big downloads, not the install. Plan for a hotspot or the venue network for install, then run with no dependency on this server.
- **Telemetry.** The NemoClaw installer/CLI sends telemetry to an NVIDIA receiver unless `NEMOCLAW_DISABLE_TELEMETRY=1` is set. Set it before install if the pitch says "nothing leaves the box"; Discord traffic is separately and knowingly external.
- **Intents.** Reaction approval and @mention commands should not need the Message Content intent (our own rehearsal assumption, unverified against live Discord). Text approvals (`discord_auth.ApprovalBinding`: `approve <nonce> <digest>`) are message-content based and may need it. The pinned NemoClaw docs never mention Discord intents, so this is unverified for the OpenClaw channel.
- **Message-based vs reaction approval:** the digest-exact flow in `discord_auth.py` needs message events; the REST rehearsal channel uses reactions and does not carry the digest in the reaction. They are not wired together.
- **Docker socket on the dev host** is `~/.docker/xdg/docker.sock` (rootless, started manually). Not relevant on the GB10.
- **Unverified:** that NemoClaw's installer will accept a Dell Pro Max GB10 as a DGX Spark profile host (docs never say "Dell"); whether the GB10's `nvidia-smi` name contains "GB10" (our H02 probe requires it); whether `inference_gate.py` flags NemoClaw's own `host.openshell.internal` route as non-loopback.

## OpenClaw integration answers (from `openclaw-integration/README.md`, researched in the pinned docs; tags are in that file)
- **Register the guarded tool as an OpenClaw native plugin**, not a skill: `nemoclaw <sandbox> exec -- openclaw plugins install <path>`, where `register(api)` calls `api.registerTool({name, label, description, parameters, execute})`. Skeleton: `openclaw-integration/plugin/phantomshift-payment-tool/` (tested only against a mock `api` and a stub server, never inside real OpenClaw). `nemoclaw <sandbox> skill install <dir>` (singular `skill`; an earlier note here said `skills`, which was wrong) only adds a SKILL.md and registers no tool. `mcp add` is wrong for this (needs an HTTPS server, rejects loopback and host.openshell.internal).
- **Reach a host service from the sandbox:** default is deny. Use a custom preset with `nemoclaw <sandbox> policy add --from-file <yaml>` (`--dry-run` first; `--trusted-private-host` for a private IP). Pin one host, one port, POST only, the exact path `/api/adapter/submit`, one binary, so the sandbox cannot reach any approval route. Skeleton: `openclaw-integration/policy/phantomshift-adapter-preset.yaml` (allowed_ips, binary and port are placeholders). The host listener must bind the Docker bridge or a private IP, not loopback-only and not 0.0.0.0; avoid ports 8000, 8080, 8081, 11434-11438, 18789+.
- **Approval:** the pinned source shows no extension point to put the nonce gate in the Discord channel handler. Submission goes through the tool; approval must be resolved by trusted code outside the model's control. Reaction delivery to the agent is UNKNOWN: plan on text-message approval (`discord_auth.ApprovalBinding`).
- **H03 evidence caveat:** the baseline policy still allows `integrate.api.nvidia.com` for the openclaw binary. Save full `nemoclaw inference get --json`, `status` and `credentials list` output, not just a grep. Consider `policy exclude` for the baseline `nvidia` entry after a `--dry-run`.
- 11 items remain UNKNOWN until run on site; see `openclaw-integration/README.md` section 6 and `ONSITE_CHECKLIST.md`.

## Rehearsal result on the dev host (2026-10-24 22:10Z): `nemoclaw onboard --no-gpu` FAILED here, for a host reason
Command: `NEMOCLAW_PROVIDER=vllm NEMOCLAW_POLICY_MODE=skip NEMOCLAW_DISABLE_TELEMETRY=1 nemoclaw onboard --no-gpu --non-interactive --yes --name phantom-dev --yes-i-accept-third-party-software`, through the guardrail launcher, with a local model server on 127.0.0.1:8000.
- Step 1/8 preflight: PASSED (docker, bridge containers, DNS, openshell 0.0.116, port 8080, memory).
- Step 2/8 gateway: managed service failed (`systemctl --user`: no D-Bus session here), standalone fallback started, then **`failed to bind to 172.18.0.1:8080: Cannot assign requested address`**. The gateway binds the Docker bridge address on the host; this box runs ROOTLESS Docker (bridge lives in a private network namespace; `slirp4netns --disable-host-loopback`), so that address does not exist. Same root cause means a sandbox could not reach a loopback model server here either.
- Left behind: nothing running, no containers; `~/.nemoclaw/onboard-session.json` and `~/.local/state/nemoclaw/openshell-docker-gateway/` state. Use `nemoclaw onboard --fresh` to start over.
- **Implication for the GB10:** NemoClaw's tested path is DGX OS with standard (rootful) Docker. On the event machine check FIRST that `docker info` works without rootless/slirp, that the user can run it, and that `ip addr` shows a host-visible docker bridge (172.x). If the GB10 is set up rootless, onboarding will fail the same way; do not work around by weakening network isolation.
- Not rehearsed (blocked by the above): sandbox creation, OpenClaw agent, `channels add discord`, the inference route, the plugin install, the egress preset, `policy add --from-file`. They remain UNKNOWN/untested; see `openclaw-integration/ONSITE_CHECKLIST.md`.
- Also learned: no systemd user bus means `nemoclaw-openshell-gateway.service` cannot be used in this kind of session; standalone fallback works. `local-inference/server.pid` records the launcher's shell pid, not llama-server: find the real pid with `ss -ltnp | grep :8000`.
