"""Deterministic authorization — final decision independent of model output."""

from __future__ import annotations

from typing import Any

from .policies import BASELINE, evaluate


def evaluate_action(policy: dict | None, action: dict) -> dict[str, Any]:
    """Return allow/deny for a scenarios-shaped action dict."""
    pol = policy or BASELINE
    d = evaluate(pol, action)
    return {"allow": d["allow"], "rule": d.get("rule", ""), "reason": d.get("reason", ""), "policy": pol["name"]}


def action_from_payment_params(params: dict) -> dict:
    """Map OpenClaw payment tool params to gateway action shape (provenance always untrusted on args)."""
    return {
        "tool": "pay_invoice",
        "args": {
            "vendor_id": params.get("vendor_id"),
            "amount": int(params["amount"]) // 100 if params.get("amount") is not None else None,
            "account": params.get("recipient_account_id"),
        },
        "prov": {
            "vendor_id": "registry",
            "amount": "untrusted",
            "account": "untrusted",
        },
        "labels": [],
    }
