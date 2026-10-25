"""Discord event authorization and approval-message verification. Pure logic, no network.

`authorize_discord_event(event, policy)` answers one question: did an allowed human operator
send this event from the allowed guild and channel? It fails closed: a missing or oddly typed
field rejects. IDs are compared as exact strings (Discord snowflakes as JSON strings); ints,
padded or case-folded values never match, and an allow-list must be a real collection so a
bare string cannot turn into a substring match.

Event shape (Discord MESSAGE_CREATE, or a reaction event with user_id instead of author):
    {"guild_id": "...", "channel_id": "...", "author": {"id": "...", "bot": false},
     "content": "...", "id": "<message id>", "timestamp": "2026-10-24T10:00:00+00:00"}
Discord omits author.bot for humans, so an absent flag counts as human; if the flag is
present it must be exactly False. Webhook messages (webhook_id) and system authors reject.
A missing guild_id means a DM and rejects unless policy["allow_dm"] is True.

Policy: {"guild_id": str, "channel_ids": [str], "user_ids": [str], "allow_dm": bool (default False)}.

`ApprovalBinding` wraps phantomshift.approval.ApprovalGate (unmodified) and adds the Discord
facts the gate does not know. An operator approves by sending, in the approvals channel:
        approve <nonce> <digest>      or      reject <nonce> <digest>
where <digest> is the FULL sha256 config digest from the request (exact match, not a prefix).
Checks, in order: event authorization, approval channel, message grammar, known nonce,
message not seen before, message timestamp not before the request and not in the future, exact digest,
then the gate itself (actor allow-list, expiry, one-time use). A wrong digest does not burn
the nonce; a successful or rejected response does.

This is a rehearsal-grade check on events handed to it. It does not authenticate the event
source: that is the OpenClaw channel's job on the GB10 (hackathon gate H05).
"""

from __future__ import annotations

import hmac
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .approval import ApprovalGate

_ID = re.compile(r"^[0-9]{5,25}$")
_CMD = re.compile(r"^(approve|reject)\s+([0-9a-f]{16})\s+([0-9a-f]{64})$")
CLOCK_SKEW_S = 2.0


def _id_set(value: Any, name: str) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)) or not value:
        raise ValueError(f"policy.{name} must be a non-empty list of strings")
    if not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"policy.{name} entries must be non-empty strings")
    return frozenset(value)


def _check_policy(policy: Any) -> tuple[str, frozenset[str], frozenset[str], bool]:
    if not isinstance(policy, Mapping):
        raise ValueError("policy must be a mapping")
    guild = policy.get("guild_id")
    if not isinstance(guild, str) or not guild:
        raise ValueError("policy.guild_id must be a non-empty string")
    allow_dm = policy.get("allow_dm", False)
    if not isinstance(allow_dm, bool):
        raise ValueError("policy.allow_dm must be a bool")
    return guild, _id_set(policy.get("channel_ids"), "channel_ids"), _id_set(policy.get("user_ids"), "user_ids"), allow_dm


def _fail(code: str, detail: str) -> tuple[bool, str]:
    return False, f"{code}: {detail}"


def authorize_discord_event(event: dict, policy: dict) -> tuple[bool, str]:
    """(ok, reason). Never raises. Reason starts with a short machine code."""
    try:
        guild, channels, users, allow_dm = _check_policy(policy)
    except ValueError as exc:
        return _fail("bad_policy", str(exc))
    try:
        if not isinstance(event, Mapping):
            return _fail("bad_event", "event must be a mapping")
        author = event.get("author")
        if author is None and "user_id" in event:  # reaction-style event
            author = {"id": event.get("user_id")}
        if not isinstance(author, Mapping):
            return _fail("missing_field", "author")
        aid = author.get("id")
        if not isinstance(aid, str) or not _ID.match(aid):
            return _fail("missing_field", "author.id must be a snowflake string")
        if "user_id" in event and event["user_id"] != aid:
            return _fail("author_mismatch", "user_id differs from author.id")
        if "bot" in author and author["bot"] is not False:
            return _fail("bot_author", "bot or malformed bot flag")
        if author.get("system") not in (None, False) or event.get("webhook_id") is not None:
            return _fail("bot_author", "webhook or system author")
        gid = event.get("guild_id")
        if gid is None:
            if not allow_dm:
                return _fail("dm_not_allowed", "direct messages are rejected by policy")
        else:
            if not isinstance(gid, str) or not gid:
                return _fail("missing_field", "guild_id must be a string")
            if gid != guild:
                return _fail("wrong_guild", "guild is not the allowed guild")
            cid = event.get("channel_id")
            if not isinstance(cid, str) or not cid:
                return _fail("missing_field", "channel_id")
            if cid not in channels:
                return _fail("wrong_channel", "channel is not an allowed channel")
        if aid not in users:
            return _fail("unauthorized_author", "author is not an allowed operator")
        return True, "ok"
    except Exception as exc:  # noqa: BLE001  fail closed
        return _fail("error", f"{type(exc).__name__}: {exc}")


