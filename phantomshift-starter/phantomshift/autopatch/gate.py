"""Fast enforcement path: ALLOW / DENY / REQUIRE_APPROVAL (fail-closed)."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from ..tool_firewall import ToolFirewall


class GateDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class EnforcementGate:
    """Wraps ToolFirewall; never trusts model or invoice provenance labels."""

    def __init__(self, firewall: ToolFirewall, *, hook_timeout_ms: float = 50.0) -> None:
        self.firewall = firewall
        self.hook_timeout_ms = hook_timeout_ms

    def evaluate(
        self,
        tool_name: str,
        params: dict | None,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        policy_store_ok: bool = True,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        if not policy_store_ok:
            return self._out(GateDecision.DENY, "POLICY_STORE_UNAVAILABLE", "policy store unavailable; fail closed", t0, run_id, session_id)
        if params is not None and not isinstance(params, dict):
            return self._out(GateDecision.DENY, "SCHEMA_MISMATCH", "params must be object", t0, run_id, session_id)

        raw = self.firewall.before_tool_call(tool_name, params or {}, run_id=run_id)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > self.hook_timeout_ms:
            return self._out(GateDecision.DENY, "HOOK_TIMEOUT", f"hook exceeded {self.hook_timeout_ms}ms budget", t0, run_id, session_id)

        if raw.get("block"):
            return {
                **self._out(GateDecision.DENY, raw.get("reason_code", "DENIED"), raw.get("blockReason", ""), t0, run_id, session_id),
                "incident_id": raw.get("incident_id"),
                "block": True,
            }

        # Adapter may return PENDING_APPROVAL on submit path; hook precheck is ALLOW for payment precheck pass
        state_hint = raw.get("state")
        if state_hint == "PENDING_APPROVAL":
            dec = GateDecision.REQUIRE_APPROVAL
        else:
            dec = GateDecision.ALLOW

        return {
            "decision": dec.value,
            "reason_code": raw.get("reason_code", "OK"),
            "reason": raw.get("note", "allowed by deterministic precheck"),
            "latency_ms": round(elapsed_ms, 4),
            "run_id": run_id,
            "session_id": session_id,
            "incident_id": raw.get("incident_id"),
            "block": False,
            "openclaw": {"block": False} if dec == GateDecision.ALLOW else {"block": True, "blockReason": "approval required"},
        }

    def _out(self, dec: GateDecision, code: str, reason: str, t0: float, run_id, session_id) -> dict[str, Any]:
        ms = (time.perf_counter() - t0) * 1000
        block = dec != GateDecision.ALLOW
        return {
            "decision": dec.value,
            "reason_code": code,
            "reason": reason,
            "latency_ms": round(ms, 4),
            "run_id": run_id,
            "session_id": session_id,
            "block": block,
            "openclaw": {"block": block, "blockReason": reason} if block else {"block": False},
        }
