# Discord operator guide

Read 2026-10-24 about 10:05Z. Covers what the operator can do **today** with the rehearsal channel, how that differs from the OpenClaw-managed channel the hackathon requires, token rules, and intents. Server and user numeric IDs are deliberately not written here.

Labels: **observed** (artifact or command output), **simulated**, **unverified**.

## 1. Two different things called "the Discord channel"

| | Rehearsal channel (exists) | OpenClaw-managed channel (required, not built) |
|---|---|---|
| Code | `phantomshift/discord_channel.py`, `commands.py`, `discord_views.py`, CLI subcommands | `nemoclaw <sandbox> channels add discord` on the GB10 |
| Transport | Plain Discord REST from a local Python process; no gateway connection, no privileged intents | NemoClaw/OpenShell routes Discord REST and gateway traffic through its managed proxy (`refs/NemoClaw/docs/manage-sandboxes/set-up-discord.mdx`) |
| Who holds the token | A local `.env` read by our scripts | Registered with the OpenShell gateway as a provider credential; non-secret config saved for rebuilds (`refs/NemoClaw/docs/reference/commands.mdx`, `channels add`) |
| What answers | Fixed handlers: `scan`, `simulate`, `report`, `help` on fixtures | The OpenClaw agent (a model) |
| Code's own labels | `openclaw_managed = False`, `real = False`, embed footer "dev rehearsal channel (not OpenClaw-managed)" | `channel.json` must say `openclaw_managed: true` (`scripts/verify_hackathon.py`) |
| Counts for the channel gate (H05 / R03) | **No** (`scripts/discord_check.py` writes `satisfies_R03: false`) | Yes, only with a saved real round trip |

Nothing in this guide makes the rehearsal channel an OpenClaw channel. Do not describe it as one in the demo.

## 2. Preflight state (observed in `artifacts/runtime-verification/discord-preflight.json`, 2026-10-24T09:38Z)

| Check | Result |
|---|---|
| Token valid (REST `GET /users/@me`) | true |
| Bot is in the target server | true |
| Operator is a member of the server | true (REST member lookup succeeded) |
| Text channels visible | `general` only; the planned PHANTOMSHIFT channels had not been created |
| Message Content intent | `false` (OFF) |
| Server Members intent | `false` (OFF) |
| Messages sent by the preflight | none (`sends_messages: false`) |

Re-run the read-only check any time with `python3 scripts/discord_check.py`. It reads `.env`, prints no token, sends nothing, and overwrites that JSON file.

## 3. Setup (operator, once)

`.env` in the repo root holds `DISCORD_BOT_TOKEN`, `DISCORD_SERVER_ID`, `DISCORD_USER_ID`, optionally `DISCORD_CHANNEL_ID` (template: `.env.example`). Process environment variables win over `.env` (`_load_env` uses `setdefault`), so a stale exported token in your shell overrides the file.

| Step | Command | Effect |
|---|---|---|
| Create channels and post a status card | `python3 -m phantomshift discord-setup` | Creates category `PHANTOMSHIFT` and text channels `phantomshift-control`, `live-attacks`, `parallel-worlds`, `approvals`, `audit-evidence` if missing (idempotent), then posts a status embed to `#phantomshift-control`. It also runs `scripts/verify_hackathon.py` and the unit-test suite as subprocesses; the test run rewrites `artifacts/runtime-verification/verify.json` and `host.json` in competition mode (observed), so re-run `python3 scripts/verify_hackathon.py` afterwards |
| Permissions the bot needs | create channels (for `discord-setup`), send messages and embeds, add reactions, read message history, view channels | derived from the REST calls in `discord_channel.py`; the Discord permission names are general Discord knowledge, **unverified** in this repo |

Not observed anywhere: a successful run of `discord-setup`, `discord-listen` or `run --discord` against the real Discord API that produced a complete round trip. `tests/test_discord_channel.py` tests these paths against a **stub** Discord API only.

## 4. Using the rehearsal channel today

### 4.1 Mention commands (operator only)

Start the listener, then mention the bot in the channel from the operator account:

```
python3 -m phantomshift discord-listen --channel phantomshift-control --seconds 120
```

| Message (after the mention) | Reply |
|---|---|
| `scan [scenario]` | Hold-check the scripted attacks and legit actions against the authority record |
| `simulate [scenario]` | Policy-only replay of the attack under baseline and every candidate policy |
| `report` | Held-out numbers, hard cases and caveats |
| `help` | Command list |