def _event_ts(event: Mapping) -> float | None:
    raw = event.get("timestamp", event.get("ts"))
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            v = float(raw)
        except OverflowError:
            return None
        return v if math.isfinite(v) else None  # NaN/inf would pass both the stale and future checks
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            v = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
        except (ValueError, OverflowError, OSError):
            return None
        return v if math.isfinite(v) else None
    return None


class ApprovalBinding:
    def __init__(self, policy: dict, *, ttl_s: float = 300.0, clock: Callable[[], float] = time.time,
                 approval_channel_id: str | None = None, require_timestamp: bool = True) -> None:
        _, channels, users, _ = _check_policy(policy)
        if approval_channel_id is not None and approval_channel_id not in channels:
            raise ValueError("approval_channel_id must be one of policy.channel_ids")
        self.policy = dict(policy)
        self.gate = ApprovalGate(set(users), ttl_s=ttl_s, clock=clock)
        self._clock, self._ttl = clock, ttl_s
        self._channel = approval_channel_id
        self._require_ts = require_timestamp
        self._bound: dict[str, dict[str, Any]] = {}
        self._seen_messages: set[str] = set()

    def request(self, cfg: dict, *, replay_tested: bool, message_id: str | None = None) -> dict:
        """Issue a nonce for cfg. Refuses unless the candidate was replay-tested first."""
        if replay_tested is not True:
            raise ValueError("refusing to request approval: candidate policy has not been replay-tested")
        req = self.gate.request(cfg)
        issued = self._clock()
        self._bound[req["nonce"]] = {"digest": req["digest"], "issued": issued, "expires": issued + self._ttl,
                                     "message_id": message_id}
        req["reply_with"] = f"approve {req['nonce']} {req['digest']}"
        return req

    def verify_approval_message(self, event: dict, *, approve: bool | None = None) -> dict:
        """Check one operator message. Returns {ok, reason, state?, actor?, nonce?, digest?}. Never raises.

        `approve` is derived from the message verb; pass it only to assert an expected verb."""
        def no(reason: str, **extra: Any) -> dict:
            return {"ok": False, "reason": reason, **extra}
        try:
            ok, why = authorize_discord_event(event, self.policy)
            if not ok:
                return no(why)
            if self._channel is not None and event.get("channel_id") != self._channel:
                return no("wrong_channel: not the approvals channel")
            content = event.get("content")
            m = _CMD.match(content.strip().lower()) if isinstance(content, str) else None
            if not m:
                return no("bad_message: expected 'approve|reject <nonce> <full digest>'")
            verb, nonce, digest = m.groups()
            if approve is not None and approve != (verb == "approve"):
                return no("verb_mismatch: message verb differs from the expected decision")
            bound = self._bound.get(nonce)
            if bound is None:
                return no("unknown_nonce: no approval was requested with this nonce", nonce=nonce)
            mid = event.get("id")
            if not isinstance(mid, str) or not mid:
                return no("missing_field: message id", nonce=nonce)
            if mid in self._seen_messages:
                return no("replayed_message: this message id was already processed", nonce=nonce)
            ts = _event_ts(event)
            if ts is None and event.get("timestamp", event.get("ts")) is not None:
                return no("bad_timestamp: message timestamp is present but not a finite time", nonce=nonce)
            if ts is None and self._require_ts:
                return no("missing_field: message timestamp", nonce=nonce)
            if ts is not None and ts < bound["issued"] - CLOCK_SKEW_S:
                return no("stale_message: message predates the approval request", nonce=nonce)
            if ts is not None and ts > self._clock() + CLOCK_SKEW_S:
                return no("future_message: message timestamp is in the future", nonce=nonce)
            if not hmac.compare_digest(digest.encode(), bound["digest"].encode()):
                return no("digest_mismatch: message digest differs from the requested config digest", nonce=nonce)
            self._seen_messages.add(mid)
            actor = event.get("author", {}).get("id") if isinstance(event.get("author"), Mapping) else event.get("user_id")
            resp = self.gate.respond(nonce, actor, verb == "approve")
            if not resp["ok"]:
                return no(f"gate_refused: {resp['reason']}", nonce=nonce)
            return {"ok": True, "reason": "ok", "state": resp["state"], "actor": actor, "nonce": nonce,
                    "digest": bound["digest"], "message_id": mid}
        except Exception as exc:  # noqa: BLE001  fail closed
            return no(f"error: {type(exc).__name__}: {exc}")

    def activate(self, nonce: str, cfg: dict) -> dict:
        """Delegate to ApprovalGate.activate: approved for exactly this config, and it validates."""
        return self.gate.activate(nonce, cfg)


__all__ = ["authorize_discord_event", "ApprovalBinding"]
