"""Slack Block Kit and message builders for PHANTOMSHIFT.

Generates structured Slack messages, attachments, and Block Kit layouts
for incidents, policy forks, status audits, and AUTOPATCH approvals.
"""

from __future__ import annotations

import json
from typing import Any

SLACK_RED = "#E5484D"
SLACK_BLUE = "#3B82F6"
SLACK_AMBER = "#F5A524"
SLACK_GREEN = "#30A46C"
SLACK_GREY = "#6B7280"

FOOTER_TEXT = "PHANTOMSHIFT · Slack Autonomous Control Plane · Zero Cloud LLM Egress"
AUTOPATCH_FOOTER = "AUTOPATCH · Continuous Remediation Loop · RWCR Formula: 3I + 2E + 3R + N + 2Q - 2D"


def slack_attack_blocks(scn: dict, held: dict) -> list[dict]:
    act = scn["attacks"][0]
    args = ", ".join(f"{k}={v}" for k, v in act["args"].items())
    usd = f"${scn['exposure_usd']:,} (synthetic)" if scn.get("exposure_usd") else "n/a (data exposure)"
    violations = "\n".join(f"• {v}" for v in held.get("violations", [])) or "None"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🛡️ HELD: {scn['title']}", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Task:* {scn.get('task', '')}\n*Untrusted Source:* {scn.get('untrusted_source', '')}\n*Broken Boundary:* `{scn.get('boundary', '')}`",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Proposed Action (Intercepted):*\n```{act.get('tool', '')}({args})```",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Financial Exposure:*\n{usd}"},
                {"type": "mrkdwn", "text": "*Backend Ledger Mutated:*\n:no_entry: *NO (Held by ToolFirewall)*"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Authority Violations:*\n{violations}",
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": FOOTER_TEXT}],
        },
    ]


def slack_forks_blocks(rec: dict) -> list[dict]:
    lines = []
    for f in rec.get("forks", []):
        mark = ":white_check_mark: *VERIFIED*" if f.get("verified") else ":x: rejected"
        lines.append(
            f"• *{f.get('name')}* — Attacks executed: {f.get('harmful_executed')}/{f.get('attacks_total')} | "
            f"Legit completed: {f.get('legit_completed')}/{f.get('legit_total')} — {mark}"
        )

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🔀 Parallel Worlds: {rec.get('title', 'Scenario')}", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Selected Policy:*\n`{rec.get('selected', 'none')}`"},
                {"type": "mrkdwn", "text": f"*Replay Mode:*\n`{rec.get('replay_mode', 'policy_only_replay')}`"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": FOOTER_TEXT}],
        },
    ]


def slack_audit_blocks(rec: dict) -> list[dict]:
    v = rec.get("verification")
    ap = rec.get("approval", {})
    trace_tail = rec["trace"][-1]["hash"][:16] if rec.get("trace") else "-"
    verified_str = ":white_check_mark: Verified" if v and v.get("verified") else ":warning: Unverified"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 Audit Record: {rec.get('title', '')}", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Run ID:*\n`{rec.get('run_id')}`"},
                {"type": "mrkdwn", "text": f"*Post-Activation Status:*\n{verified_str}"},
                {"type": "mrkdwn", "text": f"*Approval State:*\n`{ap.get('state')} via Slack`"},
                {"type": "mrkdwn", "text": f"*Trace Chain:*\n`intact={rec.get('trace_chain_ok')} (SHA256)`"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": FOOTER_TEXT}],
        },
    ]


def slack_status_blocks(gates: list[dict], tests: str) -> list[dict]:
    rows = []
    for g in gates:
        icon = ":white_check_mark:" if g.get("status") == "PASS" else (":x:" if g.get("status") == "FAIL" else ":hourglass:")
        rows.append(f"{icon} `{g.get('id', '')}` *{g.get('gate', '')}* — {g.get('status')} ({g.get('detail', '')})")

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "⚡ PHANTOMSHIFT System Status & Technical Gates", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Test Suite:*\n`{tests}`"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Technical Gates:*\n" + "\n".join(rows)},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Host: srva (x86_64 dev host) · Hardware gates report NOT TESTED until onsite GB10 run"}],
        },
    ]


def slack_autopatch_finding_blocks(payload: dict) -> list[dict]:
    fid = payload.get("finding_id", "find-unknown")
    digest = payload.get("digest", "")
    sev = payload.get("severity", "critical").upper()
    rwcr = payload.get("rwcr", {})
    idx = rwcr.get("priority_index", payload.get("priority_index", 40))

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 AUTOPATCH Finding: Policy Deployment Required", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Finding ID:*\n`{fid}`"},
                {"type": "mrkdwn", "text": f"*Severity:*\n:rotating_light: *{sev}* (RWCR Index: `{idx}`)"},
                {"type": "mrkdwn", "text": f"*Recommended Policy:*\n`context_bound`"},
                {"type": "mrkdwn", "text": f"*Policy Digest:*\n`{digest[:16]}…`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Mechanism:*\nUnauthorized payment recipient derived from untrusted document context. Policy engine intercepted attempt.",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Operator Instructions:*\nReact with :white_check_mark: to authorize policy activation, or :x: to reject.",
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": AUTOPATCH_FOOTER}],
        },
    ]
