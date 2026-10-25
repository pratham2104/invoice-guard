"""Enforcement boundary: intercept tool calls before effects (OpenClaw before_tool_call target)."""

from __future__ import annotations

import copy
from typing import Any

from .adapter import PaymentAdapter
from .incident_recorder import IncidentRecorder
from .payment_simulator import PaymentSimulator
from .policies import BASELINE
from .policy_evaluator import action_from_payment_params, evaluate_action
from .trusted_context import get_registry, verify_recipient, verify_requester, vendor_record

# Finance agent may only invoke these tools. Everything else is blocked at the hook.
FINANCE_AGENT_TOOL_ALLOWLIST = frozenset({"phantomshift_submit_payment"})

# Explicit deny list for common bypass paths (names vary by runtime; block all not allowlisted anyway).
KNOWN_BYPASS_TOOL_NAMES = frozenset({
    "exec", "shell", "bash", "run_terminal_cmd", "run_command", "execute", "write_file",
    "http_request", "fetch", "curl", "pay_invoice", "transfer_funds", "wire_payment",
})


def _redact_params(params: dict) -> dict:
    out = copy.deepcopy(params)
    if "recipient_account_id" in out and isinstance(out["recipient_account_id"], str):
        out["recipient_account_id"] = out["recipient_account_id"][:4] + "…"
    if "evidence_spans" in out and isinstance(out["evidence_spans"], list):
        out["evidence_spans"] = [(str(s)[:24] + "…") if len(str(s)) > 24 else s for s in out["evidence_spans"][:3]]
    return out


class ToolFirewall:
    """Allow, deny or defer to adapter for the single guarded payment tool."""

    def __init__(
        self,
        adapter: PaymentAdapter,
        *,
        policy: dict | None = None,
        recorder: IncidentRecorder | None = None,
        allowlist: frozenset[str] | None = None,
    ) -> None:
        self.adapter = adapter
        self.policy = policy or BASELINE
        self.recorder = recorder or IncidentRecorder()
        self.simulator = PaymentSimulator(adapter)
        self.allowlist = allowlist or FINANCE_AGENT_TOOL_ALLOWLIST

    def before_tool_call(
        self,
        tool_name: str,
        params: dict | None,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Shape returned to OpenClaw hook: block, blockReason, or allow (pass-through)."""
        params = params if isinstance(params, dict) else {}
        name = (tool_name or "").strip()
        self.recorder.record_tool_attempt(name, _redact_params(params), run_id=run_id)

        if name in KNOWN_BYPASS_TOOL_NAMES or name not in self.allowlist:
            reason = f"tool {name!r} is not on the finance-agent allow-list"
            self.recorder.record_denial(name, "TOOL_NOT_ALLOWED", reason, run_id=run_id)
            return {"block": True, "blockReason": reason, "reason_code": "TOOL_NOT_ALLOWED", "incident_id": self.recorder.incident_id}

        if name == "phantomshift_submit_payment":
            return self._precheck_payment(params, run_id=run_id)

        self.recorder.record_denial(name, "TOOL_NOT_ALLOWED", "unknown allowlisted tool", run_id=run_id)
        return {"block": True, "blockReason": "unknown tool", "reason_code": "TOOL_NOT_ALLOWED"}

    def _precheck_payment(self, params: dict, *, run_id: str | None) -> dict[str, Any]:
        registry = self.adapter.registry
        vid = params.get("vendor_id")
        acct = params.get("recipient_account_id")
        req = params.get("requested_by", "openclaw-agent")
        ok_r, msg_r = verify_requester(str(req))
        if not ok_r:
            self.recorder.record_denial("phantomshift_submit_payment", "REQUESTER_DENIED", msg_r, run_id=run_id)
            return {"block": True, "blockReason": msg_r, "reason_code": "REQUESTER_DENIED"}

        master = vendor_record(registry, str(vid)) if vid else None
        if master is None:
            self.recorder.record_denial("phantomshift_submit_payment", "UNKNOWN_VENDOR", "vendor not in master", run_id=run_id)
            return {"block": True, "blockReason": "vendor not in trusted master", "reason_code": "UNKNOWN_VENDOR"}

        ok, msg = verify_recipient(registry, str(vid), str(acct))
        pol = evaluate_action(self.policy, action_from_payment_params(params))
        if not pol["allow"]:
            self.recorder.record_denial("phantomshift_submit_payment", "POLICY_DENIED", pol["reason"], run_id=run_id)
            return {
                "block": True,
                "blockReason": pol["reason"],
                "reason_code": "POLICY_DENIED",
                "policy": pol["policy"],
                "vendor_master": master,
                "recipient_check": msg,
            }
        if not ok:
            self.recorder.record_denial("phantomshift_submit_payment", "RECIPIENT_MISMATCH", msg, run_id=run_id)
            return {"block": True, "blockReason": msg, "reason_code": "RECIPIENT_MISMATCH", "vendor_master": master}

        return {
            "block": False,
            "allow": True,
            "incident_id": self.recorder.incident_id,
            "vendor_master": master,
            "policy_precheck": pol,
            "note": "precheck passed; execution still enforced by PaymentAdapter (fail-closed)",
        }

    def execute_guarded_payment(self, params: dict, *, run_id: str | None = None) -> dict[str, Any]:
        """Full adapter submit after hook allow — records verdict and ledger proof."""
        before = self.simulator.snapshot()
        hook = self.before_tool_call("phantomshift_submit_payment", params, run_id=run_id)
        if hook.get("block"):
            return {
                **hook,
                "state": "DENIED",
                "executed_simulated": False,
                "ledger_unchanged": True,
                "ledger_rows": len(before),
            }
        verdict = self.adapter.submit(params)
        after = self.simulator.snapshot()
        self.recorder.record_execution("phantomshift_submit_payment", verdict)
        return {
            **verdict,
            "incident_id": self.recorder.incident_id,
            "ledger_unchanged": before == after and verdict.get("state") != "EXECUTED_SIMULATED",
            "ledger_rows": len(after),
            "trace_chain_ok": self.recorder.trace.verify(),
            "receipt_digest": self.recorder.receipt_digest(
                {"verdict_state": verdict.get("state"), "reason_code": verdict.get("reason_code"), "ledger_rows": len(after)}
            ),
        }
