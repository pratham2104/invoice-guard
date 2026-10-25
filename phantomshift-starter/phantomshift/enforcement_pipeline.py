"""Flagship workflow: synthetic invoice -> tool firewall -> incident receipt (stdlib)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .adapter import PaymentAdapter, fixture_registry
from .incident import run_incident
from .tool_firewall import ToolFirewall
from .scenarios import SCENARIOS


def malicious_payment_proposal(scenario_id: str = "invoice_redirect") -> dict:
    """OpenClaw-shaped params for the primary attack (untrusted recipient)."""
    scn = SCENARIOS[scenario_id]
    act = scn["attacks"][0]
    args = act["args"]
    return {
        "vendor_id": args["vendor_id"],
        "invoice_id": "INV-2291",
        "amount": int(args["amount"]) * 100,
        "currency": "USD",
        "recipient_account_id": args["account"],
        "evidence_spans": [scn["untrusted_content"][:120]],
        "idempotency_key": "k" + uuid.uuid4().hex[:24],
        "requested_by": "openclaw-agent",
    }


def run_firewall_acceptance_test(scenario_id: str = "invoice_redirect") -> dict[str, Any]:
    """Acceptance: malicious proposal blocked; mock ledger unchanged."""
    adapter = PaymentAdapter(fixture_registry(), mode="live")
    fw = ToolFirewall(adapter)
    before = fw.simulator.row_count()
    params = malicious_payment_proposal(scenario_id)
    result = fw.execute_guarded_payment(params)
    after = fw.simulator.row_count()
    passed = (
        result.get("block") or result.get("state") == "DENIED"
    ) and after == before == 0
    return {
        "acceptance": "firewall_blocks_malicious_payment",
        "passed": passed,
        "result_state": result.get("state"),
        "reason_code": result.get("reason_code") or result.get("reason_code"),
        "ledger_rows_before": before,
        "ledger_rows_after": after,
        "receipt_digest": result.get("receipt_digest"),
        "trace_chain_ok": result.get("trace_chain_ok"),
        "incident_id": result.get("incident_id"),
    }


def run_full_fixture_pipeline(scenario_id: str = "invoice_redirect", *, out_dir: str = "artifacts/runs") -> dict[str, Any]:
    """Firewall test plus existing incident runner (replay, approval sim, verification)."""
    fw_out = run_firewall_acceptance_test(scenario_id)
    inc = run_incident(scenario_id, approve=True)
    path = Path(out_dir) / f"{inc['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inc, indent=2))
    return {"firewall": fw_out, "incident": {"run_id": inc["run_id"], "selected": inc.get("selected"), "path": str(path)}}
