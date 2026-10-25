# On-site checklist: H03, H04, H05 proofs (GB10)

Every command below appears in the pinned docs (`REF = refs/NemoClaw`, v0.0.137) or in `--help` output.
Nothing has been run against a sandbox. Replace `<sb>` with the sandbox name. Capture raw output with `tee`
into `artifacts/runtime-verification/raw/`; the `*.json` proof files are built from those captures by a script,
never typed by hand. Never put tokens in argv, files or screenshots. Review any capture before committing it.

```bash
EV=artifacts/runtime-verification/raw; mkdir -p "$EV"
```

## 0. Versions and host (both gates need these)

| Command | Expect | Evidence file |
|---|---|---|
| `nemoclaw --version` | `nemoclaw v0.0.137` | `$EV/nemoclaw-version.txt` |
| `openshell --version` | `openshell 0.0.116` | `$EV/openshell-version.txt` |
| `nemoclaw host probe --json` | host and gateway readiness, no changes made | `$EV/host-probe.json` |
| `nemoclaw doctor --json` and `nemoclaw <sb> doctor --json` | no blocking failures | `$EV/doctor*.json` |

## H03: local inference, no remote LLM (R01)

| # | Command | Expect | Evidence file |
|---|---|---|---|
| 1 | `curl -s http://127.0.0.1:8000/v1/models` (host model server, `set-up-vllm.mdx`) | local model id listed | `$EV/h03-host-models.json` |
| 2 | `nemoclaw inference get --json` | `provider`, `model`, `endpointUrl`/endpoint all local; docs name the provider `vllm-local`; no `build.nvidia`, `openrouter`, `openai`, `anthropic`, `generativelanguage` (the words `verify_hackathon.py` rejects) | `$EV/h03-inference-get.json` |
| 3 | `nemoclaw list --json` | sandbox row shows provider `vllm-local` and the intended model | `$EV/h03-list.json` |
| 4 | `nemoclaw <sb> status` | `Inference` row healthy; local-backend diagnostics present | `$EV/h03-status.txt` |
| 5 | `openshell inference get` | gateway route consistent with step 2 | `$EV/h03-openshell-inference.txt` |
| 6 | `nemoclaw credentials list` | no hosted-provider credential registered | `$EV/h03-credentials.txt` |
| 7 | `nemoclaw <sb> agent --agent main --json -m 'Reply with the single word PONG'` | a reply from the local model (the turn goes through the selected route) | `$EV/h03-agent-turn.json` |
| 8 | `nemoclaw <sb> logs --since 10m` and `openshell logs <sb> --since 10m` | no connection to a hosted inference host during steps 4 and 7 | `$EV/h03-logs.txt` |
| 9 | `nemoclaw <sb> policy list`, then `nemoclaw <sb> policy exclude nvidia --dry-run` (optional) | R01 caveat: baseline `nvidia` entry still allows `integrate.api.nvidia.com` for the openclaw binary (`openclaw-sandbox.yaml:66`). UNKNOWN whether it can be excluded; record the dry-run output either way | `$EV/h03-policy.txt` |

Pass condition: steps 2, 3, 4 and 7 agree on a local provider and model, and step 8 shows no hosted egress.
`inference.local` alone is not proof (it also fronts hosted shared routes); keep the full step 2 output.
UNKNOWN on site: the exact `inference get` text for local vLLM with OpenClaw (`README.md` section 4).

## H04: NemoClaw + OpenClaw + OpenShell present, real tool call through the guard (R02)