Scenarios: `invoice_redirect` (default), `ticket_exfil`, `log_secret_post`. Behaviour from `phantomshift/discord_channel.py` `listen()`:

* It is a polling loop for the given number of seconds, not a standing bot. When the loop ends nothing answers.
* It starts from the newest message at start-up; older messages are ignored.
* Only messages that mention the bot **and** come from the configured operator ID are served; everyone else is ignored silently.
* Replies are threaded to the operator's message. Every embed footer says it is a synthetic fixture, policy-only replay, rehearsal channel.
* Mention commands do not need the Message Content intent according to the code's docstring (Discord still delivers content for messages that mention the bot). **Unverified live**: no artifact shows this against real Discord.

### 4.2 Run an incident with a real approval

```
python3 -m phantomshift run --scenario invoice_redirect --discord --wait 90
```

What happens (`phantomshift/incident.py`, `discord_channel.py`):

1. Posts the held-action card to `live-attacks` and the fork table to `parallel-worlds` (falls back to the default channel if those do not exist).
2. Posts the approval request to `approvals`: candidate policy, "SYNTHETIC FIXTURE", short digest, and an instruction to react.
3. The bot pre-adds the two reactions (best effort; if it lacks Add Reactions the operator adds them): check mark (U+2705) approves, cross mark (U+274C) rejects.
4. Polls every 3 seconds for up to `--wait` seconds (default 90) for a reaction **by the configured operator ID on that exact message**. Reactions by anyone else are ignored.
5. On approval it re-verifies the activated policy in live mode on the fixtures and posts an audit card to `audit-evidence` with the run id, trace head and the line "local checksum chain, not a signature".
6. Writes `artifacts/runs/<run_id>.json`.

Operator notes:

* React with one emoji only. The poll checks approve first, so if both are present, approve wins (code order).
* Timeout means no activation: the record says `no operator response before timeout`. **Observed:** both Discord runs on file (`artifacts/runs/4a65a2dc9721.json`, `5650c1ef3636.json`) ended that way, so no approved Discord round trip is recorded yet. The third file (`160a8709112f.json`) is a simulated-channel run, approval `activated`.
* Reaction approval and mention commands use REST only and need no privileged intent (docstring of `discord_channel.py`).
* The text-message grammar `approve <nonce> <full digest>` in `phantomshift/discord_auth.py` exists but is not wired into this channel. If it were used, the bot would have to read message text from a channel where the message does not mention it, which on a gateway-connected bot needs the Message Content intent (general Discord behaviour, **unverified here**).

## 5. Differences from the OpenClaw-managed channel (what changes on the GB10)

| Topic | Rehearsal today | OpenClaw-managed on the GB10 |
|---|---|---|
| Install | none; scripts in this repo | `nemoclaw <sandbox> channels add discord` from the host (not from inside the sandbox), applies the Discord network preset, then offers a rebuild (`refs/NemoClaw/docs/manage-sandboxes/add-channels-after-onboarding.mdx`) |
| Token entry | `.env` file | silent prompt on the host: `read -rsp "Discord bot token: " DISCORD_BOT_TOKEN` (`docs/GB10_RUNBOOK.md`); NemoClaw rejects the literal placeholder |
| Access control | `DISCORD_USER_ID` compared in our code; others ignored | `DISCORD_USER_ID` restricts to one user; **without it any member of the server can message the bot** (`set-up-discord.mdx` lines 24-26) |
| Mention mode | mention required for commands | `DISCORD_REQUIRE_MENTION=1` is the default when `DISCORD_SERVER_ID` is set; `0` makes the bot reply to all messages in the server |
| Egress | host process talks to `discord.com` directly | sandbox egress is deny-by-default; Discord REST and gateway (`gateway.discord.gg`) go through the managed proxy; blocked requests show in `openshell term` (`reference/troubleshooting.mdx` line 2382) |
| What responds | our fixed handlers | the OpenClaw agent; how PHANTOMSHIFT handlers become OpenClaw tools is **unknown** (`docs/GB10_RUNBOOK.md`) |
| Approval | emoji reaction polled over REST, digest not typed | **unknown**: pinned docs never mention reactions; runbook lists "reactions or a message reply handled by the agent" as undecided |
| Proof | none counts | `channel.json` from a real round trip with `is_live`, `openclaw_managed`, `type`, `round_trip` |
| Status check | `python3 scripts/discord_check.py` | `nemoclaw <sandbox> channels status`, `nemoclaw <sandbox> logs --follow` |
| Dev bot reuse | the same bot may be reused | do not run `discord-listen` against the same bot while the OpenClaw channel is live, to avoid double replies (precaution; whether anything breaks is unverified) |

