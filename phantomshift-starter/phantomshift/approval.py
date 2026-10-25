"""Operator approval for policy changes: expiring single-use nonce, actor allow-list,
and binding to the exact config digest. The agent can request but never approve.

The channel here is whatever delivers the nonce to the operator. SimulatedChannel is
a local stand-in and is NOT an OpenClaw messaging channel.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Callable

from .policies import validate_config


def config_digest(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SimulatedChannel:
    real = False
    name = "simulated-local (NOT an OpenClaw channel)"

    def __init__(self) -> None:
        self.outbox: list[str] = []

    def send(self, text: str) -> str:
        self.outbox.append(text)
        return "sim-0"


class ApprovalGate:
    def __init__(self, operators: set[str], ttl_s: float = 300.0, clock: Callable[[], float] = time.time) -> None:
        self._operators = set(operators)
        self._ttl = ttl_s
        self._clock = clock
        self._pending: dict[str, dict[str, Any]] = {}

    def request(self, cfg: dict) -> dict:
        nonce = secrets.token_hex(8)
        self._pending[nonce] = {"digest": config_digest(cfg), "expires": self._clock() + self._ttl,
                                "state": "pending", "actor": None}
        return {"nonce": nonce, "digest": self._pending[nonce]["digest"], "expires_in_s": self._ttl}

    def respond(self, nonce: str, actor: str, approve: bool) -> dict:
        """Never raises: a non-string or unencodable (e.g. lone-surrogate) nonce/actor is a refusal."""
        if type(nonce) is not str:
            return {"ok": False, "reason": "unknown nonce"}
        rec = self._pending.get(nonce)
        if rec is None:
            return {"ok": False, "reason": "unknown nonce"}
        if rec["state"] != "pending":
            return {"ok": False, "reason": f"nonce already used ({rec['state']})"}
        if self._clock() > rec["expires"]:
            rec["state"] = "expired"
            return {"ok": False, "reason": "nonce expired"}
        if not self._is_operator(actor):
            return {"ok": False, "reason": "actor is not an authorised operator"}
        rec["state"] = "approved" if approve else "rejected"
        rec["actor"] = actor
        return {"ok": True, "state": rec["state"]}

    def _is_operator(self, actor: Any) -> bool:
        if type(actor) is not str:
            return False
        try:
            a = actor.encode("utf-8")
            return any(hmac.compare_digest(a, op.encode("utf-8")) for op in self._operators)
        except (UnicodeError, TypeError):
            return False

    def activate(self, nonce: str, cfg: dict) -> dict:
        """Return the config to deploy only if approved for exactly this config, still within the
        SAME ttl that bounds respond() (measured from request(); an approval older than ttl cannot be
        activated), and it validates. One-time: a second activate fails. The returned config is a deep
        copy taken before the digest check, so it is exactly what was approved and never the caller's alias."""
        if type(nonce) is not str:
            return {"ok": False, "reason": "not approved"}
        rec = self._pending.get(nonce)
        if rec is None or rec["state"] != "approved":
            return {"ok": False, "reason": "not approved"}
        if self._clock() > rec["expires"]:
            rec["state"] = "expired"
            return {"ok": False, "reason": "approval expired before activation"}
        try:
            snap = copy.deepcopy(cfg)
            digest = config_digest(snap)
        except Exception:  # noqa: BLE001  un-copyable / un-serialisable config is never approved
            return {"ok": False, "reason": "config is not a plain JSON-serialisable object"}
        if rec["digest"] != digest:
            return {"ok": False, "reason": "config differs from the approved proposal"}
        problems = validate_config(snap)
        if problems:
            return {"ok": False, "reason": "invalid config: " + "; ".join(problems)}
        rec["state"] = "activated"
        return {"ok": True, "config": snap}