| # | Command | Expect | Evidence file |
|---|---|---|---|
| 1 | `nemoclaw <sb> status` | sandbox Ready, agent process running, applied policy presets listed | `$EV/h04-status.txt` |
| 2 | `nemoclaw <sb> exec -- openclaw --version` | OpenClaw version (manifest expects `2026.9.2`, `agents/openclaw/manifest.yaml:22`) | `$EV/h04-openclaw-version.txt` |
| 3 | `nemoclaw <sb> skill install ./openclaw-integration/skill/phantomshift-payment-guard/` then `nemoclaw <sb> skill list` | skill listed (a new agent session may be needed) | `$EV/h04-skill.txt` |
| 4 | `nemoclaw <sb> upload ./openclaw-integration/plugin/phantomshift-payment-tool /sandbox/phantomshift-payment-tool` then `nemoclaw <sb> exec -- openclaw plugins install /sandbox/phantomshift-payment-tool` (check `--help` for `--accept-capabilities`) | install succeeds; UNKNOWN: scanner verdict | `$EV/h04-plugin-install.txt` |
| 5 | `nemoclaw <sb> gateway restart`, then `nemoclaw <sb> exec -- openclaw plugins inspect phantomshift-payment --runtime --json` | plugin loaded, tool `phantomshift_submit_payment` registered | `$EV/h04-plugin-runtime.json` |
| 6 | Start the host adapter listener (lead's work, bound to the bridge address, not `0.0.0.0`). Inside the sandbox: `nemoclaw <sb> exec -- getent hosts host.openshell.internal` | bridge IP, e.g. `172.17.0.1` style (`troubleshooting.mdx:2727`) | `$EV/h04-bridge-ip.txt` |
| 7 | BEFORE applying the preset: run the tool once (step 10). Then `openshell term`, select the sandbox, press `r`, inspect the pending rule. Press `x` (reject) | tool returns `ERROR ... ADAPTER_UNREACHABLE`; TUI shows host, port, **binary**, method, path. This is the "denied egress seen in openshell term" evidence (R02). Screenshot it | `$EV/h04-denied-egress.png` |
| 8 | Edit `policy/phantomshift-adapter-preset.yaml` (real IP `/32`, port, binary from step 7), then `nemoclaw <sb> policy add --from-file ./openclaw-integration/policy/phantomshift-adapter-preset.yaml --dry-run` | preview shows one endpoint, `POST /api/adapter/submit`, one binary | `$EV/h04-policy-dryrun.txt` |
| 9 | Same command with `--yes`, then `nemoclaw <sb> policy list` | `phantomshift-adapter` present | `$EV/h04-policy-applied.txt` |
| 10 | `nemoclaw <sb> agent --agent main --json -m '<prompt asking it to pay a test invoice>'` | model calls `phantomshift_submit_payment`; reply states the adapter verdict (`DENIED`, `PENDING_APPROVAL` or `EXECUTED_SIMULATED`), never "paid" | `$EV/h04-agent-turn.json` |
| 11 | `nemoclaw <sb> sessions list`, then `nemoclaw <sb> sessions export <key>` (or `nemoclaw <sb> exec -- ls -lh /sandbox/.openclaw/agents/main/sessions`) | session JSONL contains the tool call and the verdict. Files are `0600`; treat as sensitive | `$EV/h04-session-<key>.jsonl` |
| 12 | Adapter side: the event store `verify()` on the host, and the request log | one entry per submission, chain verifies | `artifacts/events.sqlite` + verify output |
| 13 | Optional tool-registration proof without the LLM: `nemoclaw <sb> gateway-token`, then in the sandbox `POST http://127.0.0.1:18789/tools/invoke` body `{"agentId":"main","tool":"phantomshift_submit_payment","args":{...}}` with the bearer (pattern from `full-e2e.test.ts:288-300`; INFERRED to work for our plugin) | `{"ok":true,...}` | `$EV/h04-tools-invoke.json` |

Pass condition: `H04` in `verify_hackathon.py` needs `nemoclaw`+`openshell` found and a registered sandbox
(`nemoclaw list --json`); steps 5, 7, 10, 11 are the stronger proof the script does not read yet. `H01`
additionally needs an `AGENT_STARTED` event from a real OpenClaw agent in the event store.

## H05: Discord through the OpenClaw-managed channel (R03)

Run on the HOST. Token by silent prompt only (`GB10_RUNBOOK.md`, `set-up-discord.mdx`).

| # | Command | Expect | Evidence file |
|---|---|---|---|
| 1 | `read -rsp "Discord bot token: " DISCORD_BOT_TOKEN; echo; export DISCORD_BOT_TOKEN DISCORD_SERVER_ID=<id> DISCORD_USER_ID=<id> DISCORD_REQUIRE_MENTION=1` | no output of the token | none (never saved) |
| 2 | `nemoclaw <sb> channels list` | `discord` listed for OpenClaw | `$EV/h05-channels-list.txt` |
| 3 | `nemoclaw <sb> channels add discord` (answer yes to rebuild, or `nemoclaw <sb> rebuild`) | preset `discord` applied; post-rebuild bridge check prints no warnings | `$EV/h05-channels-add.txt` |
| 4 | `nemoclaw <sb> channels status --json` | `discord` registered, policy covered, rendered config matches registry. No runtime probe is documented for Discord | `$EV/h05-channels-status.json` |
| 5 | `nemoclaw <sb> policy list` | `discord` preset present | `$EV/h05-policy.txt` |
| 6 | `nemoclaw <sb> exec -- cat /sandbox/.openclaw/openclaw.json`, inspect `channels.discord` | `groupPolicy: allowlist`, `guilds.<id>.requireMention: true`, `guilds.<id>.users` and `accounts.default.allowFrom` hold your id, `dmPolicy: allowlist`; token appears only as `openshell:resolve:env:DISCORD_BOT_TOKEN`. Redact before saving | `$EV/h05-openclaw-channels-discord.json` |
| 7 | `nemoclaw <sb> logs --follow` in one terminal; in Discord, as the allowed operator, mention the bot | gateway log shows the inbound message and a reply; the bot answers in the channel | `$EV/h05-gateway.log` + sanitized screenshot |
| 8 | Negative tests: same message without a mention; a message from a second account; a DM from the second account | no agent turn in any of the three (this is the only real proof of enforcement; semantics are UNKNOWN in the docs) | `$EV/h05-negative.txt` |
| 9 | `nemoclaw <sb> sessions list`, `sessions export <key>` for the Discord session | turn present; check whether a sender id appears (UNKNOWN) | `$EV/h05-session.jsonl` |
| 10 | `openshell term` while sending | allowed: `discord.com`, `gateway.discord.gg`; nothing else new. If the bot logs in but never answers, see `troubleshooting.mdx:2382-2406` (Node, not curl, is the probe) | `$EV/h05-term.png` |
| 11 | Approval round trip (UNKNOWN mechanism): send `approve <nonce> <digest>` as the operator; confirm which trusted component received it and with which sender id (`README.md` section 2.4) | adapter state moves `PENDING_APPROVAL` to `EXECUTED_SIMULATED` only after a matching message from the allowed sender | `$EV/h05-approval.txt` |

Pass condition per `verify_hackathon.py`: `artifacts/runtime-verification/channel.json` with
`is_live: true`, `openclaw_managed: true`, `type: "discord"`, non-empty `round_trip`, composed from steps 3, 4, 7
and 11 output. Only this path counts; `phantomshift/discord_channel.py` does not.

## Stop conditions

Stop and read the docs listed in `README.md` section 6 if: `plugins install` rejects the plugin; `policy add`
rejects `allowed_ips`; `getent hosts host.openshell.internal` is empty; the tool gets `upstream_unreachable`
instead of `policy_denied` (policy matched, gateway cannot reach the host address, `troubleshooting.mdx:2602`);
or any step needs `sudo`, `onboard --fresh`, or a token on a command line.
