"""Direct Discord REST channel for development rehearsal.

Posts incident and approval requests to a real Discord channel and reads the operator's
reaction. Uses only REST (no gateway, no privileged intents). A real Discord message is
sent, but this is NOT the OpenClaw-managed channel the hackathon requires (R03).

Approval = the configured operator's user ID reacting on the exact message we posted.
Reactions by anyone else are ignored.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

APPROVE, REJECT = "✅", "❌"
DEFAULT_API = "https://discord.com/api/v10"
CHANNELS = {
    "phantomshift-control": "Status and controls. Fixtures only until the GB10 runtime exists.",
    "live-attacks": "Held agent actions. Synthetic fixtures, never real money.",
    "parallel-worlds": "Policy fork outcomes: what each defence does to the attack and to legit work.",
    "approvals": "Operator-only approval of proposed policy changes (react to approve or reject).",
    "audit-evidence": "Verified outcomes, run ids, digests and claim labels.",
}


class DiscordChannel:
    real_message = True
    openclaw_managed = False
    real = False  # kept False so nothing treats this as the hackathon channel
    name = "discord-rest-direct (dev rehearsal, NOT OpenClaw-managed)"

    def __init__(self, token: str, channel_id: str, operator_id: str, api: str = DEFAULT_API,
                 routes: dict | None = None) -> None:
        self._token, self.channel_id, self.operator_id, self._api = token, channel_id, operator_id, api.rstrip("/")
        self.routes = dict(routes or {})  # logical channel name -> channel id
        self.outbox: list[str] = []

    @classmethod
    def from_env(cls, api: str = DEFAULT_API) -> "DiscordChannel":
        env = _load_env()
        token, guild, op = env.get("DISCORD_BOT_TOKEN"), env.get("DISCORD_SERVER_ID"), env.get("DISCORD_USER_ID")
        if not (token and guild and op):
            raise RuntimeError("DISCORD_BOT_TOKEN, DISCORD_SERVER_ID and DISCORD_USER_ID must be set (.env)")
        chans = _call(api, token, "GET", f"/guilds/{guild}/channels")
        routes = {c["name"]: c["id"] for c in chans if c["type"] == 0}
        ch = env.get("DISCORD_CHANNEL_ID") or routes.get("approvals") or routes.get("general")
        if not ch:
            raise RuntimeError("no usable text channel found")
        return cls(token, ch, op, api, routes)

    def ensure_channels(self, guild_id: str) -> dict:
        """Idempotently create the PHANTOMSHIFT category and channels. Returns name -> id."""
        existing = self._req("GET", f"/guilds/{guild_id}/channels")
        cat = next((c for c in existing if c["type"] == 4 and c["name"].lower() == "phantomshift"), None)
        if cat is None:
            cat = self._req("POST", f"/guilds/{guild_id}/channels", {"name": "PHANTOMSHIFT", "type": 4})
        have = {c["name"]: c["id"] for c in existing if c["type"] == 0}
        for name, topic in CHANNELS.items():
            if name not in have:
                made = self._req("POST", f"/guilds/{guild_id}/channels",
                                 {"name": name, "type": 0, "parent_id": cat["id"], "topic": topic})
                have[name] = made["id"]
        self.routes.update(have)
        return {n: have[n] for n in CHANNELS}

    def listen(self, channel_name: str, handle, seconds: float = 120.0, poll_s: float = 3.0) -> int:
        """Poll a channel for operator messages that mention the bot and reply via `handle(text)`.

        `handle` returns (embed or None, text). Only the operator is served; everyone else is
        ignored. Without the Message Content intent Discord still delivers content for messages
        that mention the bot, which is all this needs. Returns the number of replies sent.
        """
        cid = self.routes.get(channel_name, self.channel_id)
        me = self._req("GET", "/users/@me")["id"]
        last = (self._req("GET", f"/channels/{cid}/messages?limit=1") or [{"id": "0"}])[0]["id"]
        deadline, replies = time.time() + seconds, 0
        while time.time() < deadline:
            batch = self._req("GET", f"/channels/{cid}/messages?after={last}&limit=20")
            for m in sorted(batch, key=lambda m: int(m["id"])):
                last = m["id"]
                mentioned = any(u["id"] == me for u in m.get("mentions", []))
                if not mentioned or m["author"]["id"] != self.operator_id:
                    continue
                text = m.get("content", "").replace(f"<@{me}>", "").replace(f"<@!{me}>", "").strip()
                embed, plain = handle(text)
                body = {"message_reference": {"message_id": m["id"]}}
                body.update({"embeds": [embed]} if embed else {"content": plain[:1900]})
                self._req("POST", f"/channels/{cid}/messages", body)
                replies += 1
            time.sleep(poll_s)
        return replies

    def post(self, channel_name: str, content: str = "", embed: dict | None = None) -> str:
        """Post to a named channel; falls back to the default channel if it does not exist."""
        cid = self.routes.get(channel_name, self.channel_id)
        body: dict = {}
        if content:
            body["content"] = content[:1900]
        if embed:
            body["embeds"] = [embed]
        self.outbox.append(content or embed.get("title", ""))
        return self._req("POST", f"/channels/{cid}/messages", body)["id"]

    def _req(self, method: str, path: str, body: dict | None = None):
        return _call(self._api, self._token, method, path, body)

    def send(self, text: str) -> str:
        self.outbox.append(text)
        cid = self.routes.get("approvals", self.channel_id)
        self.channel_id = cid  # reactions are read from the same channel
        msg = self._req("POST", f"/channels/{cid}/messages", {"content": text[:1900]})
        mid = msg["id"]
        for emoji in (APPROVE, REJECT):  # best effort: bot may lack Add Reactions
            try:
                self._req("PUT", f"/channels/{cid}/messages/{mid}/reactions/{urllib.parse.quote(emoji)}/@me")
            except Exception:  # noqa: BLE001
                break
        return mid

    def await_decision(self, message_id: str, timeout_s: float = 90.0, poll_s: float = 3.0):
        """Return (actor_id, approve) for the operator's reaction, or None on timeout.

        Fail closed: if the operator reacted both approve and reject, that is a reject. Only the operator's
        own reaction counts. (Reactions are not bound to a nonce or digest; the digest-exact flow is
        discord_auth.ApprovalBinding over message events.)"""
        deadline = time.time() + timeout_s
        while True:
            seen = {}
            for emoji, approve in ((APPROVE, True), (REJECT, False)):
                users = self._req("GET", f"/channels/{self.channel_id}/messages/{message_id}/reactions/"
                                  f"{urllib.parse.quote(emoji)}?limit=100")
                seen[approve] = any(u["id"] == self.operator_id for u in users)
            if seen[False]:
                return self.operator_id, False
            if seen[True]:
                return self.operator_id, True
            if time.time() >= deadline:
                return None
            time.sleep(poll_s)


def _load_env() -> dict:
    env = dict(os.environ)
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def _call(api: str, token: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        api + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json",
                 "User-Agent": "phantomshift-rehearsal (local, 0.2)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"discord {method} {path.split('?')[0]} -> HTTP {e.code}") from None
