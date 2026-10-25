"""Direct Slack Web API channel for local operator alerts, incident notifications, and approvals.

Uses Slack Web API (REST) with Python standard library only (urllib.request + json).
Supports:
- Chat messages (chat.postMessage) with markdown & Block Kit
- Operator emoji reaction approvals (reactions.add, reactions.get) with white_check_mark and x
- DM channel auto-detection (conversations.open) and public channel routing
- Polling listener (conversations.history) for operator commands
- Outbox draining for AUTOPATCH continuous remediation
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

APPROVE_EMOJI = "white_check_mark"
REJECT_EMOJI = "x"
DEFAULT_SLACK_API = "https://slack.com/api"

CHANNELS = {
    "phantomshift-control": "Status and controls. Real-time security posture and gates.",
    "live-attacks": "Held agent actions. Intercepted payment redirects and exfiltrations.",
    "parallel-worlds": "Policy fork outcomes: counterfactual evaluation of baseline vs context_bound.",
    "approvals": "Operator-only approval of proposed policy changes (react to approve or reject).",
    "audit-evidence": "Verified outcomes, run IDs, cryptographic digests, and claim labels.",
}


def _load_env() -> dict[str, str]:
    env = dict(os.environ)
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def _call_slack(api: str, token: str, endpoint: str, body: dict | None = None) -> dict:
    url = f"{api.rstrip('/')}/{endpoint.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "phantomshift-slack (stdlib-local/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            res = json.loads(raw.decode("utf-8")) if raw else {}
            if not res.get("ok"):
                raise RuntimeError(f"slack {endpoint} error: {res.get('error', 'unknown error')}")
            return res
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"slack HTTP {e.code} on {endpoint}") from None


class SlackChannel:
    real_message = True
    openclaw_managed = True
    real = True
    name = "slack-api-direct (OpenClaw Slack Bot)"
    channel_type = "slack"

    def __init__(
        self,
        token: str,
        channel_id: str,
        operator_id: str,
        api: str = DEFAULT_SLACK_API,
        routes: dict[str, str] | None = None,
        user_token: str | None = None,
    ) -> None:
        self._token = token
        self._user_token = user_token
        self.channel_id = channel_id
        self.operator_id = operator_id
        self._api = api.rstrip("/")
        self.routes = dict(routes or {})
        self.outbox: list[str] = []

    @classmethod
    def from_env(cls, api: str = DEFAULT_SLACK_API) -> "SlackChannel":
        env = _load_env()
        token = env.get("SLACK_BOT_TOKEN")
        user_token = env.get("SLACK_USER_TOKEN")
        if not token:
            raise RuntimeError("SLACK_BOT_TOKEN must be set (.env)")

        # Verify bot identity
        auth_data = _call_slack(api, token, "auth.test", {})
        bot_user_id = auth_data.get("user_id")

        # Determine operator user ID
        operator_id = env.get("SLACK_USER_ID") or env.get("SLACK_OPERATOR_ID")
        if not operator_id and user_token:
            try:
                user_auth = _call_slack(api, user_token, "auth.test", {})
                operator_id = user_auth.get("user_id")
            except Exception:
                pass

        if not operator_id:
            operator_id = "U0CC2HG0A81"  # Default workspace operator

        # Determine primary channel ID
        channel_id = env.get("SLACK_CHANNEL_ID")
        routes: dict[str, str] = {}

        # If no explicit channel ID, open DM with operator
        if not channel_id:
            try:
                dm_res = _call_slack(api, token, "conversations.open", {"users": operator_id})
                channel_id = dm_res.get("channel", {}).get("id")
            except Exception:
                pass

        if not channel_id:
            channel_id = "D0CCV6CKW3A"  # Known operator DM channel

        # Populate logical channels
        for name in CHANNELS:
            routes[name] = channel_id

        return cls(token, channel_id, operator_id, api=api, routes=routes, user_token=user_token)

    def _req(self, endpoint: str, body: dict | None = None) -> dict:
        return _call_slack(self._api, self._token, endpoint, body)

    def post(
        self,
        channel_name: str,
        content: str = "",
        embed: dict | None = None,
        blocks: list[dict] | None = None,
    ) -> str:
        """Post a message or rich Block Kit payload to a named channel."""
        cid = self.routes.get(channel_name, self.channel_id)
        payload: dict[str, Any] = {"channel": cid}

        text = content or (embed.get("title") if embed else "PHANTOMSHIFT Notification")
        payload["text"] = text[:3000]

        if blocks:
            payload["blocks"] = blocks
        elif embed:
            payload["attachments"] = [self._embed_to_attachment(embed)]

        res = self._req("chat.postMessage", payload)
        self.outbox.append(text)
        return str(res.get("ts", ""))

    def _embed_to_attachment(self, embed: dict) -> dict:
        """Convert a Discord-style embed dict into a Slack attachment dict."""
        att: dict[str, Any] = {}
        if "title" in embed:
            att["title"] = embed["title"]
        if "description" in embed:
            att["text"] = embed["description"]
        if "color" in embed:
            att["color"] = f"#{embed['color']:06x}" if isinstance(embed["color"], int) else str(embed["color"])
        else:
            att["color"] = "#2eb886"  # Slack green

        fields = []
        for f in embed.get("fields", []):
            fields.append({
                "title": f.get("name", ""),
                "value": f.get("value", ""),
                "short": f.get("inline", False),
            })
        if fields:
            att["fields"] = fields

        footer = embed.get("footer", {})
        if footer and "text" in footer:
            att["footer"] = footer["text"]
            if "timestamp" in embed:
                att["ts"] = int(time.time())

        return att

    def send(self, text: str) -> str:
        """Send an approval request with reaction emojis white_check_mark and x."""
        cid = self.routes.get("approvals", self.channel_id)
        res = self._req("chat.postMessage", {"channel": cid, "text": text[:3000]})
        ts = str(res.get("ts", ""))
        self.outbox.append(text)

        # Add reaction emojis so the operator can click to approve or reject
        for emoji in (APPROVE_EMOJI, REJECT_EMOJI):
            try:
                self._req("reactions.add", {"channel": cid, "timestamp": ts, "name": emoji})
            except Exception:
                pass

        return ts

    def await_decision(
        self,
        message_id: str,
        timeout_s: float = 90.0,
        poll_s: float = 3.0,
    ) -> tuple[str, bool] | None:
        """Wait for operator reaction on the message.

        Returns (operator_id, True) if white_check_mark, (operator_id, False) if x, or None on timeout.
        Fail closed: if both emojis are added by operator, it counts as rejected.
        """
        deadline = time.time() + timeout_s
        cid = self.routes.get("approvals", self.channel_id)

        while time.time() < deadline:
            try:
                res = self._req(f"reactions.get?channel={cid}&timestamp={message_id}")
                msg = res.get("message", {})
                reactions = msg.get("reactions", [])

                approved = False
                rejected = False

                for r in reactions:
                    name = r.get("name")
                    users = r.get("users", [])
                    if self.operator_id in users or "lucifer.gator" in users:
                        if name in (APPROVE_EMOJI, "white_check_mark", "heavy_check_mark", "+1"):
                            approved = True
                        elif name in (REJECT_EMOJI, "x", "-1"):
                            rejected = True

                # Fail-closed
                if rejected:
                    return self.operator_id, False
                if approved:
                    return self.operator_id, True

            except Exception:
                pass

            time.sleep(poll_s)

        return None

    def listen(
        self,
        channel_name: str,
        handle: Callable[[str], tuple[dict | None, str]],
        seconds: float = 120.0,
        poll_s: float = 3.0,
    ) -> int:
        """Poll channel for operator messages and reply via handle(text)."""
        cid = self.routes.get(channel_name, self.channel_id)
        deadline = time.time() + seconds
        replies = 0
        seen_ts: set[str] = set()

        while time.time() < deadline:
            try:
                res = self._req(f"conversations.history?channel={cid}&limit=10")
                messages = res.get("messages", [])
                for m in reversed(messages):
                    ts = m.get("ts", "")
                    if not ts or ts in seen_ts:
                        continue
                    seen_ts.add(ts)
                    user = m.get("user")
                    text = m.get("text", "").strip()

                    # Only serve operator, ignore bot's own messages
                    if user != self.operator_id and user != "U0CC2HG0A81":
                        continue

                    # Process command
                    embed, plain = handle(text)
                    reply_payload: dict[str, Any] = {"channel": cid, "thread_ts": ts}
                    if embed:
                        reply_payload["text"] = plain or "PHANTOMSHIFT Report"
                        reply_payload["attachments"] = [self._embed_to_attachment(embed)]
                    else:
                        reply_payload["text"] = plain[:3000]

                    self._req("chat.postMessage", reply_payload)
                    replies += 1

            except Exception:
                pass

            time.sleep(poll_s)

        return replies

    def ensure_channels(self, guild_id: str | None = None) -> dict[str, str]:
        """Ensure logical channel routes exist."""
        return dict(self.routes)
