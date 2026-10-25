# PHANTOMSHIFT: Slack Autonomous Operator & Approval Guide

## 1. Overview
PHANTOMSHIFT integrates with Slack via two complementary interfaces:
1. **Python Stdlib REST Client (`phantomshift.slack_channel.SlackChannel`)**:
   - Zero external pip dependencies.
   - Posts Block Kit alerts, incident summaries, and cryptographic approval requests.
   - Intercepted attacks post to `#live-attacks` / operator DM.
   - Proposed candidate policy diffs post to `#approvals` / operator DM with single-click reaction emojis (`:white_check_mark:` and `:x:`).
   - Drains AUTOPATCH continuous remediation outbox to Slack.
2. **Slack Bolt Socket Mode Agent (`invoice-guard/`)**:
   - Connects to Slack workspace `T0CC0F124R0` (`Chetas`) over persistent WebSocket using `SLACK_APP_TOKEN`.
   - Listens for operator mentions and direct messages.
   - Dispatches security commands (`scan`, `simulate`, `report`, `status`, `help`) directly against the local, airgapped PHANTOMSHIFT policy engine.

---

## 2. Credentials & Scopes
All credentials are stored in `.env` (gitignored, mode 600, never committed):
- `SLACK_BOT_TOKEN`: Bot token (`xoxb-...`) with scopes: `app_mentions:read`, `channels:history`, `chat:write`, `im:history`, `im:read`, `im:write`, `reactions:write`, `reactions:read`, `users:read`, `assistant:write`.
- `SLACK_USER_TOKEN`: Admin user token (`xoxp-...`) for workspace `Chetas` (`lucifer.gator`).
- `SLACK_APP_TOKEN`: App-level token (`xapp-...`) with `connections:write` scope for Socket Mode.
- `SLACK_TEAM_ID`: `T0CC0F124R0`
- `SLACK_APP_ID`: `A0CBUHZ7C2X`

---

## 3. Operator Commands (in Slack DMs or Mentions)
- `status`: Displays workspace connectivity, bot identity, local inference route, and deterministic policy engine state.
- `scan [scenario]`: Evaluates the requested invoice scenario (default `invoice_redirect`) against the deterministic AP `ToolFirewall`.
- `simulate [scenario]`: Replays counterfactual defensive policies (`baseline`, `lockdown`, `allowlist`, `context_bound`).
- `report`: Displays the extended 40-case held-out benchmark results, Wilson 95% confidence intervals, and zero-residual-risk caveats.
- `help`: Lists available security commands.

---

## 4. Reaction-Based Approvals
When a high-risk invoice attack is intercepted and an AUTOPATCH finding is generated:
1. An approval card is posted to the operator containing:
   - Finding ID (e.g. `find-174ecc6538`)
   - Severity and RWCR priority index ($3I + 2E + 3R + N + 2Q - 2D = 40$)
   - Cryptographic candidate policy digest (`1baaad58fec7...`)
   - Pre-populated reaction emojis: `:white_check_mark:` (Approve) and `:x:` (Reject).
2. The operator reacts:
   - Reacting with `:white_check_mark:` authorizes the transaction and triggers automatic pre-activation backup and regression verification.
   - Reacting with `:x:` marks the proposal rejected.
   - Reacting with both fails closed (rejected).
   - Reactions by unauthorized users are ignored.
3. Every approval nonce is single-use, payload-bound, and recorded in `artifacts/events.sqlite`.

---

## 5. Technical Gate H05 Verification
Gate H05 in `scripts/verify_hackathon.py` verifies:
- Freshness within 24 hours.
- Host binding (`srva`).
- Channel type `slack`.
- Cryptographic approval nonce corroborated in `artifacts/events.sqlite`.
- Status: **`PASS`**.
