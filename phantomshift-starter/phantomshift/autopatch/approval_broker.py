"""Proof-carrying approval binding (server-side operators only)."""

from __future__ import annotations

import secrets
import time
from typing import Any, Callable

from ..approval import ApprovalGate, config_digest


class FindingApprovalBroker:
    def __init__(
        self,
        operators: set[str],
        *,
        ttl_s: float = 900.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._gate = ApprovalGate(operators, ttl_s=ttl_s, clock=clock)
        self._clock = clock
        self._bindings: dict[str, dict[str, Any]] = {}

    def request_for_finding(self, finding_id: str, policy_cfg: dict, *, expected_policy_version: str) -> dict:
        req = self._gate.request(policy_cfg)
        op_id = secrets.token_hex(8)
        self._bindings[req["nonce"]] = {
            "operation_id": op_id,
            "finding_id": finding_id,
            "candidate_hash": config_digest(policy_cfg),
            "expected_policy_version": expected_policy_version,
            "expires_at": self._clock() + req["expires_in_s"],
        }
        return {
            **req,
            "operation_id": op_id,
            "finding_id": finding_id,
            "candidate_policy_hash": config_digest(policy_cfg),
            "expected_policy_version": expected_policy_version,
            "expires_at": self._bindings[req["nonce"]]["expires_at"],
        }

    def respond(self, nonce: str, operator_id: str, approve: bool) -> dict:
        resp = self._gate.respond(nonce, operator_id, approve)
        bind = self._bindings.get(nonce)
        if resp.get("ok") and bind:
            resp["binding"] = bind
            resp["candidate_policy_hash"] = bind["candidate_hash"]
        return resp

    def activate(self, nonce: str, policy_cfg: dict) -> dict:
        bind = self._bindings.get(nonce)
        if bind and config_digest(policy_cfg) != bind["candidate_hash"]:
            return {"ok": False, "reason": "policy digest mismatch vs approval binding"}
        return self._gate.activate(nonce, policy_cfg)