## 6. Token handling rules

| Rule | Why and evidence |
|---|---|
| Never paste a token into any chat, issue, commit message, doc or screenshot | `PROGRESS.md`: the first token was pasted into an AI chat in plain text and is to be treated as exposed |
| **Reset the token that was pasted earlier** in the Discord Developer Portal, then put the new value only in `.env` (and in your shell prompt on the GB10) | `PROGRESS.md`. No artifact shows the reset has happened, so treat it as **not done** until you confirm |
| After a reset, re-run `python3 scripts/discord_check.py`; expect `token_valid: true` for the new token. Also `unset DISCORD_BOT_TOKEN` in any shell that still has the old one | `_load_env` prefers process environment over `.env` |
| `.env` stays gitignored and mode 600 | observed: `.gitignore` lists `.env` and `.env.*` (keeping `.env.example`); `stat` showed mode `600` at read time. I did not open `.env` |
| Do not `cat`, `echo`, log or paste `.env`. Scripts never print the token; `tests/test_discord_channel.py::test_token_never_in_messages` checks messages against the stub | test is stub-level |
| On the GB10, give the token by silent prompt, never in argv, never in shell history | `docs/GB10_RUNBOOK.md`; NemoClaw's own doc example uses `export DISCORD_BOT_TOKEN="<...>"`, which puts the value in history if typed literally, so prefer the runbook form |
| No token on the USB drive | `offline-kit/README.md` step 5 |
| Operator and server IDs are not secrets but are kept out of tracked files | `PROGRESS.md` |
| If a token may have leaked, reset first, investigate second | general practice |

## 7. Intents status

| Intent | Status now | Needed by the rehearsal channel | Needed by the OpenClaw channel |
|---|---|---|---|
| Message Content | **OFF** (observed, preflight 09:38Z) | No for reaction approval and for mention commands (REST, per docstring; unverified live) | **Unverified.** The runbook says the bot needs it; the pinned NemoClaw docs and source never mention Discord intents (grep found nothing). Decide on site: enable only if the channel fails to receive content, and record that in the evidence |
| Server Members | **OFF** (observed) | No. The preflight's REST member lookup succeeded with it off | Runbook says "per our own setup notes"; unverified in NVIDIA docs |
| Presence | not probed | not used | unverified |

How the preflight decides: it reads the application flags from `GET /oauth2/applications/@me` and tests the Message Content and Guild Members bits (`scripts/discord_check.py`). If you change a toggle in the Developer Portal, re-run it.

Text approvals via `discord_auth.ApprovalBinding` would change the Message Content answer (section 4.2).

## 8. Quick troubleshooting

| Symptom | Likely cause (from code) |
|---|---|
| `DISCORD_BOT_TOKEN, DISCORD_SERVER_ID and DISCORD_USER_ID must be set (.env)` | `.env` missing a key and env not set |
| `HTTP 401` | token wrong or reset; first token on record was one character too long (`PROGRESS.md`) |
| `HTTP 403` on `discord-setup` | bot lacks permission to create channels |
| Approval message posted but no reactions on it | bot lacks Add Reactions (best effort; operator can add them) |
| Run ends `no operator response before timeout` | no reaction from the operator ID within `--wait`; raise `--wait` or react sooner |
| Mention command gets no reply | listener not running (it only runs for `--seconds`), message did not mention the bot, author is not the operator, or the message predates the listener |
| Everything posts to `#general` | the PHANTOMSHIFT channels do not exist yet; run `discord-setup` |
| Status card shows gates as FAIL instead of NOT TESTED | someone ran the verify script in competition mode last; re-run `python3 scripts/verify_hackathon.py` (prep mode) |

## 9. Unverified claims in this guide

* Mention commands working without Message Content against real Discord.
* Any full round trip (`discord-setup`, `discord-listen`, `run --discord` with an approval) against real Discord.
* Discord permission names for the bot.
* Whether the pasted token was reset.
* Whether OpenClaw needs either privileged intent, and whether it can handle reaction approval.
* Whether running the rehearsal poller beside the OpenClaw channel causes any conflict.
